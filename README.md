# 实体链接与知识对齐智能体

面向数据治理场景的实体链接系统，用于将文本中的实体指称链接到知识库中的标准实体。

## 项目概述

本系统是数据治理流水线中的**专项能力智能体**（课题10），在归一环节承担核心实体对齐能力。

### 核心功能

- **候选实体检索**: 多路召回（BM25 + 别名词典 + 向量检索）
- **上下文消歧**: 分层消歧（类型过滤 + 名称最短优先）
- **实体标准化**: 别名/简称/曾用名 → 标准全称 + 唯一ID
- **NIL检测**: 多信号融合判定，正确识别知识库中不存在的实体
- **全程可追溯**: 原值 → 新值 → 依据，支持回放与回滚

### 设计理念

与通用实体链接工具的三大区别：

1. **弱自主规划**: 主流程由模板固化，确保结果可复现
2. **强流程约束**: 每个Skill有明确Schema，状态机控制流转
3. **能用规则不用LLM**: BM25、别名匹配、NIL阈值均为纯规则

---

## 快速开始

### 环境要求

- Python 3.11+
- Conda (推荐)
- GPU (可选，用于向量检索)

### 安装

```bash
# 创建conda环境
conda create -n el-agent python=3.11
conda activate el-agent

# 安装依赖
pip install -r requirements.txt

# 安装GPU版本torch（可选）
pip install torch --index-url https://download.pytorch.org/whl/cu124
```

### 启动服务

```bash
# 直接启动
python -m elagent.main

# 或者使用uvicorn
uvicorn elagent.main:app --reload --host 0.0.0.0 --port 8000
```

服务启动后，访问 http://localhost:8000/docs 查看API文档。

### 测试链接

```bash
# 健康检查
curl http://localhost:8000/health

# 知识库统计
curl http://localhost:8000/kb/stats

# 实体链接
curl -X POST http://localhost:8000/link \
  -H "Content-Type: application/json" \
  -d '{
    "text": "宁夏体育馆举办比赛",
    "mention": {
      "text": "宁夏",
      "start_pos": 0,
      "end_pos": 2,
      "entity_type": "LOC"
    }
  }'

# 查询追溯日志
curl http://localhost:8000/trace/{trace_id}
```

---

## 项目结构

```
ELAGENT/
├── elagent/                    # 主代码
│   ├── main.py                 # FastAPI入口
│   ├── config.py               # 配置管理
│   ├── models/                 # 数据模型
│   │   ├── mention.py          # 指称模型
│   │   ├── entity.py           # 实体模型
│   │   └── result.py           # 结果模型
│   ├── core/                   # 核心模块
│   │   ├── knowledge_base.py   # 知识库管理
│   │   ├── bm25_index.py       # BM25索引
│   │   ├── vector_index.py     # 向量索引
│   │   ├── disambiguator.py    # 消歧器
│   │   ├── nil_detector.py     # NIL检测器
│   │   └── trace_logger.py     # 追溯日志
│   └── api/                    # API接口
│       ├── routes.py           # 路由定义
│       └── schemas.py          # 请求/响应模型
├── Dataset/                    # 原始数据
│   ├── knowledge_base_merged.json
│   ├── aliases_merged.json
│   └── llm_extracted_merged.json
├── data/                       # 处理后的数据
│   ├── fixed_chinese/          # 中文修复后的数据
│   ├── merge_candidates.json   # 合并候选
│   └── evaluation_report.md    # 评测报告
├── docs/                       # 文档
│   ├── failure_analysis.md     # 失败案例分析
│   └── technical_report.md     # 技术报告
├── scripts/                    # 脚本
│   ├── evaluate_articles.py    # 评测脚本
│   ├── generate_report.py      # 报告生成
│   └── fix_annotations.py      # 数据修复
├── tests/                      # 测试
├── requirements.txt            # 依赖
└── README.md                   # 本文件
```

---

## API接口

### 系统接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 根目录 |
| GET | `/health` | 健康检查 |
| GET | `/docs` | API文档 |

### 知识库接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/kb/stats` | 知识库统计 |

### 实体链接接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/link` | 单条实体链接 |
| POST | `/batch_link` | 批量实体链接 |

### 追溯接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/trace/{trace_id}` | 查询追溯日志 |
| GET | `/traces` | 列出最近的追溯日志 |

---

## 评测结果

### 核心指标

| 指标 | 值 |
|------|-----|
| **准确率** | 84.45% |
| **精确率** | 100% |
| **召回率** | 100% |
| **F1分数** | 100% |
| **平均延迟** | 0.01 ms |

### 错误分析

| 错误类型 | 数量 | 占比 |
|---------|------|------|
| 全称/简称混淆 | 6134 | 96.3% |
| 队伍/组合混淆 | 134 | 2.1% |
| 年份变体混淆 | 64 | 1.0% |
| 中英文对照混淆 | 36 | 0.6% |

---

## 评测方法

```bash
# 运行评测
python scripts/evaluate_articles.py

# 生成评测报告
python scripts/generate_report.py
```

---

## 数据集

本项目使用以下数据集：

- `knowledge_base_merged.json`: 知识库（7049个实体）
- `aliases_merged.json`: 别名词典（8461个别名）
- `llm_extracted_merged.json`: 标注文章（1239篇，40942个mention）

实体类型分布：
- PER（人物）: 3133
- ORG（组织）: 1495
- EVENT（事件）: 1306
- LOC（地点）: 1115

---

## 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Web框架 | FastAPI | 异步、自动OpenAPI文档 |
| BM25 | rank-bm25 | 全文检索 |
| 向量检索 | FAISS + m3e-base | 语义相似度 |
| 分词 | jieba | 中文分词 |
| 存储 | JSON + 文件 | 轻量级 |

---

## 交付物清单

| 交付物 | 路径 | 说明 |
|--------|------|------|
| 可运行代码 | elagent/ | 完整的实体链接系统 |
| 评测报告 | data/evaluation_report.md | 量化指标与分析 |
| 失败案例分析 | docs/failure_analysis.md | 典型错误分析 |
| 技术报告 | docs/technical_report.md | 方法选型与实现 |
| 部署说明 | README.md | 本文档 |

---

## 许可证

本项目仅用于学术研究和实训目的。

## 致谢

- 数据治理与数据预处理工厂项目
- 龙骑团小组
