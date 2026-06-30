"""
配置管理模块

提供系统配置的加载和管理功能。
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _load_dotenv():
    """加载 .env 文件到环境变量"""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if key not in os.environ:
                        os.environ[key] = value


_load_dotenv()


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

    # LLM消歧配置
    llm_enabled: bool = True           # 是否启用LLM消歧
    llm_model: str = "openai/gpt-oss-20b:free"  # 模型
    llm_base_url: str = "https://openrouter.ai/api/v1"  # API地址
    llm_api_key: Optional[str] = None  # API Key（默认从OPENROUTER_API_KEY环境变量读取）
    llm_score_gap: float = 0.01        # top-2得分差小于0.01时触发LLM
    llm_max_candidates: int = 5        # 送入LLM的最多候选数

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
            self.aliases_path = self.raw_data_dir / "aliases_merged.json"
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
