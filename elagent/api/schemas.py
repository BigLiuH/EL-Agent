"""
API请求和响应的数据模型
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


class MentionRequest(BaseModel):
    """待链接的实体指称"""
    text: str = Field(..., description="指称文本，如'世锦赛'、'浙江队'、'陈雨菲'")
    start_pos: int = Field(..., ge=0, description="在原文中的起始字符位置")
    end_pos: int = Field(..., ge=0, description="在原文中的结束字符位置")
    entity_type: Optional[str] = Field(None, description="实体类型，可选: PER(人物) ORG(组织) LOC(地点) EVENT(赛事)")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "世锦赛",
                "start_pos": 24,
                "end_pos": 27,
                "entity_type": "EVENT"
            }
        }


class LinkRequest(BaseModel):
    """实体链接请求"""
    text: str = Field(..., description="包含待链接指称的完整文本（建议传入全文以提高消歧准确率）")
    mention: MentionRequest = Field(..., description="待链接的指称信息")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "2024年世界羽毛球锦标赛在哥本哈根举行，中国羽毛球队在世锦赛上表现出色，石宇奇获得男单冠军。",
                "mention": {
                    "text": "世锦赛",
                    "start_pos": 37,
                    "end_pos": 40,
                    "entity_type": "EVENT"
                }
            }
        }


class BatchLinkRequest(BaseModel):
    """批量实体链接请求"""
    items: List[LinkRequest] = Field(..., description="链接请求列表（建议不超过100条）")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "text": "浙江队在2026年全国游泳冠军赛上表现出色，浙江队选手潘展乐获得金牌。",
                        "mention": {"text": "浙江队", "start_pos": 0, "end_pos": 3, "entity_type": "ORG"}
                    },
                    {
                        "text": "浙江队在2026年全国游泳冠军赛上表现出色，浙江队选手潘展乐获得金牌。",
                        "mention": {"text": "浙江队", "start_pos": 28, "end_pos": 31, "entity_type": "ORG"}
                    }
                ]
            }
        }


class EntityResponse(BaseModel):
    """知识库实体信息"""
    id: str = Field(..., description="实体唯一ID，如 EVENT_0160、ORG_0067")
    standard_name: str = Field(..., description="标准全称，如'世界羽毛球锦标赛'")
    entity_type: str = Field(..., description="实体类型: PER人物 ORG组织 LOC地点 EVENT赛事")
    aliases: List[str] = Field(default_factory=list, description="别名/简称/曾用名列表")
    description: str = Field("", description="实体描述信息")


class LinkResponse(BaseModel):
    """实体链接响应"""
    linked_entity: Optional[EntityResponse] = Field(None, description="链接到的知识库实体（NIL时为null）")
    is_nil: bool = Field(False, description="True=知识库中无对应实体")
    confidence: float = Field(0.0, description="置信度(0~1)，越高越可靠")
    nil_reason: str = Field("", description="NIL判定理由")
    trace_id: str = Field("", description="追溯ID，可通过 GET /trace/{id} 查看处理过程")
    processing_time_ms: float = Field(0.0, description="处理耗时(毫秒)")


class BatchLinkResponse(BaseModel):
    """批量链接响应"""
    results: List[LinkResponse] = Field(..., description="各条链接结果（与请求顺序一致）")
    total: int = Field(0, description="总处理数")
    success_count: int = Field(0, description="成功链接数（非NIL）")
    nil_count: int = Field(0, description="判定为NIL的数量")


class KBStatsResponse(BaseModel):
    """知识库统计"""
    total_entities: int = Field(0, description="实体总数")
    total_aliases: int = Field(0, description="别名总数")
    entity_types: Dict[str, int] = Field(default_factory=dict, description="各类型实体数量")
    loaded: bool = Field(False, description="知识库是否已加载")


class TraceResponse(BaseModel):
    """追溯日志详情"""
    trace_id: str = Field("", description="追溯唯一标识")
    mention_id: str = Field("", description="指称ID")
    skill_name: str = Field("entity_linking", description="执行的能力名称")
    input_data: Dict = Field(default_factory=dict, description="请求输入数据")
    output_data: Dict = Field(default_factory=dict, description="最终链接结果")
    timestamp: str = Field("", description="处理时间")
    duration_ms: float = Field(0.0, description="总耗时(毫秒)")
    decision_reason: str = Field("", description="最终决策依据")


class HealthResponse(BaseModel):
    """服务健康状态"""
    status: str = Field("ok", description="服务状态")
    version: str = Field("0.1.0", description="系统版本")
    kb_loaded: bool = Field(False, description="知识库是否已加载")
    kb_entity_count: int = Field(0, description="知识库中的实体总数")


class NILRequest(BaseModel):
    """NIL检测请求"""
    text: str = Field(..., description="待检测的指称文本")
    entity_type: Optional[str] = Field(None, description="实体类型（可选，提供可提高准确率）")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "丹尼·汉姆林",
                "entity_type": "PER"
            }
        }


class NILResponse(BaseModel):
    """NIL检测响应"""
    is_nil: bool = Field(False, description="True=知识库中无此实体")
    confidence: float = Field(0.0, description="判定置信度")
    reason: str = Field("", description="判定理由")


class CorefRequest(BaseModel):
    """共指消解请求"""
    text: str = Field(..., description="需要做共指消解的完整文本")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "陈雨菲在决赛中击败山口茜夺冠。她赛后表示状态很好。本次赛事是她今年第三次夺冠。"
            }
        }


class CorefResult(BaseModel):
    """共指消解结果"""
    index: int = Field(..., description="指代词在原文中的字符位置")
    mention: str = Field(..., description="指代词文本，如'她'、'本次赛事'")
    entity_type: str = Field("", description="实体类型")
    coref_target: Optional[str] = Field(None, description="回链到的前序实体名")
    entity_id: Optional[str] = Field(None, description="回链到的实体ID")


class CorefResponse(BaseModel):
    """共指消解响应"""
    results: List[CorefResult] = Field(default_factory=list, description="所有指代词的消解结果")
