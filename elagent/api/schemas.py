"""
API请求和响应的数据模型

每个模型都配有可直接运行的测试示例（Swagger "Try it out" 即点即测）。
测试数据基于项目体育知识库（羽毛球、乒乓球、游泳、斯诺克等领域）。
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional


# ============================================================
# 请求模型
# ============================================================

class MentionRequest(BaseModel):
    """待链接的实体指称"""
    text: str = Field(...,
        description="指称文本，如 '世锦赛'、'浙江队'、'陈雨菲'、'国羽'")
    start_pos: int = Field(..., ge=0,
        description="指称在原文中的起始字符位置（从0开始计数）")
    end_pos: int = Field(..., ge=0,
        description="指称在原文中的结束字符位置（不包含）")
    entity_type: Optional[str] = Field(None,
        description="实体类型: PER(人物) / ORG(组织) / LOC(地点) / EVENT(赛事)")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "世锦赛",
                "start_pos": 44,
                "end_pos": 47,
                "entity_type": "EVENT"
            }
        }


class LinkRequest(BaseModel):
    """实体链接请求"""
    text: str = Field(...,
        description="包含指称的完整文本。传入全文（非截断）可显著提高跨运动消歧准确率。")
    mention: MentionRequest = Field(...,
        description="待链接的指称信息")

    class Config:
        json_schema_extra = {
            "example": {
                "text": (
                    "2024年世界羽毛球锦标赛在丹麦哥本哈根举行，中国羽毛球队在世锦赛上"
                    "表现出色，石宇奇在男单决赛中击败安赛龙夺得冠军。"
                ),
                "mention": {
                    "text": "世锦赛",
                    "start_pos": 44,
                    "end_pos": 47,
                    "entity_type": "EVENT"
                }
            }
        }


class BatchLinkRequest(BaseModel):
    """批量实体链接请求，用于同一篇文章中多个实体的链接"""
    items: List[LinkRequest] = Field(...,
        description="链接请求列表（建议不超过100条）",
        min_length=1, max_length=100)

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "text": (
                            "2026年全国游泳冠军赛在杭州举行。浙江队选手潘展乐在男子100米"
                            "自由泳中夺冠，余依婷在女子200米混合泳中打破亚洲纪录。"
                        ),
                        "mention": {
                            "text": "浙江队", "start_pos": 17, "end_pos": 20,
                            "entity_type": "ORG"
                        }
                    },
                    {
                        "text": (
                            "2026年全国游泳冠军赛在杭州举行。浙江队选手潘展乐在男子100米"
                            "自由泳中夺冠，余依婷在女子200米混合泳中打破亚洲纪录。"
                        ),
                        "mention": {
                            "text": "全国游泳冠军赛", "start_pos": 0, "end_pos": 7,
                            "entity_type": "EVENT"
                        }
                    },
                    {
                        "text": (
                            "2026年全国游泳冠军赛在杭州举行。浙江队选手潘展乐在男子100米"
                            "自由泳中夺冠，余依婷在女子200米混合泳中打破亚洲纪录。"
                        ),
                        "mention": {
                            "text": "潘展乐", "start_pos": 24, "end_pos": 27,
                            "entity_type": "PER"
                        }
                    }
                ]
            }
        }


class NILRequest(BaseModel):
    """NIL检测请求"""
    text: str = Field(...,
        description="待检测的指称文本")
    entity_type: Optional[str] = Field(None,
        description="可选实体类型，提供可提高检测准确率")

    class Config:
        json_schema_extra = {
            "example": {
                "text": "丹尼·汉姆林",
                "entity_type": "PER"
            }
        }


class CorefRequest(BaseModel):
    """共指消解请求"""
    text: str = Field(...,
        description="需要消解的完整文本（含人称代词和指示代词）")

    class Config:
        json_schema_extra = {
            "example": {
                "text": (
                    "陈雨菲在决赛中击败山口茜。她赛后表示状态很好，"
                    "本次赛事是她今年第三次夺冠。该赛事汇聚了世界顶尖选手。"
                )
            }
        }


# ============================================================
# 响应模型
# ============================================================

class EntityResponse(BaseModel):
    """知识库实体信息"""
    id: str = Field(...,
        description="实体唯一ID，如 EVENT_0160")
    standard_name: str = Field(...,
        description="标准全称，如 '世界羽毛球锦标赛'")
    entity_type: str = Field(...,
        description="实体类型: PER / ORG / LOC / EVENT")
    aliases: List[str] = Field(default_factory=list,
        description="别名列表，如 ['世锦赛', '羽毛球世锦赛']")
    description: str = Field("",
        description="实体简介")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "EVENT_0160",
                "standard_name": "世界羽毛球锦标赛",
                "entity_type": "EVENT",
                "aliases": ["世锦赛", "羽毛球世锦赛", "世界羽毛球锦标赛"],
                "description": "世界羽毛球联合会主办的顶级羽毛球赛事，每年举办一届，"
                               "是世界羽毛球运动员争夺的最高荣誉之一。"
            }
        }


class LinkResponse(BaseModel):
    """实体链接响应"""
    linked_entity: Optional[EntityResponse] = Field(None,
        description="链接到的 KB 实体。is_nil=true 时为 null。")
    is_nil: bool = Field(False,
        description="True = KB 中无对应实体（应标注为 NIL）")
    confidence: float = Field(0.0,
        description="链接置信度 (0~1)，1.0=标准名精确匹配, 0.95=别名精确匹配")
    nil_reason: str = Field("",
        description="NIL 判定理由")
    trace_id: str = Field("",
        description="追溯 ID，可调用 GET /trace/{id} 查看完整处理链路")
    processing_time_ms: float = Field(0.0,
        description="处理耗时（毫秒）")

    class Config:
        json_schema_extra = {
            "example": {
                "linked_entity": {
                    "id": "EVENT_0160",
                    "standard_name": "世界羽毛球锦标赛",
                    "entity_type": "EVENT",
                    "aliases": ["世锦赛", "羽毛球世锦赛"],
                    "description": "世界羽毛球联合会主办的顶级羽毛球赛事。"
                },
                "is_nil": False,
                "confidence": 0.95,
                "nil_reason": "",
                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "processing_time_ms": 2.35
            }
        }


class BatchLinkResponse(BaseModel):
    """批量链接响应"""
    results: List[LinkResponse] = Field(...,
        description="各条链接结果（顺序与请求一致）")
    total: int = Field(0,
        description="总处理条数")
    success_count: int = Field(0,
        description="成功链接数（找到了 KB 实体）")
    nil_count: int = Field(0,
        description="NIL 判定数（未找到 KB 实体）")


class KBStatsResponse(BaseModel):
    """知识库统计"""
    total_entities: int = Field(0, description="实体总数")
    total_aliases: int = Field(0, description="别名映射总数")
    entity_types: Dict[str, int] = Field(default_factory=dict,
        description="各类型实体数量（PER/ORG/LOC/EVENT）")
    loaded: bool = Field(False, description="知识库是否已加载")


class TraceResponse(BaseModel):
    """追溯日志详情（每步含原值→新值→依据）"""
    trace_id: str = Field("", description="追溯唯一标识")
    mention_id: str = Field("", description="指称 ID")
    skill_name: str = Field("entity_linking", description="能力名称")
    input_data: Dict = Field(default_factory=dict,
        description="请求的完整输入（含全文、位置）")
    output_data: Dict = Field(default_factory=dict,
        description="{linked_entity_name, is_nil, confidence, ...}")
    timestamp: str = Field("", description="处理时间 ISO8601")
    duration_ms: float = Field(0.0, description="总耗时（毫秒）")
    decision_reason: str = Field("",
        description="最终选择依据，如 '别名精确匹配' 或 '从8个候选中消歧选择'")

    class Config:
        json_schema_extra = {
            "example": {
                "trace_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "mention_id": "m_001",
                "skill_name": "entity_linking",
                "input_data": {
                    "mention_text": "世锦赛",
                    "entity_type": "EVENT",
                    "start_pos": 44, "end_pos": 47,
                    "full_text": "2024年世界羽毛球锦标赛在哥本哈根举行..."
                },
                "output_data": {
                    "linked_entity_id": "EVENT_0160",
                    "linked_entity_name": "世界羽毛球锦标赛",
                    "is_nil": False,
                    "confidence": 0.95
                },
                "timestamp": "2026-07-01T12:00:00",
                "duration_ms": 2.35,
                "decision_reason": "从8个候选中消歧选择，得分=0.705"
            }
        }


class HealthResponse(BaseModel):
    """服务健康状态"""
    status: str = Field("ok", description="服务状态（ok = 正常）")
    version: str = Field("0.1.0", description="系统版本号")
    kb_loaded: bool = Field(False, description="知识库是否加载完成")
    kb_entity_count: int = Field(0, description="知识库实体总数")


class NILResponse(BaseModel):
    """NIL检测响应"""
    is_nil: bool = Field(False,
        description="True = KB 中不存在此实体")
    confidence: float = Field(0.0,
        description="NIL 判定置信度")
    reason: str = Field("",
        description="判定理由，如 '未找到任何候选实体'")

    class Config:
        json_schema_extra = {
            "example": {
                "is_nil": True,
                "confidence": 0.95,
                "reason": "未找到任何候选实体"
            }
        }


class CorefResult(BaseModel):
    """共指消解结果"""
    index: int = Field(...,
        description="指代词在原文中的字符位置")
    mention: str = Field(...,
        description="指代词文本，如 '她'、'本次赛事'")
    entity_type: str = Field("",
        description="PER / ORG / LOC / EVENT")
    coref_target: Optional[str] = Field(None,
        description="回链到的前序实体名（如 '陈雨菲'）")
    entity_id: Optional[str] = Field(None,
        description="回链到的实体 ID（如 'PER_0523'）")


class CorefResponse(BaseModel):
    """共指消解响应"""
    results: List[CorefResult] = Field(default_factory=list,
        description="文本中每个指代词的消解结果")

    class Config:
        json_schema_extra = {
            "example": {
                "results": [
                    {
                        "index": 13,
                        "mention": "她",
                        "entity_type": "PER",
                        "coref_target": "陈雨菲",
                        "entity_id": "PER_0523"
                    },
                    {
                        "index": 26,
                        "mention": "本次赛事",
                        "entity_type": "EVENT",
                        "coref_target": "2024年世界羽毛球锦标赛",
                        "entity_id": "EVENT_0006"
                    }
                ]
            }
        }
