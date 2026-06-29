"""
数据模型模块

定义实体链接系统的核心数据结构。
"""

from .mention import Mention
from .entity import Entity, Candidate
from .result import LinkResult, TraceLog

__all__ = [
    "Mention",
    "Entity",
    "Candidate",
    "LinkResult",
    "TraceLog",
]
