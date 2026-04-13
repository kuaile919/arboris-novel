from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class IMAKnowledgeBaseSummary(BaseModel):
    id: str
    name: str
    cover_url: Optional[str] = None
    description: Optional[str] = None
    recommended_questions: List[str] = Field(default_factory=list)
    member_count: Optional[int] = None
    content_count: Optional[int] = None
    creator: Optional[str] = None
    role_type: Optional[str] = None


class IMAKnowledgeBaseCollectionResponse(BaseModel):
    items: List[IMAKnowledgeBaseSummary]
    next_cursor: str = ""
    is_end: bool = True


class IMAKnowledgePathEntry(BaseModel):
    id: str
    name: str
    is_root: bool = False


class IMAKnowledgeItem(BaseModel):
    id: str
    title: str
    is_folder: bool
    media_type: int
    parent_folder_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    highlight_content: Optional[str] = None


class IMAKnowledgeItemListResponse(BaseModel):
    items: List[IMAKnowledgeItem]
    current_path: List[IMAKnowledgePathEntry]
    next_cursor: str = ""
    is_end: bool = True


class IMAFallbackWebResult(BaseModel):
    title: str
    link: str
    snippet: Optional[str] = None
    date: Optional[str] = None


class IMASearchResponse(BaseModel):
    items: List[IMAKnowledgeItem]
    next_cursor: str = ""
    is_end: bool = True
    fallback_used: bool = False
    fallback_provider: Optional[str] = None
    fallback_message: Optional[str] = None
    fallback_results: List[IMAFallbackWebResult] = Field(default_factory=list)


class IMAKnowledgeBaseDetailResponse(BaseModel):
    knowledge_base: IMAKnowledgeBaseSummary


class IMAUrlImportRequest(BaseModel):
    urls: List[str]
    folder_id: Optional[str] = None

    @field_validator("urls")
    @classmethod
    def validate_urls(cls, value: List[str]) -> List[str]:
        cleaned = [item.strip() for item in value if item and item.strip()]
        if not cleaned:
            raise ValueError("至少提供 1 个 URL")
        if len(cleaned) > 10:
            raise ValueError("单次最多导入 10 个 URL")
        return cleaned


class IMAImportedUrlResult(BaseModel):
    url: str
    success: bool
    media_id: Optional[str] = None
    error: Optional[str] = None


class IMAUrlImportResponse(BaseModel):
    message: str
    success_count: int
    failure_count: int
    results: List[IMAImportedUrlResult]


class IMAFileUploadResponse(BaseModel):
    message: str
    knowledge_base: IMAKnowledgeBaseSummary
    item: IMAKnowledgeItem
    duplicate_handling: Literal["original", "renamed"] = "original"
    original_name: str
    final_name: str
