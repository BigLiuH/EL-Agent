"""
链接结果(LinkResult)和追溯日志(TraceLog)数据模型

定义实体链接结果和追溯日志的数据结构。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime
import uuid

from .mention import Mention
from .entity import Entity, Candidate


@dataclass
class LinkResult:
    """
    链接结果

    表示一次实体链接的完整结果。

    Attributes:
        mention: 原始指称
        linked_entity: 链接到的实体（NIL时为None）
        is_nil: 是否为NIL（知识库中无对应实体）
        confidence: 置信度（0-1）
        nil_reason: NIL判定理由（若为NIL）
        candidates: 候选实体列表
        trace_id: 追溯ID
        timestamp: 处理时间
        processing_time_ms: 处理耗时（毫秒）
    """

    mention: Mention
    linked_entity: Optional[Entity] = None
    is_nil: bool = False
    confidence: float = 0.0
    nil_reason: str = ""
    candidates: List[Candidate] = field(default_factory=list)
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "mention": self.mention.to_dict(),
            "linked_entity": self.linked_entity.to_dict() if self.linked_entity else None,
            "is_nil": self.is_nil,
            "confidence": self.confidence,
            "nil_reason": self.nil_reason,
            "candidates": [c.to_dict() for c in self.candidates],
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "processing_time_ms": self.processing_time_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinkResult":
        """从字典创建LinkResult实例"""
        return cls(
            mention=Mention.from_dict(data["mention"]),
            linked_entity=Entity.from_dict(data["linked_entity"]) if data.get("linked_entity") else None,
            is_nil=data.get("is_nil", False),
            confidence=data.get("confidence", 0.0),
            nil_reason=data.get("nil_reason", ""),
            candidates=[Candidate.from_dict(c) for c in data.get("candidates", [])],
            trace_id=data.get("trace_id", str(uuid.uuid4())),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            processing_time_ms=data.get("processing_time_ms", 0.0),
        )


@dataclass
class TraceLog:
    """
    追溯日志

    记录实体链接过程中每一步的详细信息。

    Attributes:
        trace_id: 追溯ID
        mention_id: 指称ID
        skill_name: 执行的Skill名称
        input_data: 输入数据快照
        output_data: 输出数据快照
        timestamp: 记录时间
        duration_ms: 耗时（毫秒）
        decision_reason: 决策依据
    """

    trace_id: str
    mention_id: str
    skill_name: str
    input_data: Dict = field(default_factory=dict)
    output_data: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0
    decision_reason: str = ""

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "trace_id": self.trace_id,
            "mention_id": self.mention_id,
            "skill_name": self.skill_name,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "decision_reason": self.decision_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TraceLog":
        """从字典创建TraceLog实例"""
        return cls(
            trace_id=data["trace_id"],
            mention_id=data["mention_id"],
            skill_name=data["skill_name"],
            input_data=data.get("input_data", {}),
            output_data=data.get("output_data", {}),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            duration_ms=data.get("duration_ms", 0.0),
            decision_reason=data.get("decision_reason", ""),
        )
