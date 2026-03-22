# AIMETA P=参考文档API_上传与管理|R=上传电子书_列表_删除|NR=不含写作生成|E=route:/api/references/*|X=http|A=APIRouter|D=fastapi|S=db|RD=./README.ai
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.reference import ReferenceDocumentItem, ReferenceUploadResponse
from ...schemas.user import UserInDB
from ...services.llm_service import LLMService
from ...services.novel_service import NovelService
from ...services.reference_document_service import ReferenceDocumentService

router = APIRouter(prefix="/api/references", tags=["References"])


@router.get("/projects/{project_id}/documents", response_model=List[ReferenceDocumentItem])
async def list_reference_documents(
    project_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> List[ReferenceDocumentItem]:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    service = ReferenceDocumentService(session, LLMService(session))
    docs = await service.list_documents(project_id)
    return [ReferenceDocumentItem.model_validate(item) for item in docs]


@router.post(
    "/projects/{project_id}/documents/upload",
    response_model=ReferenceUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference_document(
    project_id: str,
    file: UploadFile,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> ReferenceUploadResponse:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    service = ReferenceDocumentService(session, LLMService(session))
    doc = await service.upload_and_ingest(project_id, current_user.id, file)
    return ReferenceUploadResponse(
        document=ReferenceDocumentItem.model_validate(doc),
        message="参考文档上传并向量化完成",
    )


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reference_document(
    project_id: str,
    document_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> Response:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)

    service = ReferenceDocumentService(session, LLMService(session))
    await service.delete_document(project_id, document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
