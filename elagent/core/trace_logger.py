"""
追溯日志模块

记录实体链接过程中每一步的详细信息，支持可追溯、可回放。
"""

import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)


@dataclass
class TraceStep:
    """
    追溯步骤

    记录每一次数据加工的原值、新值、依据。
    """
    step_name: str  # 步骤名称
    original_value: any  # 原值
    new_value: any  # 新值
    reason: str  # 依据
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TraceLog:
    """
    追溯日志

    记录一次实体链接的完整处理过程。
    """
    trace_id: str
    mention_id: str
    mention_text: str
    entity_type: str
    steps: List[TraceStep] = field(default_factory=list)
    final_result: Dict = field(default_factory=dict)
    input_data: Dict = field(default_factory=dict)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None
    total_duration_ms: float = 0.0

    def add_step(self, step_name: str, original_value: any, new_value: any, reason: str, duration_ms: float = 0.0):
        """添加追溯步骤"""
        step = TraceStep(
            step_name=step_name,
            original_value=original_value,
            new_value=new_value,
            reason=reason,
            duration_ms=duration_ms
        )
        self.steps.append(step)

    def finalize(self, final_result: Dict):
        """完成追溯日志"""
        self.end_time = datetime.now().isoformat()
        self.final_result = final_result
        # 计算总耗时
        start = datetime.fromisoformat(self.start_time)
        end = datetime.fromisoformat(self.end_time)
        self.total_duration_ms = (end - start).total_seconds() * 1000

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "mention_id": self.mention_id,
            "mention_text": self.mention_text,
            "entity_type": self.entity_type,
            "steps": [s.to_dict() for s in self.steps],
            "final_result": self.final_result,
            "input_data": self.input_data,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "total_duration_ms": self.total_duration_ms
        }


class TraceLogger:
    """
    追溯日志管理器

    管理和存储追溯日志。
    """

    def __init__(self, storage_path: str = "data/trace_logs"):
        """
        初始化追溯日志管理器

        Args:
            storage_path: 日志存储路径
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logs: Dict[str, TraceLog] = {}

    def create_trace(self, mention_id: str, mention_text: str, entity_type: str,
                     input_data: Dict = None) -> TraceLog:
        """
        创建追溯日志

        Args:
            mention_id: 指称ID
            mention_text: 指称文本
            entity_type: 实体类型
            input_data: 原始输入数据（用于回放）

        Returns:
            追溯日志对象
        """
        trace_id = str(uuid.uuid4())
        trace = TraceLog(
            trace_id=trace_id,
            mention_id=mention_id,
            mention_text=mention_text,
            entity_type=entity_type
        )
        if input_data:
            trace.input_data = input_data
        self.logs[trace_id] = trace
        return trace

    def get_trace(self, trace_id: str) -> Optional[TraceLog]:
        """获取追溯日志"""
        return self.logs.get(trace_id)

    def save_trace(self, trace: TraceLog):
        """保存追溯日志到文件"""
        file_path = self.storage_path / f"{trace.trace_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(trace.to_dict(), f, ensure_ascii=False, indent=2)
        logger.debug(f"追溯日志已保存: {file_path}")

    def load_trace(self, trace_id: str) -> Optional[TraceLog]:
        """从文件加载追溯日志"""
        file_path = self.storage_path / f"{trace_id}.json"
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # 重建TraceLog对象
                trace = TraceLog(
                    trace_id=data["trace_id"],
                    mention_id=data["mention_id"],
                    mention_text=data["mention_text"],
                    entity_type=data["entity_type"],
                    start_time=data["start_time"],
                    end_time=data.get("end_time"),
                    total_duration_ms=data.get("total_duration_ms", 0.0)
                )
                # 重建步骤
                for step_data in data.get("steps", []):
                    trace.steps.append(TraceStep(**step_data))
                trace.final_result = data.get("final_result", {})
                return trace
        return None

    def list_traces(self, limit: int = 100) -> List[Dict]:
        """列出最近的追溯日志"""
        traces = []
        for file_path in sorted(self.storage_path.glob("*.json"), reverse=True)[:limit]:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                traces.append({
                    "trace_id": data["trace_id"],
                    "mention_text": data["mention_text"],
                    "entity_type": data["entity_type"],
                    "start_time": data["start_time"],
                    "total_duration_ms": data.get("total_duration_ms", 0.0)
                })
        return traces


# 全局追溯日志管理器实例
trace_logger = TraceLogger()
