import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.services.trend.analysis_service import TrendAnalysisService


def build_service() -> TrendAnalysisService:
    return TrendAnalysisService.__new__(TrendAnalysisService)


def test_parse_truncated_json_response_extracts_summary():
    service = build_service()
    response = """```json
{
  "summary": "这是一个可读的摘要",
  "genre_distribution": {
    "都市": {"count": 6, "percentage": 33.3}
  },
  "hot_keywords": ["系统", "都市"],
  "creation_suggestions": ["建议一", "建议二"]
"""

    report = service._parse_llm_response("qidian", response)

    assert report["trend_summary"] == "这是一个可读的摘要"
    assert not report["trend_summary"].startswith("```json")
    assert report["ai_full_report"].startswith("```json")


def test_parse_nested_summary_json_extracts_inner_fields():
    service = build_service()
    response = (
        '{"summary":"```json\\n{\\n  \\"summary\\": \\"内层摘要\\",\\n'
        '  \\"hot_keywords\\": [\\"家族修仙\\", \\"种田\\"],\\n'
        '  \\"creation_suggestions\\": [\\"建议聚焦长线成长\\" ]\\n}\\n```"}'
    )

    report = service._parse_llm_response("qidian", response)

    assert report["trend_summary"] == "内层摘要"
    assert report["hot_keywords"] == ["家族修仙", "种田"]
    assert report["creation_suggestions"] == ["建议聚焦长线成长"]


def test_normalize_report_record_repairs_legacy_json_summary():
    service = build_service()
    legacy_report = SimpleNamespace(
        platform="qidian",
        category="hot",
        report_date=datetime.utcnow(),
        genre_distribution=None,
        hot_keywords=[],
        trend_summary='```json\n{"summary":"修复后的摘要","hot_keywords":["系统"]}',
        ai_full_report='```json\n{"summary":"修复后的摘要","hot_keywords":["系统"]}',
        hot_elements=[],
        reader_preferences={},
        opportunities=[],
        creation_suggestions=[],
    )

    normalized = service._normalize_report_record(legacy_report)

    assert normalized["trend_summary"] == "修复后的摘要"
    assert normalized["hot_keywords"] == ["系统"]
