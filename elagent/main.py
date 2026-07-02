"""
实体链接智能体 - 主入口

启动FastAPI服务，加载知识库。
"""

import logging
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager

from .api.routes import router
from .core.knowledge_base import knowledge_base
from .core.bm25_index import bm25_index
from .config import config


# 配置日志
logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理

    启动时加载知识库和构建索引，关闭时清理资源。
    """
    # 启动时
    logger.info("正在启动实体链接智能体...")
    try:
        # 加载知识库
        knowledge_base.load()
        logger.info(f"知识库加载成功: {knowledge_base.entity_count}个实体")

        # 构建BM25索引
        logger.info("正在构建BM25索引...")
        bm25_index.build(knowledge_base.entities)
        logger.info("BM25索引构建完成")

    except Exception as e:
        logger.error(f"初始化失败: {e}", exc_info=True)
        # 不阻止服务启动，但会返回错误
    yield
    # 关闭时
    logger.info("正在关闭实体链接智能体...")


# 创建FastAPI应用
app = FastAPI(
    title="实体链接与知识对齐智能体 API",
    description="""
## 概述

面向数据治理场景的实体链接系统。给定文本中的实体指称（mention），将其链接到知识库中的标准实体，完成消歧、别名标准化、NIL检测与共指消解。本智能体作为数据治理流水线中的专项能力，可被归一智能体和清洗智能体按需调用。

### 数据领域

知识库覆盖体育领域（羽毛球、乒乓球、游泳、田径、斯诺克、足球、篮球等），共 6,420 个实体（PER 3,133 / ORG 1,495 / EVENT 1,306 / LOC 1,115），8,452 条别名映射。标注数据集 1,239 篇文章、40,942 个 mention。

### 核心指标

| 指标 | 数值 | 目标 |
|---|---|---|
| 链接准确率 | 98.92% | ≥85% |
| 消歧准确率 | 90.85% | ≥85% |
| 别名召回率 | 99.00% | ≥85% |
| 共指消解 | 94.3% | ≥80% |
| NIL 检测 | 83.18% | ≥80% |

---

## 实体链接流水线

系统按以下优先级依次尝试：

1. **标准名称精确匹配** — mention 完全等于 KB 中的 standard_name → 置信度 1.0
2. **别名精确匹配** — mention 命中某个实体的 aliases → 置信度 0.95。多候选时触发消歧器
3. **模糊匹配** — mention 与 KB 实体名存在包含关系，长度差 ≤8 字符 → 置信度 0.80
4. **BM25 全文检索** — 基于 jieba 分词的 BM25 全文检索兜底
5. **NIL 判定** — 以上四步均未命中 → 判定为知识库中不存在

### 消歧器（第 2-4 步多候选时触发）

5 信号加权评分：

| 信号 | 权重 | 说明 |
|---|---|---|
| 名称匹配 | 0.15 | 精确匹配 1.0 / 别名匹配 0.95 / 包含匹配 0.6~0.95 |
| 先验概率 | 0.15 | cbrt 压缩归一化，中频实体差距最小 |
| 名称完整度 | 0.09 | 全称优先于简称，过度细化惩罚 |
| 类型一致性 | 0.15 | PER/ORG/LOC/EVENT 类型匹配 |
| 领域匹配 | 0.10 | 2+3gram 区分词在全文中的命中密度 |

### 共指消解逻辑

纯规则驱动——代词（她/他/它）和指代词（本次赛事/该队/该地区）通过查找**最近前序同类型实体提及**进行回链。

---

## 接口列表

### 系统
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 服务信息 |
| GET | `/health` | 健康检查 + KB 状态 |
| GET | `/kb/stats` | 知识库统计数据 |

### 核心能力
| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/link` | **实体链接**（核心接口） |
| POST | `/batch_link` | 批量实体链接 |
| POST | `/nil_check` | **NIL 检测**（独立 Skill） |
| POST | `/coref` | **共指消解**（独立 Skill，按需启用） |

### 审计追溯
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/trace/{id}` | 查看处理链路（每步原值→新值→依据） |
| GET | `/traces` | 列出最近的追溯记录 |
| POST | `/trace/{id}/replay` | 回放验证（重新执行并对比结果） |
| POST | `/trace/{id}/rollback` | 回滚（查看原始mention状态） |

---

## 快速测试

启动后访问 `/docs`，每个接口都有预填的**可直接运行的测试数据**（体育领域真实数据）。

### cURL 示例

```bash
# 实体链接
curl -X POST http://localhost:8000/link \\
  -H "Content-Type: application/json" \\
  -d '{"text":"2024年世界羽毛球锦标赛在哥本哈根举行，中国羽毛球队在世锦赛上表现出色。","mention":{"text":"世锦赛","start_pos":44,"end_pos":47,"entity_type":"EVENT"}}'

# NIL 检测
curl -X POST http://localhost:8000/nil_check \\
  -H "Content-Type: application/json" \\
  -d '{"text":"丹尼·汉姆林","entity_type":"PER"}'

# 共指消解
curl -X POST http://localhost:8000/coref \\
  -H "Content-Type: application/json" \\
  -d '{"text":"陈雨菲在决赛中击败山口茜。她赛后表示状态很好。本次赛事是她今年第三次夺冠。"}'
```

---

## 设计原则

1. **弱自主规划** — 主流程由模板固化，确保结果可复现
2. **强流程约束** — 每个 Skill 有明确 Schema，状态机控制流转
3. **能用规则不用 LLM** — BM25、别名匹配、NIL 阈值均为纯规则。LLM 仅作为可选按需兜底
4. **可溯源可审计** — 每一步留痕（原值→新值→依据），支持回放和回滚
    """,
    version="0.1.0",
    lifespan=lifespan,
)

# 注册路由
app.include_router(router)


@app.get("/", tags=["根目录"])
async def root():
    """根目录，返回服务基本信息"""
    return {
        "name": "实体链接与知识对齐智能体",
        "version": "0.1.0",
        "description": "面向数据治理场景的实体链接系统",
        "docs": "/docs",
        "health": "/health",
    }


def main():
    """启动服务"""
    uvicorn.run(
        "elagent.main:app",
        host=config.host,
        port=config.port,
        reload=config.debug,
    )


if __name__ == "__main__":
    main()
