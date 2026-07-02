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
    面向数据治理场景的实体链接系统。

    ## 接口速览

    | 接口 | 功能 |
    |---|---|
    | `POST /link` | 实体链接（核心） |
    | `POST /nil_check` | NIL检测 |
    | `POST /coref` | 共指消解 |
    | `GET /trace/{id}` | 追溯查询 |
    | `POST /trace/{id}/replay` | 追溯回放 |

    ## 调用关系

    本智能体作为数据治理流水线中的专项能力，可被归一智能体和清洗智能体按需调用。
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
