"""
BM25索引模块

提供基于BM25的全文检索能力。
"""

import json
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from collections import defaultdict

import jieba
from rank_bm25 import BM25Okapi

from ..models.entity import Entity

logger = logging.getLogger(__name__)


class BM25Index:
    """
    BM25索引

    对知识库实体建立BM25倒排索引，支持全文检索。
    """

    def __init__(self):
        """初始化BM25索引"""
        self.bm25: Optional[BM25Okapi] = None
        self.entity_ids: List[str] = []  # 与BM25文档顺序对应
        self.corpus: List[str] = []  # 原始文本
        self.tokenized_corpus: List[List[str]] = []  # 分词后的文本
        self._built = False

    @property
    def built(self) -> bool:
        """索引是否已构建"""
        return self._built

    def build(self, entities: Dict[str, Entity], user_dict_path: Optional[str] = None) -> None:
        """
        构建BM25索引

        Args:
            entities: 实体字典 {entity_id: Entity}
            user_dict_path: 自定义词典路径（可选）
        """
        logger.info("开始构建BM25索引...")

        # 加载自定义词典
        if user_dict_path and Path(user_dict_path).exists():
            jieba.load_userdict(user_dict_path)
            logger.info(f"加载自定义词典: {user_dict_path}")

        # 添加实体名到自定义词典
        for entity in entities.values():
            jieba.add_word(entity.standard_name)
            for alias in entity.aliases:
                jieba.add_word(alias)

        # 构建语料库
        self.entity_ids = []
        self.corpus = []
        self.tokenized_corpus = []

        for entity_id, entity in entities.items():
            # 拼接文本：标准名 + 别名 + 描述
            text_parts = [entity.standard_name]
            text_parts.extend(entity.aliases)
            if entity.description:
                text_parts.append(entity.description[:200])  # 限制描述长度

            text = " ".join(text_parts)
            tokens = list(jieba.cut(text))

            self.entity_ids.append(entity_id)
            self.corpus.append(text)
            self.tokenized_corpus.append(tokens)

        # 构建BM25索引
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        self._built = True

        logger.info(f"BM25索引构建完成: {len(self.entity_ids)}个文档")

    def search(self, query: str, top_k: int = 20) -> List[Tuple[str, float]]:
        """
        BM25检索

        Args:
            query: 查询文本
            top_k: 返回前K个结果

        Returns:
            [(entity_id, score), ...] 按分数降序排列
        """
        if not self._built:
            logger.warning("BM25索引未构建")
            return []

        # 分词
        tokens = list(jieba.cut(query))

        # 计算BM25分数
        scores = self.bm25.get_scores(tokens)

        # 获取Top-K
        top_indices = scores.argsort()[-top_k:][::-1]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:
                results.append((self.entity_ids[idx], float(scores[idx])))

        return results

    def save(self, path: str) -> None:
        """保存索引到文件"""
        data = {
            "entity_ids": self.entity_ids,
            "corpus": self.corpus,
            "tokenized_corpus": self.tokenized_corpus,
        }
        with open(path, 'wb') as f:
            pickle.dump(data, f)
        logger.info(f"BM25索引已保存到: {path}")

    def load(self, path: str) -> None:
        """从文件加载索引"""
        with open(path, 'rb') as f:
            data = pickle.load(f)

        self.entity_ids = data["entity_ids"]
        self.corpus = data["corpus"]
        self.tokenized_corpus = data["tokenized_corpus"]

        # 重建BM25对象
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        self._built = True

        logger.info(f"BM25索引已加载: {len(self.entity_ids)}个文档")


# 全局BM25索引实例
bm25_index = BM25Index()
