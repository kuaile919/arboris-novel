from backend.app.services.ima_kb_service import (
    IMAServiceError,
    IMAValidationError,
    build_duplicate_filename,
    detect_supported_file,
    is_folder_item,
    normalize_folder_id,
    normalize_ima_response,
    normalize_knowledge_base_item,
    normalize_knowledge_item,
    validate_importable_url,
)


def test_normalize_ima_response_accepts_code_and_retcode() -> None:
    assert normalize_ima_response({"code": 0, "msg": "success", "data": {"ok": True}}) == {"ok": True}
    assert normalize_ima_response({"retcode": 0, "errmsg": "success", "data": {"ok": True}}) == {"ok": True}


def test_normalize_ima_response_raises_on_error() -> None:
    try:
        normalize_ima_response({"code": 110030, "msg": "无权限"})
    except IMAServiceError as exc:
        assert exc.message == "无权限"
        assert exc.status_code == 502
    else:  # pragma: no cover
        raise AssertionError("expected IMAServiceError")


def test_normalize_knowledge_base_item_supports_kb_fields() -> None:
    item = normalize_knowledge_base_item(
        {
            "kb_id": "kb-1",
            "kb_name": "个人知识库",
            "member_count": "3",
            "content_count": "22",
        },
        {"description": "测试描述", "recommended_questions": ["Q1"]},
    )
    assert item["id"] == "kb-1"
    assert item["name"] == "个人知识库"
    assert item["description"] == "测试描述"
    assert item["member_count"] == 3
    assert item["recommended_questions"] == ["Q1"]


def test_normalize_knowledge_item_recognizes_folder() -> None:
    folder = normalize_knowledge_item({"media_id": "folder_123", "title": "文档", "media_type": 99})
    file_item = normalize_knowledge_item({"media_id": "word_123", "title": "文件.docx", "media_type": 3})
    assert folder["is_folder"] is True
    assert file_item["is_folder"] is False
    assert is_folder_item({"media_id": "folder_999"}) is True


def test_normalize_folder_id_omits_root_like_values() -> None:
    assert normalize_folder_id(None) is None
    assert normalize_folder_id("") is None
    assert normalize_folder_id("001a0d998b801ace") is None
    assert normalize_folder_id("folder_123") == "folder_123"


def test_detect_supported_file_validates_type_and_size() -> None:
    spec = detect_supported_file(filename="outline.md", file_size=1024, content_type="text/markdown")
    assert spec.media_type == 7

    try:
        detect_supported_file(filename="audio.mp3", file_size=1024)
    except IMAValidationError as exc:
        assert "音频" in exc.message
    else:  # pragma: no cover
        raise AssertionError("expected IMAValidationError")

    try:
        detect_supported_file(filename="huge.xlsx", file_size=11 * 1024 * 1024)
    except IMAValidationError as exc:
        assert "最大支持 10MB" in exc.message
    else:  # pragma: no cover
        raise AssertionError("expected IMAValidationError")


def test_validate_importable_url_rejects_file_and_video_urls() -> None:
    assert validate_importable_url("https://example.com/article") == "https://example.com/article"

    for url in [
        "file:///tmp/test.html",
        "https://www.bilibili.com/video/BV1xx411c7mD",
        "https://www.youtube.com/watch?v=abc",
        "https://example.com/report.pdf",
    ]:
        try:
            validate_importable_url(url)
        except IMAValidationError:
            pass
        else:  # pragma: no cover
            raise AssertionError(f"expected IMAValidationError for {url}")


def test_build_duplicate_filename_appends_timestamp() -> None:
    renamed = build_duplicate_filename("report.pdf")
    assert renamed.startswith("report_")
    assert renamed.endswith(".pdf")
