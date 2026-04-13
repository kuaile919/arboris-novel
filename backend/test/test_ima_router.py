from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.app.api.routers import ima as ima_router
from backend.app.core.dependencies import get_current_user
from backend.app.db.session import get_session
from backend.app.schemas.user import UserInDB
from backend.app.services.ima_kb_service import IMADuplicateNameError


def _build_app(monkeypatch, service_cls, *, allow_access: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(ima_router.router)

    async def override_current_user() -> UserInDB:
        return UserInDB(
            id=1,
            username="tester",
            email=None,
            is_admin=False,
            is_active=True,
            must_change_password=False,
            hashed_password="hashed",
        )

    async def override_session():
        return SimpleNamespace()

    async def fake_ensure_owner(self, project_id: str, user_id: int):
        if not allow_access:
            raise HTTPException(status_code=403, detail="无权访问该项目")
        return SimpleNamespace(id=project_id, user_id=user_id)

    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(ima_router, "IMAKnowledgeBaseService", service_cls)
    monkeypatch.setattr(ima_router.NovelService, "ensure_project_owner", fake_ensure_owner)
    return TestClient(app)


def test_ima_router_requires_auth() -> None:
    app = FastAPI()
    app.include_router(ima_router.router)
    client = TestClient(app)

    response = client.get("/api/projects/project-1/ima/knowledge-bases/addable")
    assert response.status_code == 401


def test_ima_router_checks_project_permission(monkeypatch) -> None:
    class FakeService:
        async def list_addable_knowledge_bases(self, *, cursor: str = "", limit: int = 20):
            return {"items": [], "next_cursor": "", "is_end": True}

    client = _build_app(monkeypatch, FakeService, allow_access=False)
    response = client.get("/api/projects/project-1/ima/knowledge-bases/addable")
    assert response.status_code == 403
    assert response.json()["detail"] == "无权访问该项目"


def test_ima_router_duplicate_upload_returns_409(monkeypatch) -> None:
    class FakeService:
        async def upload_file(self, knowledge_base_id: str, **kwargs):
            raise IMADuplicateNameError(original_name="report.md", suggested_name="report_20260407120000.md")

    client = _build_app(monkeypatch, FakeService)
    response = client.post(
        "/api/projects/project-1/ima/knowledge-bases/kb-1/files/upload",
        files={"file": ("report.md", b"hello", "text/markdown")},
    )
    payload = response.json()
    assert response.status_code == 409
    assert payload["error_code"] == "duplicate_name"
    assert payload["duplicate_name"] == "report.md"
    assert payload["suggested_name"] == "report_20260407120000.md"


def test_ima_router_import_urls_success(monkeypatch) -> None:
    class FakeService:
        async def import_urls(self, knowledge_base_id: str, *, urls, folder_id=None):
            assert knowledge_base_id == "kb-1"
            assert urls == ["https://example.com/article"]
            assert folder_id is None
            return {
                "message": "已向「临时」导入 1 个 URL",
                "success_count": 1,
                "failure_count": 0,
                "results": [
                    {
                        "url": "https://example.com/article",
                        "success": True,
                        "media_id": "web_1",
                        "error": None,
                    }
                ],
            }

    client = _build_app(monkeypatch, FakeService)
    response = client.post(
        "/api/projects/project-1/ima/knowledge-bases/kb-1/urls/import",
        json={"urls": ["https://example.com/article"]},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["success_count"] == 1
    assert payload["results"][0]["success"] is True


def test_ima_router_search_includes_fallback_results(monkeypatch) -> None:
    class FakeService:
        async def search_items(self, knowledge_base_id: str, query: str, *, cursor: str = ""):
            return {
                "items": [],
                "next_cursor": "",
                "is_end": True,
                "fallback_used": True,
                "fallback_provider": "MiniMax MCP",
                "fallback_message": "IMA 未命中，已切换到 MiniMax 联网搜索结果",
                "fallback_results": [
                    {
                        "title": "落云宗 - 相关网页",
                        "link": "https://example.com/luoyunzong",
                        "snippet": "示例摘要",
                        "date": "2026-04-08",
                    }
                ],
            }

    client = _build_app(monkeypatch, FakeService)
    response = client.get(
        "/api/projects/project-1/ima/knowledge-bases/kb-1/search",
        params={"query": "落云宗"},
    )
    payload = response.json()
    assert response.status_code == 200
    assert payload["fallback_used"] is True
    assert payload["fallback_provider"] == "MiniMax MCP"
    assert payload["fallback_results"][0]["title"] == "落云宗 - 相关网页"
