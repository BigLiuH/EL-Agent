"""
LLM消歧模块

当规则消歧器无法可靠区分候选实体时（top-2得分差<阈值），
调用LLM利用语境+世界知识做最终判别。

支持: OpenRouter (OpenAI兼容API)
"""

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
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
        self._cache_file = Path(__file__).parent.parent.parent / "data" / "llm_cache.json"
        self._cache = self._load_cache()  # 持久化缓存
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

    def _call_with_retry(self, messages, max_tokens=30):
        """API调用带重试（429限流自动等待）"""
        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=self.model, max_tokens=max_tokens, temperature=0,
                    messages=messages)
                return response
            except Exception as e:
                if "429" in str(e) and attempt < 2:
                    wait = (attempt + 1) * 5
                    logger.debug(f"限流，等待{wait}s...")
                    time.sleep(wait)
                else:
                    raise
        return None

    def _load_cache(self) -> dict:
        """加载持久化缓存"""
        if self._cache_file.exists():
            try:
                with open(self._cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        """立即写入缓存到磁盘，每次调用LLM后必须保存"""
        self._cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_path = str(self._cache_file.resolve())
        tmp = cache_path + ".tmp"
        data = json.dumps(self._cache, ensure_ascii=False, indent=2)
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, cache_path)
        print(f"  [缓存] 已保存 {len(self._cache)} 条记录")

    def get_article_domain(self, full_text: str) -> str:
        """判断文章运动领域（缓存），每篇文章只调一次LLM"""
        text_key = hashlib.md5(full_text[:500].encode()).hexdigest()
        if text_key in self._cache:
            return self._cache.get(text_key, "")

        if not self.available or len(full_text) < 50:
            return ""

        try:
            prompt = f"以下文章主要讨论哪种体育运动？只回复一个词，如：羽毛球、乒乓球、游泳、斯诺克、田径、足球、篮球。\n\n{full_text[:1500]}"
            response = self._call_with_retry(
                [{"role": "user", "content": prompt}], max_tokens=10)
            if not response: return ""
            domain = response.choices[0].message.content.strip()
            self._cache[text_key] = domain
            self._save_cache()
            self._call_count += 1
            print(f"  [LLM #{self._call_count}] 文章领域: {domain}")
            return domain
        except Exception:
            return ""

    def reset(self):
        """重置调用计数（缓存保留）"""
        self._call_count = 0

    def disambiguate(self,
                     mention: Mention,
                     candidates: List[Candidate],
                     full_text: str = "",
                     top_k: int = 1) -> List[Candidate]:
        """LLM消歧"""
        if len(candidates) < 2:
            return candidates[:top_k]

        # 缓存优先（max_calls到了也能用历史缓存）
        cache_key = f"{mention.text}|{hashlib.md5((full_text[:200] or '').encode()).hexdigest()}"
        if cache_key in self._cache:
            best_id = self._cache[cache_key]
            return self._reorder(candidates, best_id, top_k)

        if not self.available:
            return candidates[:top_k]

        try:
            best_id = self._call_llm(mention, candidates[:5], full_text)
            if best_id:
                self._cache[cache_key] = best_id
                self._save_cache()  # 持久化
                self._call_count += 1
                print(f"  [LLM #{self._call_count}] 消歧 {mention.text} -> {best_id}")
                return self._reorder(candidates, best_id, top_k)
        except Exception as e:
            print(f"  [LLM ERROR] {e}")
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

        # 取mention周围±1000字的窗口作为上下文
        if full_text:
            start = max(0, mention.start_pos - 1000)
            end = min(len(full_text), mention.end_pos + 1000)
            context = full_text[start:end]
        else:
            context = (mention.context or "")[:2000]

        prompt = f"""根据文章语境，\"{mention.text}\"最可能是以下哪个实体？只回复entity_id，不要解释。

文章：
{context}

候选：
{chr(10).join(candidate_lines)}"""

        # 限流间隔
        if self._call_count > 0:
            time.sleep(self.call_interval)

        response = self._call_with_retry(
            [{"role": "user", "content": prompt}], max_tokens=30)
        if not response: return None

        content = response.choices[0].message.content.strip()
        result = self._parse_response(content)
        if result and self._call_count % 50 == 0:
            logger.info(f"LLM消歧 [{self._call_count}/{self.max_calls}]: {mention.text} → {result.get('entity_id','?')}")
        return result.get("entity_id") if result else None

    def _parse_response(self, content: str) -> Optional[Dict]:
        # 尝试JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        # 尝试提取JSON片段
        match = re.search(r'\{[^}]+\}', content)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        # 纯文本：提取entity_id（去掉 ID=、id= 等前缀）
        for token in content.strip().split():
            token = token.strip('"\'` ,.;:')
            # 去掉常见前缀
            for prefix in ['ID=', 'id=', 'Id=', 'entity_id=']:
                if token.startswith(prefix):
                    token = token[len(prefix):]
            if '_' in token and len(token) > 5:
                return {"entity_id": token}
        first_line = content.strip().split('\n')[0].strip('"\'` ,.;:')
        for prefix in ['ID=', 'id=', 'Id=', 'entity_id=']:
            if first_line.startswith(prefix):
                first_line = first_line[len(prefix):]
        return {"entity_id": first_line} if first_line else None


llm_disambiguator = LLMDisambiguator(
    model="openai/gpt-oss-20b:free",
    base_url="https://openrouter.ai/api/v1",
    max_calls=500,       # gap<0.01触发 ~400次
    call_interval=1.0,   # 每秒1次
    call_timeout=15,     # 15秒超时
)
