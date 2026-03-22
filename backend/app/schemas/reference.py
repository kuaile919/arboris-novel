# AIMETA P=参考文档Schema_上传与列表响应|R=请求响应定义|NR=不含业务逻辑|E=ReferenceDocumentItem|X=internal|A=Pydantic模型|D=pydantic|S=none|RD=./README.ai
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ReferenceDocumentItem(BaseModel):
    id: int
    project_id: str
    filename: str
    title: str
    file_type: str
    file_size: int
    char_count: int
    chunk_count: int
    status: str
    error_message: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ReferenceUploadResponse(BaseModel):
    document: ReferenceDocumentItem
    message: str
