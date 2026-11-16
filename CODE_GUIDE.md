# 灵梦工作台 · 代码导读（给第一次看这个项目的人）

> 这份文档不讲“怎么用”，只讲**这个项目是怎么搭起来的、代码该从哪里看起**。  
> 即使你只懂一点点 Python，也能顺着看完。

---

## 0. 一句话理解这个项目

这是一个 **Windows 上运行的本地 AI 办公工作台**：

- 前端是一个网页界面（聊天框 + 业务表单 + 成果预览）；
- 后端是一个本地 Python 服务（FastAPI），负责聊天、文件解析、计算、导出 Office 文档；
- 大模型（Qwen3 GGUF）用 OpenVINO 在本机 CPU 上跑，**不联网、不上传数据**；
- 数据存在本地 SQLite（`data/app.db`），导出的 Excel/Word/PPT 存在 `output/`。

它不是一个“模型训练项目”，而是**把本地大模型 + 确定性计算 + Office 导出，包装成一个业务工具的工程项目**。

---

## 1. 先看哪几个文件（推荐阅读顺序）

| 顺序 | 文件 | 为什么先看它 |
|---|---|---|
| 1 | `README.md` | 项目功能、安装、使用说明 |
| 2 | `CODE_GUIDE.md`（本文） | 整体结构 |
| 3 | `app/webapp.py` | 后端入口：所有 HTTP 接口、聊天主流程 |
| 4 | `app/core.py` | 模型加载、流式生成、PPT/Word/Excel 生成 |
| 5 | `app/calc_engine.py` | 三个核心业务的“确定性计算” |
| 6 | `app/web/app.js` | 前端逻辑：聊天、流式渲染、三个业务向导 |
| 7 | `app/desktop.py` | 桌面窗口（pywebview）与启动流程 |

> 看不懂细节没关系，先记住一句话：**`webapp.py` 管接口，`core.py` 管模型和导出，`calc_engine.py` 管算数，`app.js` 管界面。**

---

## 2. 目录结构

```text
lingmeng-workbench/
├─ app/
│  ├─ webapp.py        # 后端主程序：FastAPI 路由 + 聊天 SSE + 文件上传 + 导出
│  ├─ core.py          # 大模型加载/推理、流式输出、Word/PPT/Excel 模板生成
│  ├─ calc_engine.py   # 确定性计算：对账汇总、供应商比价/TCO、合同/合规审查
│  ├─ desktop.py       # 桌面壳：启动本地服务 + pywebview 窗口
│  └─ web/
│     ├─ index.html    # 页面结构（聊天、设置抽屉、三个业务向导）
│     ├─ style.css     # 全部样式
│     └─ app.js        # 前端逻辑（最大、最核心的前端文件）
├─ data/               # 运行时数据（数据库、上传文件、备份）—— 不进 Git
├─ models/             # 本地 GGUF 模型 —— 不进 Git
├─ output/             # 生成的 Excel/Word/PPT —— 不进 Git
├─ tests/              # 自动化测试 + 合成业务样例（mock_data）
├─ test_*.py           # 各阶段测试脚本（根目录）
├─ launch.ps1          # Windows 启动脚本（单实例、激活窗口）
├─ requirements.txt    # Python 依赖
└─ README.md / CODE_GUIDE.md
```

### 为什么 `data/`、`models/`、`output/` 是空的？
Git 仓库只放**代码**。数据库、你的业务文件、模型权重都很大且涉及隐私，所以在 `.gitignore` 里被排除了，只保留 `.gitkeep` 占位。

---

## 3. 技术栈

| 层 | 技术 | 作用 |
|---|---|---|
| 后端 Web | FastAPI + Uvicorn | 提供 `/api/*` 接口、SSE 流式返回 |
| 模型推理 | OpenVINO GenAI + GGUF | 在本机 CPU 上跑 Qwen3 |
| 桌面窗口 | pywebview（WebView2） | 把网页包成桌面应用 |
| 数据库 | SQLite | 会话、消息、文件、记忆、提示词 |
| 表格/文档 | pandas + openpyxl | 读取 Excel、确定性计算、导出 xlsx |
| Word/PPT | python-docx + python-pptx | 生成 docx / pptx（含原生图表） |
| PDF/文本 | PyMuPDF + pypdf | 读取合同、报告等文档 |
| 前端 | 原生 HTML/CSS/JS | 无框架，单页应用 |

---

## 4. 启动时发生了什么

以 `app/desktop.py` 为例：

```text
launch.ps1
  └─ 启动 pythonw app/desktop.py
       ├─ 创建/检查单实例（app.lock、端口 7860、窗口）
       ├─ 起一个后台线程：uvicorn 运行 webapp.app（本地 127.0.0.1:7860）
       ├─ 后台线程加载模型（core.warmup → get_pipe）
       └─ pywebview 打开 127.0.0.1:7860 的桌面窗口
```

如果不用桌面窗口，也可以直接：

```bash
python app/webapp.py
# 然后浏览器打开 http://127.0.0.1:7860
```

---

## 5. 一次聊天请求的完整链路

```text
浏览器输入一句话
   │
   ▼
app.js  send()  →  POST /api/chat（SSE 流式）
   │
   ▼
webapp.py  api_chat()
   ├─ 保存用户消息（SQLite messages 表）
   ├─ 取出历史消息 + 模式提示词（MODES）+ 文件内容
   ├─ 调用 calc_engine 做“预计算”（表格统计/对账/比价等）
   └─ 起一个后台线程 → core.generate_stream(...)
          │
          ▼
      OpenVINO 逐 token 生成
          │  通过 queue 回传
          ▼
   webapp.py 组装成 SSE：data: {"type":"delta","text":"..."}
          │
          ▼
app.js 收到 delta，实时渲染文字
          │
          ▼
   done 事件 → 保存助手消息 + artifact（成果文件信息）
```

关键点：
- **流式（SSE）**：模型一边生成一边显示，不是等全部生成完；
- **思考内容**：如果模型输出 `<think>...</think>`，前端会折叠成“已深度推演”；
- **停止**：`/api/chat/stop` 设置取消事件，生成线程会尽快退出；
- **成果 artifact**：生成的 Excel/Word/PPT 会通过 SSE 推给前端，在右侧成果舱展示。

---

## 6. 三个核心业务在代码里怎么实现

这三个业务不是“让模型自由发挥”，而是 **先由 Python 做确定性计算，再让模型组织语言/生成文档**。

### 6.1 调拨对账汇总

| 环节 | 代码 |
|---|---|
| 识别表头/读取多表 | `calc_engine.read_dataframes_from_file()`、`detect_excel_header_row()` |
| 汇总计算 | `calc_engine.precompute_tables_summary()` |
| 对账审计 | `calc_engine.generate_reconciliation_audit()` |
| 导出汇总 Excel | `calc_engine.generate_summary_excel()` |
| 前端向导 | `app.js` 的 `openReconcilePipeline()` |
| 后端接口 | `/api/calc/reconcile_fields`、`/api/calc/reconcile_audit`、`/api/calc/summary` |

### 6.2 供应商比选 / 比价（TCO）

| 环节 | 代码 |
|---|---|
| 比价计算（含税/未税、账期、TCO、四维评分） | `calc_engine.calculate_supplier_price_comparison()` |
| 导出 Excel 比价表 | `calc_engine.generate_price_tco_excel()` |
| 导出 PPT 汇报（原生图表） | `calc_engine.generate_price_tco_ppt()` |
| 前端向导 | `app.js` 的 `openPricePipeline()` |
| 后端接口 | `/api/calc/price_compare`、`/api/calc/price_export`、`/api/calc/price_ppt` |

### 6.3 合规性 / 合同审查

| 环节 | 代码 |
|---|---|
| 条款库 + 风险分析 | `calc_engine.analyze_contract_full()`、`analyze_contract_risks()` |
| 生成 Word 审查报告 | `calc_engine.generate_contract_review_docx()` |
| 生成 PPT 汇报 | `calc_engine.generate_contract_review_pptx()` |
| 前端向导 | `app.js` 的 `openReviewPipeline()` |
| 后端接口 | `/api/calc/contract_review`、`/api/calc/compliance_review`、`/api/calc/*_export` |

> 为什么强调“确定性”？因为金额、合计、差额这些不能靠大模型口算；大模型只负责解释和建议，数字由 Python 算。

---

## 7. 数据库里有什么

SQLite 文件：`data/app.db`（首次启动自动建表）

| 表 | 存什么 |
|---|---|
| `conversations` | 会话（id、标题、模式、时间） |
| `messages` | 消息（角色、内容、meta JSON、时间） |
| `files` | 上传文件（路径、文本、字符数） |
| `chunks` | 文件切块（用于本地检索） |
| `memories` | 长期记忆 |
| `mode_prompts` | 用户自定义的模式提示词 |

---

## 8. 怎么在本机跑起来

### 环境
- Windows 10/11 64 位
- Python 3.10+（推荐 3.12）
- 建议 16GB 以上内存

### 步骤

```bash
# 1. 装依赖
pip install -r requirements.txt
pip install openvino-genai        # 模型推理需要（requirements 里是可选注释）

# 2. 放模型：把 GGUF 文件放到 models/ 目录
#    例如 Qwen3-8B-Q4_K_M.gguf

# 3. 启动（二选一）
python app/desktop.py             # 桌面窗口
# 或
python app/webapp.py              # 浏览器打开 http://127.0.0.1:7860
```

模型路径、端口、输出目录都可以用环境变量覆盖：
`QWEN_MODEL_DIR`、`QWEN_PORT`、`QWEN_OUT`、`QWEN_DEVICE`（默认 CPU）。

---

## 9. 测试怎么跑

```bash
python test_suite.py                  # 核心功能自检
python test_phase3_pipelines.py       # 比价/合同流水线测试
python tests/auto_business_eval.py    # 业务样例评测（15 个场景）
```

测试用的样例表格/合同在 `tests/mock_data/`，都是**合成数据**，不包含真实业务数据。

---

## 10. 如果想加一个新功能，改哪里？

以“新增一个业务模式”为例：

1. `app/webapp.py` 的 `MODES` 列表加一项（id、名称、提示词）；
2. 前端 `app/web/index.html` 加卡片/入口，`app.js` 加点击逻辑；
3. 如果涉及计算：在 `app/calc_engine.py` 写确定性函数；
4. 如果涉及导出：在 `app/core.py` 写 docx/pptx/xlsx 生成函数；
5. 加对应 `/api/calc/...` 接口（`webapp.py`）；
6. 在 `test_*.py` 里加测试。

---

## 11. 隐私边界（很重要）

- 仓库里**没有**：数据库、上传文件、生成成果、模型权重、运行环境；
- 这些都在本机 `data/`、`output/`、`models/`，并被 `.gitignore` 排除；
- 程序运行时不访问云端，模型推理、文件解析、导出全部在本机完成。

---

## 12. 术语小抄

| 术语 | 大白话 |
|---|---|
| FastAPI | Python 的 Web 框架，负责提供接口 |
| SSE | 服务器一边生成一边往浏览器推文字 |
| OpenVINO GenAI | Intel 的本地模型推理框架 |
| GGUF | 一种量化后的大模型文件格式 |
| SQLite | 单文件数据库，不需要装数据库服务 |
| pywebview | 把网页变成桌面窗口的库 |
| artifact | 生成的成果文件（Excel/Word/PPT） |

---

## 13. 给“完全不想读代码”的人

你只需要知道三件事：

1. **界面**在 `app/web/`（HTML/CSS/JS）；
2. **服务**在 `app/webapp.py`（接口）、`app/core.py`（模型与导出）、`app/calc_engine.py`（算数）；
3. **数据**在本机 `data/` 和 `output/`，不会上传。

想跑起来：装依赖 → 把模型放进 `models/` → 运行 `python app/desktop.py`。
