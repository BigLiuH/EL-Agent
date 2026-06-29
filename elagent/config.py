"""
配置管理模块

提供系统配置的加载和管理功能。
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    """系统配置"""

    # 项目根目录
    project_root: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    # 数据目录
    data_dir: Path = field(default=None)
    raw_data_dir: Path = field(default=None)
    processed_data_dir: Path = field(default=None)

    # 知识库文件路径
    knowledge_base_path: Path = field(default=None)
    aliases_path: Path = field(default=None)
    llm_extracted_path: Path = field(default=None)

    # 服务配置
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True

    # 日志配置
    log_level: str = "INFO"

    def __post_init__(self):
        """初始化后处理，设置默认路径"""
        if self.data_dir is None:
            self.data_dir = self.project_root / "data"
        if self.raw_data_dir is None:
            self.raw_data_dir = self.project_root / "Dataset"  # 指向实际的Dataset目录
        if self.processed_data_dir is None:
            self.processed_data_dir = self.data_dir / "processed"
        if self.knowledge_base_path is None:
            self.knowledge_base_path = self.raw_data_dir / "knowledge_base_merged.json"
        if self.aliases_path is None:
            self.aliases_path = self.raw_data_dir / "aliases_from_kb.json.json"
        if self.llm_extracted_path is None:
            self.llm_extracted_path = self.raw_data_dir / "llm_extracted_merged.json"


# 全局配置实例
config = Config()


def load_config_from_yaml(yaml_path: str) -> Config:
    """从YAML文件加载配置"""
    import yaml

    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    # 更新配置
    cfg = Config()
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)

    return cfg
