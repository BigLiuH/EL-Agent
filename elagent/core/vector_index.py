"""
向量索引模块

提供基于向量的语义检索能力。
"""

import json
import logging
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger(__name__)


class VectorIndex:
    """
    向量索引

    使用sentence-transformers编码文本，FAISS建立索引。
    """

    def __init__(self):
        """初始化向量索引"""
        self.model = None
        self.index = None
        self.entity_ids: List[str] = []
        self.dimension: int = 768
        self._built = False

    @property
    def built(self) -> bool:
        """索引是否已构建"""
        return self._built

    def load_model(self, model_name: str = "moka-ai/m3e-base"):
        """
        加载预训练模型

        Args:
            model_name: 模型名称
        """
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            logger.info(f"加载向量模型: {model_name}")

            # 检测设备
            device = "cuda" if torch.cuda.is_available() else "cpu"
            logger.info(f"使用设备: {device}")

            self.model = SentenceTransformer(model_name, device=device)
            self.dimension = self.model.get_sentence_embedding_dimension()
            logger.info(f"模型加载完成，维度: {self.dimension}")
        except Exception as e:
            logger.warning(f"模型加载失败，向量检索将不可用: {e}")
            self.model = None
            # 不抛出异常，允许系统继续运行

    def build(self, entities: Dict, model_name: str = "moka-ai/m3e-base"):
        """
        构建向量索引

        Args:
            entities: 实体字典 {entity_id: Entity}
            model_name: 模型名称
        """
        logger.info("开始构建向量索引...")

        # 加载模型
        if self.model is None:
            self.load_model(model_name)

        # 如果模型加载失败，跳过向量索引构建
        if self.model is None:
            logger.warning("模型未加载，跳过向量索引构建")
            return

        import faiss

        # 准备文本
        self.entity_ids = []
        texts = []

        for entity_id, entity in entities.items():
            # 拼接文本：标准名 + 别名 + 描述
            text_parts = [entity.standard_name]
            text_parts.extend(entity.aliases[:3])  # 最多3个别名
            if entity.description:
                text_parts.append(entity.description[:100])

            text = " ".join(text_parts)
            self.entity_ids.append(entity_id)
            texts.append(text)

        # 编码
        logger.info(f"编码 {len(texts)} 个实体...")
        embeddings = self.model.encode(texts, show_progress_bar=True, batch_size=16)
        embeddings = np.array(embeddings).astype('float32')

        # 归一化
        faiss.normalize_L2(embeddings)

        # 构建索引
        self.index = faiss.IndexFlatIP(self.dimension)  # 内积索引
        self.index.add(embeddings)

        self._built = True
        logger.info(f"向量索引构建完成: {len(self.entity_ids)} 个实体")

    def search(self, query: str, top_k: int = 10) -> List[Tuple[str, float]]:
        """
        向量检索

        Args:
            query: 查询文本
            top_k: 返回前K个结果

        Returns:
            [(entity_id, score), ...] 按分数降序排列
        """
        if not self._built:
            logger.warning("向量索引未构建")
            return []

        import faiss

        # 编码查询
        query_embedding = self.model.encode([query])
        query_embedding = np.array(query_embedding).astype('float32')
        faiss.normalize_L2(query_embedding)

        # 检索
        scores, indices = self.index.search(query_embedding, top_k)

        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < len(self.entity_ids) and score > 0:
                results.append((self.entity_ids[idx], float(score)))

        return results

    def save(self, path: str):
        """保存索引到文件"""
        import faiss

        output_dir = Path(path)
        output_dir.mkdir(parents=True, exist_ok=True)

        # 保存FAISS索引
        faiss.write_index(self.index, str(output_dir / "vector.index"))

        # 保存entity_ids
        with open(output_dir / "entity_ids.json", 'w', encoding='utf-8') as f:
            json.dump(self.entity_ids, f)

        logger.info(f"向量索引已保存到: {path}")

    def load(self, path: str, model_name: str = "moka-ai/m3e-base"):
        """从文件加载索引"""
        import faiss

        input_dir = Path(path)

        # 加载模型
        if self.model is None:
            self.load_model(model_name)

        # 加载FAISS索引
        self.index = faiss.read_index(str(input_dir / "vector.index"))

        # 加载entity_ids
        with open(input_dir / "entity_ids.json", 'r', encoding='utf-8') as f:
            self.entity_ids = json.load(f)

        self._built = True
        logger.info(f"向量索引已加载: {len(self.entity_ids)} 个实体")


# 全局向量索引实例
vector_index = VectorIndex()
