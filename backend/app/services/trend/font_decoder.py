# AIMETA P=字体反爬解码器|R=解析番茄自定义字体，还原加密字符|NR=不含爬虫逻辑|E=FanqieFontDecoder|X=internal|A=解码器|D=fontTools,httpx|S=net|RD=./README.ai
"""番茄小说字体反爬解码器。

番茄小说使用自定义 CFF 字体（基于 SourceHanSansSC）实现反爬虫：
1. 服务端 API 返回加密字符（PUA/埃及象形文字等）
2. 自定义字体的 cmap 将加密码点映射到实际汉字的字形
3. 浏览器加载字体后，用户看到的是正确的汉字

本模块通过对比自定义字体和参考字体（SourceHanSansSC）的字形轮廓，
还原加密码点到实际汉字的映射关系。
"""
from __future__ import annotations

import hashlib
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx
from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

logger = logging.getLogger(__name__)

# 字体缓存目录
FONT_CACHE_DIR = Path(__file__).parent.parent.parent / "storage" / "fonts"
FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# 参考字体文件名和路径（SourceHanSansSC Regular, CFF/OTF 格式）
REF_FONT_FILENAME = "SourceHanSansSC-Regular.otf"
REF_FONT_PATH = FONT_CACHE_DIR / REF_FONT_FILENAME

# 多个下载源（按优先级排序，jsDelivr 国内速度快）
REF_FONT_URLS = [
    # jsDelivr CDN（国内可访问，推荐）
    (
        "https://cdn.jsdelivr.net/gh/adobe-fonts/source-han-sans@2.004R/"
        f"OTF/SimplifiedChinese/{REF_FONT_FILENAME}"
    ),
    # GitHub releases（可能较慢）
    (
        "https://github.com/adobe-fonts/source-han-sans/"
        f"releases/download/2.004R/{REF_FONT_FILENAME}"
    ),
    # GitHub raw（备用）
    (
        "https://raw.githubusercontent.com/adobe-fonts/source-han-sans/"
        f"release/OTF/SimplifiedChinese/{REF_FONT_FILENAME}"
    ),
]

# 番茄使用的加密字符范围（不限于 PUA，还使用了其他罕见 Unicode 块）
ENCRYPTED_RANGES = [
    (0xE000, 0xF8FF),      # BMP 私用区
    (0x13000, 0x1342F),    # Egyptian Hieroglyphs
    (0x14400, 0x14646),    # Anatolian Hieroglyphs
    (0x1B000, 0x1B0FF),    # Kana Supplement
    (0x20000, 0x2A6DF),    # CJK Unified Ideographs Extension B（排除正常汉字）
    (0xF0000, 0xFFFFD),    # Supplementary PUA-A
    (0x100000, 0x10FFFD),  # Supplementary PUA-B
]

# 正常 CJK 汉字范围（这些不算加密字符）
NORMAL_CJK_RANGES = [
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0x2F00, 0x2FDF),    # Kangxi Radicals
]


def is_likely_encrypted(char: str) -> bool:
    """检查字符是否可能来自字体反爬加密。

    排除正常 CJK 字符，只检测罕见 Unicode 区域的字符。
    """
    code = ord(char)

    # 先检查是否在正常 CJK 范围内
    for start, end in NORMAL_CJK_RANGES:
        if start <= code <= end:
            return False

    # 再检查是否在加密范围内
    for start, end in ENCRYPTED_RANGES:
        if start <= code <= end:
            return True

    return False


def _compute_glyph_hash(glyph_set, glyph_name: str) -> Optional[str]:
    """使用 RecordingPen 计算字形的轮廓哈希。

    RecordingPen 记录所有绘制命令（moveTo/lineTo/curveTo），
    对于同一个源字体的相同字形，绘制命令序列完全一致。
    """
    try:
        pen = RecordingPen()
        glyph_set[glyph_name].draw(pen)
        if not pen.value:
            return None
        return hashlib.md5(str(pen.value).encode("utf-8")).hexdigest()
    except Exception:
        return None


class FanqieFontDecoder:
    """番茄小说字体反爬解码器。

    通过对比自定义字体和参考 SourceHanSansSC 字体的字形容器，
    还原加密字符到实际汉字的映射关系。
    """

    def __init__(self):
        self._mapping: dict[int, str] = {}  # encrypted_codepoint -> real_char
        self._ref_font: Optional[TTFont] = None

    @property
    def mapping(self) -> dict[int, str]:
        """当前映射表（只读副本）。"""
        return self._mapping.copy()

    @property
    def has_mapping(self) -> bool:
        """是否已建立映射。"""
        return len(self._mapping) > 0

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def ensure_reference_font(self) -> bool:
        """确保参考字体可用（同步版本，供 Playwright 调用）。

        如果本地缓存不存在则下载。返回是否成功。
        """
        if self._ref_font is not None:
            return True

        # 尝试从本地缓存加载
        if REF_FONT_PATH.exists() and REF_FONT_PATH.stat().st_size > 1_000_000:
            try:
                self._ref_font = TTFont(str(REF_FONT_PATH))
                logger.info("从缓存加载参考字体: %s (%d glyphs)",
                            REF_FONT_PATH,
                            len(self._ref_font.getGlyphOrder()))
                return True
            except Exception as e:
                logger.warning("缓存字体损坏，重新下载: %s", e)
                REF_FONT_PATH.unlink(missing_ok=True)

        # 下载
        return self._download_reference_font()

    async def ensure_reference_font_async(self) -> bool:
        """确保参考字体可用（异步版本）。"""
        if self._ref_font is not None:
            return True

        if REF_FONT_PATH.exists() and REF_FONT_PATH.stat().st_size > 1_000_000:
            try:
                self._ref_font = TTFont(str(REF_FONT_PATH))
                logger.info("从缓存加载参考字体: %s", REF_FONT_PATH)
                return True
            except Exception:
                REF_FONT_PATH.unlink(missing_ok=True)

        return await self._download_reference_font_async()

    def build_mapping(self, font_data: bytes) -> dict[int, str]:
        """从自定义字体数据构建字符映射（同步方法）。

        Args:
            font_data: 自定义字体文件的原始字节（woff2/woff/otf 均可）

        Returns:
            加密码点 -> 实际汉字 的映射字典
        """
        try:
            custom_font = TTFont(BytesIO(font_data))
        except Exception as e:
            logger.error("无法解析自定义字体: %s", e)
            return {}

        logger.info(
            "自定义字体: %d glyphs, tables=%s",
            len(custom_font.getGlyphOrder()),
            list(custom_font.keys()),
        )

        mapping: dict[int, str] = {}

        # 方法 1: 从 CFF charset 提取（如果字形名包含 uniXXXX 信息）
        mapping = self._extract_cff_charset(custom_font)
        if len(mapping) >= 50:
            logger.info("CFF charset 提取成功: %d 个映射", len(mapping))
            self._mapping = mapping
            custom_font.close()
            return mapping

        logger.debug("CFF charset 无法提取有效映射，尝试字形对比")

        # 方法 2: 与参考字体对比字形轮廓
        if self._ref_font is not None:
            mapping = self._compare_glyph_outlines(custom_font, self._ref_font)
            if len(mapping) >= 10:
                logger.info("字形对比成功: %d 个映射", len(mapping))
                self._mapping = mapping
                custom_font.close()
                return mapping

        custom_font.close()
        logger.info("无法构建字体映射，等待上层回退到详情页明文补全")
        return {}

    def decode_text(self, text: str) -> str:
        """使用已建立的映射解码加密文本。

        未映射的加密字符会被替换为 □。
        """
        if not text:
            return text

        if not self._mapping:
            # 无映射时，仅替换明确的加密字符为 □
            return "".join(
                "□" if is_likely_encrypted(c) else c for c in text
            )

        result: list[str] = []
        for char in text:
            code = ord(char)
            if code in self._mapping:
                result.append(self._mapping[code])
            elif is_likely_encrypted(char):
                result.append("□")
            else:
                result.append(char)
        return "".join(result)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _extract_cff_charset(self, font: TTFont) -> dict[int, str]:
        """尝试从 CFF charset/String INDEX 提取映射。

        如果字形名包含 uniXXXX 格式，可以直接提取 Unicode 码点。
        """
        if "CFF " not in font:
            return {}

        try:
            cff = font["CFF "].cff
            top_key = list(cff.keys())[0]
            top_dict = cff[top_key]

            if not hasattr(top_dict, "charset") or not top_dict.charset:
                return {}

            charset = top_dict.charset

            strings = None
            if hasattr(top_dict, "Strings") and top_dict.Strings:
                strings = list(top_dict.Strings)

            best_cmap = font["cmap"].getBestCmap()
            if not best_cmap:
                return {}

            glyph_order = font.getGlyphOrder()
            mapping: dict[int, str] = {}

            for codepoint, glyph_name in best_cmap.items():
                if glyph_name not in glyph_order:
                    continue
                glyph_idx = glyph_order.index(glyph_name)
                if glyph_idx >= len(charset):
                    continue

                sid = charset[glyph_idx]
                glyph_string = None
                if sid >= 391 and strings and (sid - 391) < len(strings):
                    glyph_string = strings[sid - 391]

                if not glyph_string or not isinstance(glyph_string, str):
                    continue

                real_cp = None
                if glyph_string.startswith("uni") and len(glyph_string) == 7:
                    try:
                        real_cp = int(glyph_string[3:], 16)
                    except ValueError:
                        pass
                elif glyph_string.startswith("u") and 5 <= len(glyph_string) <= 6:
                    try:
                        real_cp = int(glyph_string[1:], 16)
                    except ValueError:
                        pass

                if real_cp is not None:
                    try:
                        mapping[codepoint] = chr(real_cp)
                    except (ValueError, OverflowError):
                        pass

            return mapping
        except Exception as e:
            logger.debug("CFF charset 提取失败: %s", e)
            return {}

    def _compare_glyph_outlines(
        self, custom_font: TTFont, ref_font: TTFont
    ) -> dict[int, str]:
        """对比自定义字体和参考字形的轮廓哈希。

        由于自定义字体基于 SourceHanSansSC，相同字形的轮廓
        （RecordingPen 记录的绘制命令）应完全一致。
        """
        custom_cmap = custom_font["cmap"].getBestCmap()
        ref_cmap = ref_font["cmap"].getBestCmap()

        if not custom_cmap or not ref_cmap:
            return {}

        # 构建参考字体: outline_hash -> standard_codepoint
        logger.info("构建参考字体哈希表（%d glyphs）...", len(ref_cmap))
        ref_glyph_set = ref_font.getGlyphSet()
        ref_hashes: dict[str, int] = {}

        for codepoint, glyph_name in ref_cmap.items():
            h = _compute_glyph_hash(ref_glyph_set, glyph_name)
            if h:
                ref_hashes[h] = codepoint

        logger.info("参考哈希表: %d entries", len(ref_hashes))

        # 匹配自定义字体的字形
        mapping: dict[int, str] = {}
        custom_glyph_set = custom_font.getGlyphSet()
        matched = 0

        for encrypted_cp, glyph_name in custom_cmap.items():
            h = _compute_glyph_hash(custom_glyph_set, glyph_name)
            if h and h in ref_hashes:
                real_cp = ref_hashes[h]
                try:
                    mapping[encrypted_cp] = chr(real_cp)
                    matched += 1
                except (ValueError, OverflowError):
                    pass

        logger.info("匹配结果: %d / %d", matched, len(custom_cmap))
        return mapping

    # ------------------------------------------------------------------
    # 参考字体下载
    # ------------------------------------------------------------------

    def _download_reference_font(self) -> bool:
        """同步下载参考字体。"""
        for url in REF_FONT_URLS:
            try:
                logger.info("下载参考字体: %s", url)
                with httpx.Client(
                    timeout=180.0, follow_redirects=True
                ) as client:
                    resp = client.get(
                        url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36"
                            )
                        },
                    )
                    resp.raise_for_status()
                    data = resp.content

                if len(data) < 1_000_000:
                    logger.warning("下载字体过小 (%d bytes)，跳过", len(data))
                    continue

                REF_FONT_PATH.write_bytes(data)
                self._ref_font = TTFont(BytesIO(data))
                logger.info(
                    "参考字体下载成功: %d bytes, %d glyphs",
                    len(data),
                    len(self._ref_font.getGlyphOrder()),
                )
                return True
            except Exception as e:
                logger.debug("下载失败 %s: %s", url, e)

        logger.error("参考字体下载失败")
        return False

    async def _download_reference_font_async(self) -> bool:
        """异步下载参考字体。"""
        for url in REF_FONT_URLS:
            try:
                logger.info("下载参考字体: %s", url)
                async with httpx.AsyncClient(
                    timeout=180.0, follow_redirects=True
                ) as client:
                    resp = await client.get(
                        url,
                        headers={
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36"
                            )
                        },
                    )
                    resp.raise_for_status()
                    data = resp.content

                if len(data) < 1_000_000:
                    continue

                REF_FONT_PATH.write_bytes(data)
                self._ref_font = TTFont(BytesIO(data))
                logger.info("参考字体下载成功: %d bytes", len(data))
                return True
            except Exception as e:
                logger.debug("下载失败 %s: %s", url, e)

        logger.error("参考字体下载失败")
        return False
