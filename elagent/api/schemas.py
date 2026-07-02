"""
API请求和响应的数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class MentionRequest(BaseModel):
    """指称信息"""
    text: str = Field(..., description="指称文本，如'世锦赛'、'浙江队'")
    start_pos: int = Field(..., description="在原文中的起始位置")
    end_pos: int = Field(..., description="在原文中的结束位置")
    entity_type: Optional[str] = Field(None, description="实体类型: PER/ORG/LOC/EVENT")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "世锦赛",
                "start_pos": 5,
                "end_pos": 8,
                "entity_type": "EVENT"
            }
        }


class LinkRequest(BaseModel):
    """实体链接请求"""
    text: str = Field(..., description="包含指称的完整文本")
    mention: MentionRequest = Field(..., description="待链接的指称信息")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "2024年世界羽毛球锦标赛在哥本哈根举行，世锦赛吸引了众多顶尖选手参赛。",
                "mention": {
                    "text": "世锦赛",
                    "start_pos": 24,
                    "end_pos": 27,
                    "entity_type": "EVENT"
                }
            }
        }


class BatchLinkRequest(BaseModel):
    """批量实体链接请求"""
    items: List[LinkRequest] = Field(..., description="链接请求列表，最多100条")


class EntityResponse(BaseModel):
    """实体信息"""
    id: str = Field(..., description="实体ID，如 'EVENT_0160'")
    standard_name: str = Field(..., description="标准名称，如 '世界羽毛球锦标赛'")
    entity_type: str = Field(..., description="实体类型: PER/ORG/LOC/EVENT")
    aliases: List[str] = Field(default_factory=list, description="别名列表")
    description: str = Field("", description="实体描述")


class LinkResponse(BaseModel):
    """实体链接响应"""
    linked_entity: Optional[EntityResponse] = Field(None, description="链接到的实体")
    is_nil: bool = Field(False, description="True=知识库无对应实体")
    confidence: float = Field(0.0, description="置信度(0~1)")
    nil_reason: str = Field("", description="NIL判定理由")
    trace_id: str = Field("", description="追溯ID，可通过 GET /trace/{id} 查看详情")
    processing_time_ms: float = Field(0.0, description="处理耗时(毫秒)")


class BatchLinkResponse(BaseModel):
    """批量链接响应"""
    results: List[LinkResponse] = Field(..., description="链接结果列表")
    total: int = Field(0, description="总数")
    success_count: int = Field(0, description="成功链接数")
    nil_count: int = Field(0, description="NIL数")


class KBStatsResponse(BaseModel):
    """知识库统计"""
    total_entities: int = Field(0, description="实体总数")
    total_aliases: int = Field(0, description="别名总数")
    entity_types: Dict[str, int] = Field(default_factory=dict, description="各类型实体数")
    loaded: bool = Field(False, description="知识库是否已加载")


class TraceResponse(BaseModel):
    """追溯日志"""
    trace_id: str = Field("", description="追溯ID")
    mention_id: str = Field("", description="指称ID")
    skill_name: str = Field("entity_linking", description="能力名称")
    input_data: Dict = Field(default_factory=dict, description="原始输入")
    output_data: Dict = Field(default_factory=dict, description="最终结果")
    timestamp: str = Field("", description="处理时间")
    duration_ms: float = Field(0.0, description="总耗时(毫秒)")
    decision_reason: str = Field("", description="最终决策依据")


class HealthResponse(BaseModel):
    """健康检查"""
    status: str = Field("ok", description="服务状态")
    version: str = Field("0.1.0", description="版本号")
    kb_loaded: bool = Field(False, description="知识库是否已加载")
    kb_entity_count: int = Field(0, description="知识库实体数")


class NILRequest(BaseModel):
    """NIL检测请求"""
    text: str = Field(..., description="待检测的指称文本")
    entity_type: Optional[str] = Field(None, description="实体类型(可选)")


class NILResponse(BaseModel):
    """NIL检测响应"""
    is_nil: bool = Field(False, description="True=知识库中无此实体")
    confidence: float = Field(0.0, description="置信度")
    reason: str = Field("", description="判定理由")


class CorefRequest(BaseModel):
    """共指消解请求"""
    text: str = Field(..., description="需要消解的完整文本")


class CorefResult(BaseModel):
    """共指消解结果项"""
    index: int = Field(..., description="在原文中的字符位置")
    mention: str = Field(..., description="指代词文本")
    entity_type: str = Field("", description="实体类型")
    coref_target: Optional[str] = Field(None, description="回链到的实体名")
    entity_id: Optional[str] = Field(None, description="回链到的实体ID")


class CorefResponse(BaseModel):
    """共指消解响应"""
    results: List[CorefResult] = Field(default_factory=list, description="消解结果列表")
