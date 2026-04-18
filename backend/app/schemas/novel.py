# AIMETA P=小说模式_小说和章节请求响应|R=小说结构_章节结构|NR=不含业务逻辑|E=NovelSchema_ChapterSchema|X=internal|A=Pydantic模式|D=pydantic|S=none|RD=./README.ai
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChoiceOption(BaseModel):
    """前端选择项描述，用于动态 UI 控件。"""

    id: str
    label: str


class UIControl(BaseModel):
    """描述前端应渲染的组件类型与配置。"""

    type: str = Field(..., description="控件类型，如 single_choice/text_input")
    options: Optional[List[ChoiceOption]] = Field(default=None, description="可选项列表")
    placeholder: Optional[str] = Field(default=None, description="输入提示文案")


class ConverseResponse(BaseModel):
    """概念对话接口的统一返回体。"""

    ai_message: str
    ui_control: UIControl
    conversation_state: Dict[str, Any]
    is_complete: bool = False
    ready_for_blueprint: Optional[bool] = None


class ConverseRequest(BaseModel):
    """概念对话接口的请求体。"""

    user_input: Dict[str, Any]
    conversation_state: Dict[str, Any]


class ChapterGenerationStatus(str, Enum):
    NOT_GENERATED = "not_generated"
    GENERATING = "generating"
    EVALUATING = "evaluating"
    SELECTING = "selecting"
    FAILED = "failed"
    EVALUATION_FAILED = "evaluation_failed"
    WAITING_FOR_CONFIRM = "waiting_for_confirm"
    SUCCESSFUL = "successful"


class ChapterOutline(BaseModel):
    chapter_number: int
    title: str
    summary: str
    foreshadowing: Optional[Dict[str, List[str]]] = None
    mark_tag: Optional[str] = None


class Chapter(ChapterOutline):
    real_summary: Optional[str] = None
    content: Optional[str] = None
    versions: Optional[List[str]] = None
    evaluation: Optional[str] = None
    generation_status: ChapterGenerationStatus = ChapterGenerationStatus.NOT_GENERATED


class ChapterRuntimeStatus(BaseModel):
    chapter_number: int
    generation_status: ChapterGenerationStatus = ChapterGenerationStatus.NOT_GENERATED
    word_count: int = 0
    updated_at: Optional[str] = None
    has_content: bool = False
    versions_count: int = 0
    has_evaluation: bool = False
    selected_version_id: Optional[int] = None


class WritingStyleLibrary(BaseModel):
    outline_text: str = Field(default="", description="大纲写作风格文本")
    chapter_text: str = Field(default="", description="章节写作风格文本")


class UpdateWritingStyleLibraryRequest(BaseModel):
    outline_text: str = Field(default="", description="大纲风格文本（按行分隔）")
    chapter_text: str = Field(default="", description="章节风格文本（按行分隔）")


class Relationship(BaseModel):
    character_from: str
    character_to: str
    description: str


class Blueprint(BaseModel):
    title: str
    target_audience: str = ""
    genre: str = ""
    style: str = ""
    tone: str = ""
    one_sentence_summary: str = ""
    full_synopsis: str = ""
    world_setting: Dict[str, Any] = {}
    characters: List[Dict[str, Any]] = []
    relationships: List[Relationship] = []
    chapter_outline: List[ChapterOutline] = []
    total_chapters: int = Field(default=0, description="小说预计总章节数，用于大纲续写时保持故事节奏")

    class Config:
        from_attributes = True


class NovelProject(BaseModel):
    id: str
    user_id: int
    title: str
    initial_prompt: str
    conversation_history: List[Dict[str, Any]] = []
    blueprint: Optional[Blueprint] = None
    chapters: List[Chapter] = []

    class Config:
        from_attributes = True


class NovelProjectSummary(BaseModel):
    id: str
    title: str
    genre: str
    last_edited: str
    completed_chapters: int
    total_chapters: int


class BlueprintGenerationResponse(BaseModel):
    blueprint: Blueprint
    ai_message: str


class ChapterGenerationResponse(BaseModel):
    ai_message: str
    chapter_versions: List[Dict[str, Any]]


class NovelSectionType(str, Enum):
    OVERVIEW = "overview"
    WORLD_SETTING = "world_setting"
    CHARACTERS = "characters"
    RELATIONSHIPS = "relationships"
    CHAPTER_OUTLINE = "chapter_outline"
    CHAPTERS = "chapters"


class NovelSectionResponse(BaseModel):
    section: NovelSectionType
    data: Dict[str, Any]


class GenerateChapterRequest(BaseModel):
    chapter_number: int
    writing_notes: Optional[str] = Field(default=None, description="章节额外写作指令")


class FlowConfig(BaseModel):
    preset: str = Field(default="basic", description="basic|enhanced|ultimate|custom")
    versions: Optional[int] = Field(default=None, description="生成版本数量")
    enable_preview: Optional[bool] = Field(default=None, description="是否启用预演生成")
    enable_optimizer: Optional[bool] = Field(default=None, description="是否启用优化器")
    enable_consistency: Optional[bool] = Field(default=None, description="是否启用一致性检查")
    enable_enrichment: Optional[bool] = Field(default=None, description="是否启用字数扩写")
    async_finalize: Optional[bool] = Field(default=None, description="是否异步定稿")
    enable_rag: Optional[bool] = Field(default=None, description="是否启用 RAG")
    rag_mode: Optional[str] = Field(default=None, description="simple|two_stage")


class AdvancedGenerateRequest(BaseModel):
    project_id: str
    chapter_number: int
    writing_notes: Optional[str] = Field(default=None, description="章节额外写作指令")
    flow_config: FlowConfig = Field(default_factory=FlowConfig)


class AdvancedGenerateVariant(BaseModel):
    index: int
    version_id: int
    content: str
    metadata: Optional[Dict[str, Any]] = None


class AdvancedGenerateResponse(BaseModel):
    project_id: str
    chapter_number: int
    preset: str
    best_version_index: int
    variants: List[AdvancedGenerateVariant]
    review_summaries: Dict[str, Any] = Field(default_factory=dict)
    debug_metadata: Optional[Dict[str, Any]] = None


class FinalizeChapterRequest(BaseModel):
    project_id: str
    selected_version_id: int
    skip_vector_update: Optional[bool] = Field(default=False, description="是否跳过向量库更新")


class FinalizeChapterResponse(BaseModel):
    project_id: str
    chapter_number: int
    selected_version_id: int
    result: Dict[str, Any]


class SelectVersionRequest(BaseModel):
    chapter_number: int
    version_index: int


class EvaluateChapterRequest(BaseModel):
    chapter_number: int


class UpdateChapterOutlineRequest(BaseModel):
    chapter_number: int
    title: str
    summary: str
    ai_message: Optional[str] = Field(default=None, description="AI对话中给出的建议，将提炼为规则追加到提示词文件中")


class UpdateChapterMarkRequest(BaseModel):
    chapter_number: int
    mark_tag: str = Field(
        ...,
        description="章节标记：none|todo_fix|todo_check|todo_polish",
    )


class DeleteChapterRequest(BaseModel):
    chapter_numbers: List[int]


class GenerateOutlineRequest(BaseModel):
    start_chapter: int
    num_chapters: int
    total_chapters: Optional[int] = Field(default=None, description="小说预计总章节数，用于保持故事节奏")
    user_hint: Optional[str] = Field(default=None, description="用户提示文字，用于指导大纲生成方向")


class BlueprintPatch(BaseModel):
    title: Optional[str] = None
    target_audience: Optional[str] = None
    genre: Optional[str] = None
    style: Optional[str] = None
    tone: Optional[str] = None
    one_sentence_summary: Optional[str] = None
    full_synopsis: Optional[str] = None
    total_chapters: Optional[int] = None
    world_setting: Optional[Dict[str, Any]] = None
    characters: Optional[List[Dict[str, Any]]] = None
    relationships: Optional[List[Relationship]] = None
    chapter_outline: Optional[List[ChapterOutline]] = None


class EditChapterRequest(BaseModel):
    chapter_number: int
    content: str


class BlueprintSettingImpactAnalysis(BaseModel):
    impact_level: str = "low"
    summary: str = ""
    impacted_sections: List[str] = Field(default_factory=list)
    impacted_chapters: List[int] = Field(default_factory=list)
    recommended_actions: List[str] = Field(default_factory=list)


class BlueprintSettingChatMessage(BaseModel):
    id: int
    role: str
    message: str
    phase: str = "post_blueprint_setting"
    created_at: Optional[str] = None
    applied_to_blueprint: bool = False
    proposed_patch: Optional[BlueprintPatch] = None
    impact_analysis: Optional[BlueprintSettingImpactAnalysis] = None
    source: str = "blueprint_setting"


class BlueprintSettingHistoryResponse(BaseModel):
    history: List[BlueprintSettingChatMessage] = Field(default_factory=list)


class BlueprintSettingConverseRequest(BaseModel):
    user_message: str


class BlueprintSettingConverseResponse(BaseModel):
    ai_message: str
    history: List[BlueprintSettingChatMessage] = Field(default_factory=list)
    proposed_patch: Optional[BlueprintPatch] = None
    impact_analysis: Optional[BlueprintSettingImpactAnalysis] = None
    need_confirm: bool = False
    latest_message_id: Optional[int] = None


class ApplyBlueprintSettingPatchRequest(BaseModel):
    patch: BlueprintPatch
    assistant_message_id: Optional[int] = None


class ChapterOutlineConverseRequest(BaseModel):
    """章节大纲对话修改请求"""
    chapter_number: int
    user_message: str
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)


class ProposedOutline(BaseModel):
    """建议的大纲修改"""
    title: str
    summary: str


class OutlineEntityItem(BaseModel):
    name: str
    description: Optional[str] = ""
    first_appear_chapter: Optional[int] = None


class OutlineForeshadowingItem(BaseModel):
    content: str
    target_reveal_chapter: Optional[int] = None
    planted_chapter: Optional[int] = None
    importance: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    foreshadowing_id: Optional[int] = None


class ChapterOutlineConverseContextResponse(BaseModel):
    chapter_number: int
    title: str
    summary: str
    narrative_phase: Optional[str] = None
    story_progress: Optional[str] = None
    emotion_hook: Optional[str] = None
    new_characters: List[OutlineEntityItem] = Field(default_factory=list)
    new_locations: List[OutlineEntityItem] = Field(default_factory=list)
    new_factions: List[OutlineEntityItem] = Field(default_factory=list)
    foreshadowing_plants: List[OutlineForeshadowingItem] = Field(default_factory=list)
    foreshadowing_payoffs: List[OutlineForeshadowingItem] = Field(default_factory=list)


class ChapterOutlineConverseResponse(BaseModel):
    """章节大纲对话修改响应"""
    ai_message: str
    proposed_outline: Optional[ProposedOutline] = None
    new_characters: List[OutlineEntityItem] = Field(default_factory=list)
    new_locations: List[OutlineEntityItem] = Field(default_factory=list)
    new_factions: List[OutlineEntityItem] = Field(default_factory=list)
    foreshadowing_plants: List[OutlineForeshadowingItem] = Field(default_factory=list)
    foreshadowing_payoffs: List[OutlineForeshadowingItem] = Field(default_factory=list)


class ApplyChapterOutlineConverseRequest(BaseModel):
    chapter_number: int
    title: str
    summary: str
    ai_message: Optional[str] = Field(default=None, description="AI 对话建议文本，用于提炼规则")
    new_characters: List[Dict[str, Any]] = Field(default_factory=list)
    new_locations: List[Dict[str, Any]] = Field(default_factory=list)
    new_factions: List[Dict[str, Any]] = Field(default_factory=list)
    foreshadowing_plants: List[Dict[str, Any]] = Field(default_factory=list)
    foreshadowing_payoffs: List[Dict[str, Any]] = Field(default_factory=list)


# ========== 大纲预览相关 ==========

class OutlineChapterPreview(BaseModel):
    """单章大纲预览"""
    chapter_number: int
    title: str
    summary: str
    narrative_phase: Optional[str] = None
    story_progress: Optional[str] = None
    foreshadowing: Optional[Dict[str, List[str]]] = None
    emotion_hook: Optional[str] = None


class OutlinePreviewRequest(BaseModel):
    """大纲预览请求 - 只生成预览，不保存"""
    start_chapter: int
    num_chapters: int
    total_chapters: Optional[int] = Field(default=None, description="小说预计总章节数")
    user_hint: Optional[str] = Field(default=None, description="用户提示文字")


class OutlinePreviewResponse(BaseModel):
    """大纲预览响应 - 包含所有生成的内容供用户确认"""
    chapters: List[OutlineChapterPreview]
    new_characters: List[Dict[str, Any]] = Field(default_factory=list)
    new_relationships: List[Dict[str, Any]] = Field(default_factory=list)
    new_locations: List[Dict[str, Any]] = Field(default_factory=list)
    new_factions: List[Dict[str, Any]] = Field(default_factory=list)
    foreshadowing_plants: List[Dict[str, Any]] = Field(default_factory=list, description="待埋设的伏笔 [{chapter_number, content}]")
    foreshadowing_payoffs: List[Dict[str, Any]] = Field(default_factory=list, description="待回收的伏笔 [{chapter_number, content}]")
    ai_message: Optional[str] = None


class OutlineConfirmRequest(BaseModel):
    """大纲确认保存请求 - 用户确认后保存"""
    start_chapter: int
    preview_data: Dict[str, Any] = Field(..., description="预览时的完整数据，直接传回")
