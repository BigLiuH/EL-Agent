"""
BERT消歧模块

使用Bi-Encoder计算mention上下文与候选实体描述的语义相似度。
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class BERTDisambiguator:
    """
    BERT消歧器

    使用Bi-Encoder计算语义相似度进行消歧。
    优点：速度快，候选向量可以预计算。
    """

    def __init__(self):
        """初始化BERT消歧器"""
        self.model = None
        self.entity_embeddings = {}  # entity_id -> embedding
        self.entity_ids = []
        self._loaded = False

    def load_model(self, model_name: str = "moka-ai/m3e-base"):
        """
        加载Bi-Encoder模型

        Args:
            model_name: 模型名称
        """
        try:
            from sentence_transformers import SentenceTransformer
            import torch

            # 检测设备
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"加载Bi-Encoder模型: {model_name} (设备: {device})")

            self.model = SentenceTransformer(model_name, device=device)
            self._loaded = True
            logger.info("Bi-Encoder模型加载完成")
        except Exception as e:
            logger.warning(f"Bi-Encoder模型加载失败: {e}")
            self._loaded = False

    @property
    def loaded(self) -> bool:
        """模型是否已加载"""
        return self._loaded

    def build_index(self, entities: Dict):
        """
        构建实体向量索引

        Args:
            entities: 实体字典 {entity_id: Entity}
        """
        if not self._loaded:
            logger.warning("模型未加载，无法构建索引")
            return

        logger.info("构建实体向量索引...")

        # 准备文本
        self.entity_ids = []
        texts = []

        for entity_id, entity in entities.items():
            # 拼接文本：标准名 + 描述
            text = entity.standard_name
            if entity.description:
                text += " " + entity.description[:200]

            self.entity_ids.append(entity_id)
            texts.append(text)

        # 编码
        logger.info(f"编码 {len(texts)} 个实体...")
        embeddings = self.model.encode(texts, show_progress_bar=True, batch_size=32)

        # 存储向量
        for i, entity_id in enumerate(self.entity_ids):
            self.entity_embeddings[entity_id] = embeddings[i]

        logger.info(f"实体向量索引构建完成: {len(self.entity_ids)} 个实体")

    def disambiguate(self,
                     mention_text: str,
                     mention_context: str,
                     candidates: List[Dict],
                     top_k: int = 1) -> List[Tuple[str, float]]:
        """
        使用Bi-Encoder消歧

        Args:
            mention_text: mention文本
            mention_context: mention上下文
            candidates: 候选实体列表，每个包含 entity_id, standard_name
            top_k: 返回前K个结果

        Returns:
            [(entity_id, score), ...] 按分数降序排列
        """
        if not self._loaded or not candidates:
            return []

        # 编码mention上下文
        query_embedding = self.model.encode([mention_context])

        # 计算与每个候选的相似度
        results = []
        for candidate in candidates:
            entity_id = candidate['entity_id']
            if entity_id in self.entity_embeddings:
                entity_embedding = self.entity_embeddings[entity_id]
                # 计算余弦相似度
                score = np.dot(query_embedding[0], entity_embedding) / (
                    np.linalg.norm(query_embedding[0]) * np.linalg.norm(entity_embedding)
                )
                results.append((entity_id, float(score)))

        # 按分数降序排序
        results.sort(key=lambda x: x[1], reverse=True)

        return results[:top_k]

    def save_index(self, path: str):
        """保存向量索引"""
        output_path = Path(path)
        output_path.mkdir(parents=True, exist_ok=True)

        # 保存entity_ids
        with open(output_path / "entity_ids.json", 'w', encoding='utf-8') as f:
            json.dump(self.entity_ids, f)

        # 保存向量
        embeddings = np.array([self.entity_embeddings[eid] for eid in self.entity_ids])
        np.save(output_path / "embeddings.npy", embeddings)

        logger.info(f"向量索引已保存到: {path}")

    def load_index(self, path: str):
        """加载向量索引"""
        input_path = Path(path)

        # 加载entity_ids
        with open(input_path / "entity_ids.json", 'r', encoding='utf-8') as f:
            self.entity_ids = json.load(f)

        # 加载向量
        embeddings = np.load(input_path / "embeddings.npy")

        for i, entity_id in enumerate(self.entity_ids):
            self.entity_embeddings[entity_id] = embeddings[i]

        logger.info(f"向量索引已加载: {len(self.entity_ids)} 个实体")


# 全局BERT消歧器实例
bert_disambiguator = BERTDisambiguator()
