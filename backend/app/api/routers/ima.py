from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ...core.dependencies import get_current_user
from ...db.session import get_session
from ...schemas.ima import (
    IMAFileUploadResponse,
    IMAKnowledgeBaseCollectionResponse,
    IMAKnowledgeBaseDetailResponse,
    IMAKnowledgeItemListResponse,
    IMASearchResponse,
    IMAUrlImportRequest,
    IMAUrlImportResponse,
)
from ...schemas.user import UserInDB
from ...services.ima_kb_service import IMADuplicateNameError, IMAKnowledgeBaseService, IMAServiceError
from ...services.novel_service import NovelService

router = APIRouter(prefix="/api/projects/{project_id}/ima", tags=["IMA"])


async def _ensure_project_access(project_id: str, session: AsyncSession, current_user: UserInDB) -> None:
    novel_service = NovelService(session)
    await novel_service.ensure_project_owner(project_id, current_user.id)


@router.get("/knowledge-bases/addable", response_model=IMAKnowledgeBaseCollectionResponse)
async def list_addable_knowledge_bases(
    project_id: str,
    cursor: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAKnowledgeBaseCollectionResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        data = await service.list_addable_knowledge_bases(cursor=cursor, limit=limit)
        return IMAKnowledgeBaseCollectionResponse.model_validate(data)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/knowledge-bases/search", response_model=IMAKnowledgeBaseCollectionResponse)
async def search_knowledge_bases(
    project_id: str,
    query: str = Query(default=""),
    cursor: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAKnowledgeBaseCollectionResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        data = await service.search_knowledge_bases(query=query, cursor=cursor, limit=limit)
        return IMAKnowledgeBaseCollectionResponse.model_validate(data)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/knowledge-bases/{knowledge_base_id}", response_model=IMAKnowledgeBaseDetailResponse)
async def get_knowledge_base(
    project_id: str,
    knowledge_base_id: str,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAKnowledgeBaseDetailResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        knowledge_base = await service.get_knowledge_base(knowledge_base_id)
        return IMAKnowledgeBaseDetailResponse(knowledge_base=knowledge_base)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/knowledge-bases/{knowledge_base_id}/items", response_model=IMAKnowledgeItemListResponse)
async def list_knowledge_items(
    project_id: str,
    knowledge_base_id: str,
    cursor: str = Query(default=""),
    limit: int = Query(default=20, ge=1, le=50),
    folder_id: Optional[str] = Query(default=None),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAKnowledgeItemListResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        data = await service.list_items(
            knowledge_base_id,
            cursor=cursor,
            limit=limit,
            folder_id=folder_id,
        )
        return IMAKnowledgeItemListResponse.model_validate(data)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.get("/knowledge-bases/{knowledge_base_id}/search", response_model=IMASearchResponse)
async def search_knowledge_items(
    project_id: str,
    knowledge_base_id: str,
    query: str = Query(..., min_length=1),
    cursor: str = Query(default=""),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMASearchResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        data = await service.search_items(knowledge_base_id, query=query, cursor=cursor)
        return IMASearchResponse.model_validate(data)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post(
    "/knowledge-bases/{knowledge_base_id}/files/upload",
    response_model=IMAFileUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_knowledge_file(
    project_id: str,
    knowledge_base_id: str,
    file: UploadFile = File(...),
    folder_id: Optional[str] = Form(default=None),
    on_duplicate: str = Form(default="error"),
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAFileUploadResponse:
    await _ensure_project_access(project_id, session, current_user)
    if on_duplicate not in {"error", "rename"}:
        raise HTTPException(status_code=400, detail="on_duplicate 仅支持 error 或 rename")

    service = IMAKnowledgeBaseService()
    try:
        data = await service.upload_file(
            knowledge_base_id,
            file=file,
            folder_id=folder_id,
            on_duplicate=on_duplicate,
        )
        return IMAFileUploadResponse.model_validate(data)
    except IMADuplicateNameError as exc:
        return JSONResponse(
            status_code=409,
            content={
                "detail": exc.message,
                "error_code": "duplicate_name",
                "duplicate_name": exc.original_name,
                "suggested_name": exc.suggested_name,
            },
        )
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    finally:
        await file.close()


@router.post("/knowledge-bases/{knowledge_base_id}/urls/import", response_model=IMAUrlImportResponse)
async def import_urls(
    project_id: str,
    knowledge_base_id: str,
    payload: IMAUrlImportRequest,
    session: AsyncSession = Depends(get_session),
    current_user: UserInDB = Depends(get_current_user),
) -> IMAUrlImportResponse:
    await _ensure_project_access(project_id, session, current_user)
    service = IMAKnowledgeBaseService()
    try:
        data = await service.import_urls(
            knowledge_base_id,
            urls=payload.urls,
            folder_id=payload.folder_id,
        )
        return IMAUrlImportResponse.model_validate(data)
    except IMAServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
