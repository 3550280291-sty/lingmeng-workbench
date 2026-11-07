# 灵梦工作台 (Lingmeng Workbench)

> **寻找最优解，是灵梦的唯一直觉**  
> 100% 离线、物理级隐私隔离的供应链智能业务工作台。专注调拨对账、供应商比选、合规性审查、专业报告生成与原生可编辑 Office PPT 演示文稿生成。

---

## 🌟 核心业务流水线

灵梦工作台基于现代化 **Bento Grid** 便当盒矩阵构建，提供五大开箱即用的供应链与政企核心流水线：

| 业务模块 | 核心能力 | 交付物 |
|---|---|---|
| **调拨对账汇总** | 智能跨期对账、智能识别前 15 行真实表头、支持多列自定义比对与浮点容差比对，自动标记账实差异与未到货明细 | 标红/标绿差异对比表、汇总对账单 (`.xlsx`) |
| **供应商比选/比价** | 支持未税/含税价（3%、6%、9%、13%）统一基准折算，30/60/90天账期资金占用成本贴现，4D 综合加权评分（商务/交期/付款/质量）与履约排查 | 供应商综合比价矩阵 (`.xlsx`)、决策汇报 PPT (`.pptx`) |
| **合规性审查** | 支持合同、采购寻源流程、招投标文件、报销与供应商准入合规审查。内置 6 大核心标准开关，支持大尺寸逐条自定义审查标准输入器，强弱视觉红黄绿灯风险排查 | 审查意见书 (`.docx`)、合规审查汇报 PPT (`.pptx`) |
| **写专业报告** | 支持短报告与全景深度长报告，结合内置知识库与行业公文标准分章节撰写，严格统一中文字体（微软雅黑）与排版规范 | 标准专业报告 (`.docx`) |
| **生成演示 PPT** | 7 套标准母版版式、文本精简公文规范（超长公文智能压缩至 <=30 字并注入演讲者备注）、**原生 Office 动态可编辑矢量图表（柱状图/折线图/饼图）**，非静态截图 | 演示文稿 (`.pptx`) |

---

## 🔒 隐私与安全承诺 (Local-First Architecture)

- **100% 本机离线运行**：所有计算、解析与大模型推理均在本机内存与处理器中执行，文件与数据绝不离开当前电脑。
- **物理级数据隔离**：本地 SQLite 数据库独立存储于 `data/` 目录，生成的交付成果独立存放于 `output/` 目录。
- **免登录、零云端外泄**：无需注册账号、无需上传云端服务器，保障企业商业机密与财务核心数据安全。

---

## 🚀 极速启动与桌面体验

- **0.5 秒极速响应**：Web 服务秒开监听 `127.0.0.1:7860`，大模型后台独立线程异步预热，彻底告别启动卡顿。
- **全局单实例防多开**：内置系统级命名互斥锁与端口验活，连击仅唤醒已有窗口，绝不重复生成多余后台进程。
- **纯净无边框桌面窗口**：调用系统原生 Edge/WebView2 渲染，沉浸式极简无标签栏设计，优雅居中。

---

## 🛠️ 安装与运行指南

### 1. 环境准备
- **操作系统**：Windows 10 / 11 (64-bit)
- **Python 版本**：Python 3.10 或更高版本
- **系统组件**：Microsoft Edge / WebView2（Windows 10/11 已内置）

### 2. 克隆与安装依赖

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/lingmeng-workbench.git
cd lingmeng-workbench

# 创建并激活虚拟环境 (推荐)
python -m venv .venv
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 一键启动
在项目根目录下，直接双击运行：
- **`启动灵梦工作台.bat`**
- 或在终端中执行：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\launch.ps1
  ```

---

## 📁 项目目录结构

```text
lingmeng-workbench/
├── app/
│   ├── webapp.py            # FastAPI 异步后台服务与 REST/SSE 接口
│   ├── core.py              # 业务逻辑调度、文档生成与模板引擎
│   ├── calc_engine.py       # 对账、比价、合规审查与图表数据萃取引擎
│   ├── desktop.py           # 原生桌面窗口宿主与单实例控制器
│   └── web/
│       ├── index.html       # 黄金比例 Bento Grid 响应式界面
│       ├── style.css        # Apple 暖白质感设计系统与流畅微动效
│       └── app.js           # 前端数据驱动控制器与交互逻辑
├── tests/
│   ├── mock_data/           # 15 项真实供应链合成测试用例 (.xlsx, .docx, .json)
│   ├── auto_business_eval.py# 15 项全量业务场景自动化评测套件 (15/15 PASS)
│   ├── test_frontend_refactor.py # 前端与布局自动化回归测试
│   └── test_async_startup_and_single_instance.py # 极速启动与单实例单测
├── data/                    # [本地运行时自动生成] 本地数据库与日志 (已加入 .gitignore)
├── output/                  # [本地运行时自动生成] 导出的 Excel/Word/PPT 成果 (已加入 .gitignore)
├── models/                  # [可选] 本地 GGUF 离线模型权重存放目录 (已加入 .gitignore)
├── launch.ps1               # 智能探测环境并启动应用的 PowerShell 脚本
├── 启动灵梦工作台.bat        # Windows 快捷启动入口
├── 启动灵梦工作台.vbs        # 静默无控制台黑框启动脚本
├── 灵梦-v6.ico              # 灵梦黑金星芒高清矢量图标
├── requirements.txt         # Python 依赖清单
├── .gitignore               # 严格隐私过滤规则 (防数据外泄)
└── README.md                # 项目文档
```

---

## 🧪 自动化评测与测试验证

本项目内置了全套高标准的自动化测试套件与业务回归测试：

```bash
# 运行全部 39 项单元与架构验证测试 (39/39 PASS)
python -m unittest discover -s tests -p "test_*.py"

# 运行 15 项真实供应链业务场景评测 (对账/比价/合同/PPT/极限表格, 15/15 PASS)
python tests/auto_business_eval.py

# 运行全链路系统自检脚本 (17/17 Chapters PASS)
python test_suite.py
```

---

## 📄 开源许可与声明

本项目仅供学习、研究与企业本地化离线生产力辅助使用。请妥善保管好您的本地数据与自定义业务模板。
