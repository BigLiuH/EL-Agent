# ELAGENT - 实体链接与知识对齐智能体

面向数据治理场景的实体链接系统。给定文本中的实体指称（mention），将其链接到知识库中的标准实体，完成消歧、别名标准化、NIL检测与共指消解。

五项指标全部达标：链接 **98.92%** / 消歧 **90.85%** / 别名 **99.00%** / 共指 **94.3%** / NIL **83.18%**。

---

## 目录

- [架构](#架构)
- [核心能力](#核心能力)
- [快速开始](#快速开始)
- [API接口](#api接口)
- [评测](#评测)
- [项目结构](#项目结构)
- [技术栈](#技术栈)
- [数据集](#数据集)
- [评测结果](#评测结果)

---

## 架构

```
输入: 文本 + mention + 实体类型
         │
         ▼
┌─────────────────────────────────────────────────┐
│ 1. 标准名称精确匹配                               │
│    → 命中则返回，置信度 1.0                        │
└─────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─────────────────────────────────────────────────┐
│ 2. 别名精确匹配                                  │
│    ├─ 单候选 → 置信度 0.95                        │
│    └─ 多候选 → 消歧器 5信号评分 → LLM兜底          │
└─────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─────────────────────────────────────────────────┐
│ 3. 模糊匹配（名称包含关系）                        │
│    → 消歧器评分                                   │
└─────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─────────────────────────────────────────────────┐
│ 4. BM25 全文检索                                  │
│    → 消歧器评分                                   │
└─────────────────────────────────────────────────┘
         │ 未命中
         ▼
┌─────────────────────────────────────────────────┐
│ 5. NIL 声明                                       │
│    → 知识库中不存在该实体                          │
└─────────────────────────────────────────────────┘
```

### 消歧器 5 信号

| 信号 | 权重 | 说明 |
|---|---|---|
| 名称匹配 | 0.15 | 精确/别名/包含匹配评分 |
| 先验概率 | 0.15 | cbrt压缩，中频实体差距最小化 |
| 名称完整度 | 0.09 | 全称优先，过度细化惩罚 |
| 类型一致性 | 0.15 | PER/ORG/LOC/EVENT过滤 |
| 领域匹配 | 0.10 | 2+3gram区分词命中密度 |

### 共指消解

代词/指代词 → 最近同类型非指代 mention 规则回链。

```python
"她" → 前文 PER 实体    "本次赛事" → 前文 EVENT 实体
"该队" → 前文 ORG 实体   "该地区" → 前文 LOC 实体
```

---

## 核心能力

| 能力 | 说明 | 准确率 |
|---|---|---|
| **实体链接** | mention → 标准实体ID | 98.92% |
| **消歧** | 同名异指区分 | 90.85% |
| **别名标准化** | 简称/别名 → 标准全称 | 99.00% |
| **共指消解** | 代词/指代词回链 | 94.3% |
| **NIL检测** | 知识库不存在实体识别 | 83.18% |
| **可追溯** | 每一步保留原值→新值→依据 | ✅ |

---

## 快速开始

### 环境要求

- Python 3.11+
- Conda（推荐）

### 安装

```bash
conda create -n el-agent python=3.11
conda activate el-agent
pip install -r requirements.txt
```

### 启动服务

```bash
python -m elagent.main
```

服务启动后访问 `http://localhost:8000/docs` 查看 API 文档。

### 测试链接

```bash
curl -X POST http://localhost:8000/link \
  -H "Content-Type: application/json" \
  -d '{
    "text": "中国羽毛球队在2024年世锦赛上夺得冠军",
    "mention": {
      "text": "世锦赛",
      "start_pos": 14,
      "end_pos": 17,
      "entity_type": "EVENT"
    }
  }'
```

---

## API接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/kb/stats` | 知识库统计 |
| POST | `/link` | 单条实体链接 |
| POST | `/batch_link` | 批量实体链接 |
| GET | `/trace/{trace_id}` | 查询追溯日志 |
| GET | `/traces` | 列出最近的追溯日志 |

---

## 评测

```bash
# 实体链接评测（链接+消歧+别名）
python scripts/evaluate_full.py

# NIL 检测评测
python scripts/evaluate_nil.py

# 共指消解评测
python scripts/evaluate_coref.py

# 全功能评测（含共指消解）
python scripts/evaluate_all.py --no-coref  # 跳过共指
```

---

## 项目结构

```
ELAGENT/
├── elagent/                        # 核心系统
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 系统配置
│   ├── api/
│   │   ├── routes.py               # 核心管道 _enhanced_link()
│   │   └── schemas.py              # Pydantic 模型
│   ├── core/
│   │   ├── knowledge_base.py       # 知识库加载
│   │   ├── disambiguator.py        # 消歧器（5信号评分+domain）
│   │   ├── coref_resolver.py       # 共指消解
│   │   ├── bm25_index.py           # BM25 全文索引
│   │   ├── llm_disambiguator.py    # LLM 消歧兜底
│   │   ├── nil_detector.py         # NIL 检测器
│   │   └── trace_logger.py         # 追溯日志
│   └── models/
│       ├── mention.py              # Mention 模型
│       ├── entity.py               # Entity / Candidate
│       └── result.py               # LinkResult
├── Dataset/
│   ├── knowledge_base_merged.json  # 知识库（6,420 实体）
│   ├── aliases_merged.json         # 别名映射（8,452 条）
│   └── llm_extracted_merged.json   # 标注文章（1,239篇）
├── scripts/
│   ├── evaluate_full.py            # 实体链接评测
│   ├── evaluate_nil.py             # NIL 检测评测
│   ├── evaluate_coref.py           # 共指消解评测
│   └── rebuild_aliases_from_kb.py  # 别名文件重建
├── docs/
│   ├── technical_report.md         # 技术报告
│   └── failure_analysis.md         # 错误分析
├── tests/
├── requirements.txt
└── README.md
```

---

## 技术栈

| 组件 | 选型 |
|---|---|
| 框架 | FastAPI |
| BM25 | rank-bm25 + jieba |
| 分词 | jieba |
| LLM | OpenRouter API（可选） |
| 存储 | JSON |

---

## 数据集

| 文件 | 内容 |
|---|---|
| `knowledge_base_merged.json` | 6,420 个体育领域实体 |
| `aliases_merged.json` | 8,452 条别名映射 |
| `llm_extracted_merged.json` | 1,239 篇文章，40,942 条标注 mention |

实体类型分布：PER 3,133 / ORG 1,495 / EVENT 1,306 / LOC 1,115

数据集覆盖运动：羽毛球、乒乓球、游泳、田径、斯诺克、足球、篮球等。

---

## 评测结果

### 五项指标

| 指标 | 数值 | 目标 | 状态 |
|---|---|---|---|
| 链接准确率 | **98.92%** | ≥85% | ✅ |
| 消歧准确率 | **90.85%** | ≥85% | ✅ |
| 别名召回率 | **99.00%** | ≥85% | ✅ |
| 共指消解 | **94.3%** | ≥80% | ✅ |
| NIL 检测 | **83.18%** | ≥80% | ✅ |

### 高频错误 Top 10（去重后）

| mention | 次数 | 预期 | 预测 |
|---|---|---|---|
| 世锦赛 | 3 | 世界羽毛球锦标赛 | 世界游泳锦标赛 |
| 总决赛 | 2 | NBA总决赛/CBA总决赛 | 总决赛 |
| 亚锦赛 | 2 | 亚洲羽毛球锦标赛 | 亚锦赛 |
| WTT卢布尔雅那 | 2 | 多个WTT赛事变体 | — |

---

## 许可证

本项目仅用于学术研究和实训目的。

## 致谢

- 数据治理与数据预处理工厂项目
- 龙骑团小组
