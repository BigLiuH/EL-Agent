"""
LLM消歧模块

当规则消歧器无法可靠区分候选实体时（top-2得分差<阈值），
调用LLM利用语境+世界知识做最终判别。

支持: OpenRouter (OpenAI兼容API)
"""

import json
import logging
import os
import re
import time
from typing import List, Dict, Optional

from ..models.mention import Mention
from ..models.entity import Entity, Candidate

logger = logging.getLogger(__name__)


class LLMDisambiguator:
    """
    LLM消歧器

    仅作为规则消歧器的补充——当top-2候选得分接近时，
    用LLM的语境理解和世界知识打破僵局。

    安全措施：
    - 缓存：相同mention在同一文章中不重复调用
    - 限流：最大调用数 + 调用间隔
    - 超时：单次调用10s超时
    - 降级：任何异常都回退到规则结果
    """

    def __init__(self,
                 api_key: str = None,
                 model: str = "nvidia/nemotron-3-ultra-550b-a55b:free",
                 base_url: str = "https://openrouter.ai/api/v1",
                 max_calls: int = 500,       # 单次评测最大调用数
                 call_interval: float = 0.5,  # 调用间隔（秒），避免限流
                 call_timeout: int = 15):     # 单次调用超时（秒）
        self.model = model
        self.base_url = base_url
        self.max_calls = max_calls
        self.call_interval = call_interval
        self.call_timeout = call_timeout
        self.client = None
        self._available = False
        self._call_count = 0
        self._cache = {}  # (mention_text, article_hash) -> entity_id
        self._init_client(api_key)

    def _init_client(self, api_key: str = None):
        """初始化LLM客户端（OpenAI兼容API）"""
        try:
            from openai import OpenAI
            key = api_key or os.environ.get("OPENROUTER_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                logger.warning("LLM消歧: 未设置API Key")
                return
            self.client = OpenAI(api_key=key, base_url=self.base_url, timeout=self.call_timeout)
            self._available = True
            logger.info(f"LLM消歧器就绪: model={self.model}, max_calls={self.max_calls}")
        except ImportError:
            logger.warning("LLM消歧: pip install openai")
            self._available = False
        except Exception as e:
            logger.warning(f"LLM消歧: 初始化失败 - {e}")
            self._available = False

    @property
    def available(self) -> bool:
        if not self._available or self.client is None:
            return False
        if self._call_count >= self.max_calls:
            return False
        return True

    def reset(self):
        """重置调用计数和缓存（每次评测前调用）"""
        self._call_count = 0
        self._cache = {}

    def disambiguate(self,
                     mention: Mention,
                     candidates: List[Candidate],
                     full_text: str = "",
                     top_k: int = 1) -> List[Candidate]:
        """LLM消歧"""
        if not self.available or len(candidates) < 2:
            return candidates[:top_k]

        # 缓存检查
        cache_key = (mention.text, hash(full_text[:200]) if full_text else 0)
        if cache_key in self._cache:
            best_id = self._cache[cache_key]
            return self._reorder(candidates, best_id, top_k)

        try:
            best_id = self._call_llm(mention, candidates[:5], full_text)
            if best_id:
                self._cache[cache_key] = best_id
                self._call_count += 1
                return self._reorder(candidates, best_id, top_k)
        except Exception as e:
            logger.debug(f"LLM调用失败，回退: {e}")

        return candidates[:top_k]

    def _reorder(self, candidates, best_id, top_k):
        """将best_id排到首位"""
        reordered = list(candidates)
        for i, c in enumerate(reordered):
            if c.entity.id == best_id:
                reordered.insert(0, reordered.pop(i))
                break
        return reordered[:top_k]

    def _call_llm(self, mention: Mention, candidates: List[Candidate], full_text: str) -> Optional[str]:
        """调用LLM"""
        candidate_lines = []
        for i, c in enumerate(candidates, 1):
            entity = c.entity
            aliases_str = "、".join(entity.aliases[:5]) if entity.aliases else "无"
            candidate_lines.append(
                f"{i}. ID={entity.id} 名称={entity.standard_name} "
                f"类型={entity.entity_type} 别名={aliases_str}"
            )

        context = full_text[:2000] if full_text else (mention.context or "")[:2000]

        prompt = f"""体育实体链接：根据文章语境，判断"{mention.text}"最可能指向哪个候选实体。只返回JSON：{{"entity_id":"ID","reason":"理由"}}

文章（截取）：
{context}

候选：
{chr(10).join(candidate_lines)}"""

        # 限流间隔
        if self._call_count > 0:
            time.sleep(self.call_interval)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=150,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )

        content = response.choices[0].message.content.strip()
        result = self._parse_response(content)
        if result and self._call_count % 50 == 0:
            logger.info(f"LLM消歧 [{self._call_count}/{self.max_calls}]: {mention.text} → {result.get('entity_id','?')}")
        return result.get("entity_id") if result else None

    def _parse_response(self, content: str) -> Optional[Dict]:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r'\{[^}]+\}', content)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass
        return None


llm_disambiguator = LLMDisambiguator(
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    base_url="https://openrouter.ai/api/v1",
    max_calls=100,       # 小规模测试最多100次
    call_interval=1.0,   # 每秒1次
    call_timeout=15,     # 15秒超时
)
