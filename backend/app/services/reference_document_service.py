# AIMETA P=参考文档服务_电子书入库RAG|R=上传解析_分块向量化_删除|NR=不含章节写作|E=ReferenceDocumentService|X=internal|A=服务类|D=fastapi,sqlalchemy,zipfile|S=db,fs|RD=./README.ai
from __future__ import annotations

import html
import logging
import re
import zipfile
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import List, Optional
from xml.etree import ElementTree as ET

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models.reference_document import ReferenceDocument
from .llm_service import LLMService
from .vector_store_service import VectorStoreService

logger = logging.getLogger(__name__)

try:  # noqa: SIM105 - 可选依赖
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:  # pragma: no cover
    RecursiveCharacterTextSplitter = None  # type: ignore[assignment]


class _HtmlTextExtractor(HTMLParser):
    """简易 HTML 文本提取器。"""

    def __init__(self) -> None:
        super().__init__()
        self._parts: List[str] = []

    def handle_data(self, data: str) -> None:  # noqa: D401
        if data:
            self._parts.append(data)

    def text(self) -> str:
        merged = " ".join(self._parts)
        return re.sub(r"\s+", " ", html.unescape(merged)).strip()


class ReferenceDocumentService:
    """参考文档上传、向量化与管理。"""

    _ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".epub"}
    _MAX_FILE_SIZE = 25 * 1024 * 1024

    def __init__(
        self,
        session: AsyncSession,
        llm_service: LLMService,
        vector_store: Optional[VectorStoreService] = None,
    ) -> None:
        self._session = session
        self._llm_service = llm_service
        self._vector_store = vector_store or VectorStoreService()
        self._text_splitter = self._init_text_splitter()

    async def list_documents(self, project_id: str) -> List[ReferenceDocument]:
        stmt = (
            select(ReferenceDocument)
            .where(ReferenceDocument.project_id == project_id)
            .order_by(ReferenceDocument.created_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def upload_and_ingest(self, project_id: str, user_id: int, file: UploadFile) -> ReferenceDocument:
        if not settings.vector_store_enabled:
            raise HTTPException(status_code=400, detail="未启用向量库，无法上传参考文档")

        filename = file.filename or "unnamed"
        suffix = Path(filename).suffix.lower()
        if suffix not in self._ALLOWED_SUFFIXES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"仅支持 {', '.join(sorted(self._ALLOWED_SUFFIXES))} 文件",
            )

        file_bytes = await file.read()
        file_size = len(file_bytes)
        if file_size == 0:
            raise HTTPException(status_code=400, detail="上传文件为空")
        if file_size > self._MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail="文件过大，单文件最多 25MB")

        doc = ReferenceDocument(
            project_id=project_id,
            user_id=user_id,
            filename=filename,
            title=Path(filename).stem[:255] or "参考文档",
            file_type=suffix.lstrip("."),
            file_size=file_size,
            status="processing",
        )
        self._session.add(doc)
        await self._session.flush()

        try:
            raw_text = self._extract_text(file_bytes, suffix)
            normalized_text = self._normalize_text(raw_text)
            if len(normalized_text) < 50:
                raise HTTPException(status_code=400, detail="可解析文本太少，无法建立参考资料")

            chunks = self._split_text(normalized_text)
            if not chunks:
                raise HTTPException(status_code=400, detail="文本分块失败，无法建立参考资料")

            records = []
            for idx, chunk in enumerate(chunks):
                embedding = await self._llm_service.get_embedding(chunk, user_id=user_id)
                if not embedding:
                    continue
                records.append(
                    {
                        "id": f"ref:{project_id}:{doc.id}:{idx}",
                        "project_id": project_id,
                        "chapter_number": 0,
                        "chunk_index": idx,
                        "chapter_title": f"[参考书] {doc.title}",
                        "content": chunk,
                        "embedding": embedding,
                        "metadata": {
                            "source_type": "reference_document",
                            "source_id": doc.id,
                            "source_name": doc.title,
                            "chunk_index": idx,
                            "total_chunks": len(chunks),
                        },
                    }
                )

            if not records:
                raise HTTPException(status_code=500, detail="向量化失败，请检查嵌入模型配置")

            await self._vector_store.upsert_chunks(records=records)

            doc.char_count = len(normalized_text)
            doc.chunk_count = len(records)
            doc.status = "ready"
            doc.error_message = None
            await self._session.commit()
            await self._session.refresh(doc)
            logger.info(
                "参考文档入库完成: project=%s doc_id=%s chunks=%s",
                project_id,
                doc.id,
                len(records),
            )
            return doc
        except HTTPException as exc:
            await self._mark_failed(doc, exc.detail)
            raise
        except Exception as exc:  # pragma: no cover - 兜底日志
            logger.exception("参考文档入库失败: project=%s doc_id=%s error=%s", project_id, doc.id, exc)
            await self._mark_failed(doc, str(exc))
            raise HTTPException(status_code=500, detail="参考文档处理失败，请稍后重试") from exc

    async def delete_document(self, project_id: str, document_id: int) -> None:
        stmt = select(ReferenceDocument).where(
            ReferenceDocument.id == document_id,
            ReferenceDocument.project_id == project_id,
        )
        result = await self._session.execute(stmt)
        doc = result.scalars().first()
        if not doc:
            raise HTTPException(status_code=404, detail="参考文档不存在")

        await self._vector_store.delete_reference_document_chunks(project_id=project_id, document_id=document_id)
        await self._session.execute(
            delete(ReferenceDocument).where(
                ReferenceDocument.id == document_id,
                ReferenceDocument.project_id == project_id,
            )
        )
        await self._session.commit()

    async def _mark_failed(self, doc: ReferenceDocument, message: str) -> None:
        doc.status = "failed"
        doc.error_message = message[:1000]
        await self._session.commit()

    def _extract_text(self, file_bytes: bytes, suffix: str) -> str:
        if suffix in {".txt", ".md", ".markdown"}:
            return self._decode_text(file_bytes)
        if suffix == ".epub":
            return self._extract_epub_text(file_bytes)
        raise HTTPException(status_code=400, detail="不支持的文件格式")

    @staticmethod
    def _decode_text(file_bytes: bytes) -> str:
        for encoding in ("utf-8", "gbk", "gb18030"):
            try:
                return file_bytes.decode(encoding)
            except UnicodeDecodeError:
                continue
        raise HTTPException(status_code=400, detail="文件编码不支持，请使用 UTF-8 或 GBK")

    def _extract_epub_text(self, file_bytes: bytes) -> str:
        try:
            with zipfile.ZipFile(BytesIO(file_bytes)) as zf:
                opf_path = self._locate_opf_path(zf)
                spine_paths = self._resolve_spine_paths(zf, opf_path)
                texts = []
                for item_path in spine_paths:
                    if item_path not in zf.namelist():
                        continue
                    raw = zf.read(item_path)
                    content = self._decode_text(raw)
                    extractor = _HtmlTextExtractor()
                    extractor.feed(content)
                    text = extractor.text()
                    if text:
                        texts.append(text)
                return "\n\n".join(texts)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="EPUB 文件损坏或格式非法") from exc
        except ET.ParseError as exc:
            raise HTTPException(status_code=400, detail="EPUB 解析失败，请检查文件完整性") from exc

    @staticmethod
    def _locate_opf_path(zf: zipfile.ZipFile) -> str:
        container_xml = zf.read("META-INF/container.xml")
        root = ET.fromstring(container_xml)
        ns = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
        rootfile = root.find(".//c:rootfile", ns)
        if rootfile is None:
            raise HTTPException(status_code=400, detail="EPUB 缺少 OPF 描述文件")
        opf_path = rootfile.attrib.get("full-path")
        if not opf_path:
            raise HTTPException(status_code=400, detail="EPUB OPF 路径无效")
        return opf_path

    @staticmethod
    def _resolve_spine_paths(zf: zipfile.ZipFile, opf_path: str) -> List[str]:
        opf_xml = zf.read(opf_path)
        root = ET.fromstring(opf_xml)
        ns = {"opf": "http://www.idpf.org/2007/opf"}
        manifest = root.find("opf:manifest", ns)
        spine = root.find("opf:spine", ns)
        if manifest is None or spine is None:
            return []

        id_to_href = {}
        for item in manifest.findall("opf:item", ns):
            item_id = item.attrib.get("id")
            href = item.attrib.get("href")
            if item_id and href:
                id_to_href[item_id] = href

        base_dir = str(Path(opf_path).parent).replace("\\", "/")
        if base_dir == ".":
            base_dir = ""
        paths: List[str] = []
        for item_ref in spine.findall("opf:itemref", ns):
            ref_id = item_ref.attrib.get("idref")
            href = id_to_href.get(ref_id or "")
            if not href:
                continue
            resolved = f"{base_dir}/{href}" if base_dir else href
            paths.append(str(Path(resolved).as_posix()))
        return paths

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = re.sub(r"[ \t]{2,}", " ", normalized)
        return normalized.strip()

    def _split_text(self, text: str) -> List[str]:
        if not text:
            return []
        if self._text_splitter:
            parts = [segment.strip() for segment in self._text_splitter.split_text(text)]
            return [part for part in parts if part]
        return self._legacy_split(text)

    def _init_text_splitter(self) -> Optional["RecursiveCharacterTextSplitter"]:
        if RecursiveCharacterTextSplitter is None:
            return None
        chunk_size = settings.vector_chunk_size
        overlap = min(settings.vector_chunk_overlap, chunk_size // 2)
        return RecursiveCharacterTextSplitter(
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", ";", "；", ",", "，", " "],
            chunk_size=chunk_size,
            chunk_overlap=overlap,
            keep_separator=False,
            strip_whitespace=True,
        )

    @staticmethod
    def _legacy_split(text: str) -> List[str]:
        chunk_size = settings.vector_chunk_size
        overlap = min(settings.vector_chunk_overlap, chunk_size // 2)

        chunks: List[str] = []
        start = 0
        total_length = len(text)
        while start < total_length:
            end = min(total_length, start + chunk_size)
            segment = text[start:end].strip()
            if segment:
                chunks.append(segment)
            if end >= total_length:
                break
            start = max(0, end - overlap)
        return chunks
