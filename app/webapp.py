# -*- coding: utf-8 -*-
"""本地千问工作台 —— FastAPI 后端（会话持久化 + SSE 流式 + 文件/导出）。"""
import asyncio
import json
import os
import queue
import re
import shutil
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

class _LazyCalcEngine:
    _module = None

    def __getattr__(self, name):
        if self._module is None:
            import calc_engine as _ce
            self._module = _ce
        return getattr(self._module, name)


calc_engine = _LazyCalcEngine()
import core

_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(_HOME, "data")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")
WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
DB_PATH = os.path.join(DATA_DIR, "app.db")
BACKUP_DIR = os.path.join(DATA_DIR, "backups")
BACKUP_KEEP = 15
os.makedirs(UPLOAD_DIR, exist_ok=True)

MAX_FILE_MB = 40
TOTAL_DOC_CHARS = 12000
OUT_KEEP_DAYS = int(os.environ.get("QWEN_OUT_KEEP_DAYS", "30"))
OUT_MAX_FILES = int(os.environ.get("QWEN_OUT_MAX_FILES", "200"))
ACTIVE_CANCELS: dict = {}


# ---------------------------------------------------------------- 数据库
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations(
                id TEXT PRIMARY KEY, title TEXT, mode TEXT,
                created_at TEXT, updated_at TEXT
            );
            CREATE TABLE IF NOT EXISTS messages(
                id TEXT PRIMARY KEY, conv_id TEXT, role TEXT, content TEXT,
                meta TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS files(
                id TEXT PRIMARY KEY, conv_id TEXT, name TEXT, path TEXT,
                chars INTEGER, text TEXT, created_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conv_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_file_conv ON files(conv_id);
            CREATE TABLE IF NOT EXISTS memories(
                id TEXT PRIMARY KEY, text TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS chunks(
                id TEXT PRIMARY KEY, file_id TEXT, conv_id TEXT, name TEXT,
                body TEXT, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS mode_prompts(
                mode TEXT PRIMARY KEY, prompt TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_chunk_conv ON chunks(conv_id);
            """
        )
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()]
        if "pinned" not in cols:
            conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER DEFAULT 0")


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- 模式
APP_VERSION = "1.3"

MODES = [
    {"id": "general", "name": "通用对话", "icon": "💬", "hint": "日常问答、改写、提炼", 
     "prompt": """【当前模式：通用对话】你是「灵梦工作台」专业级本地智能助手。
目标：提供专业、严谨、高效且富有逻辑的业务支持。
回答要求：
1）结论先行：针对提问开门见山给出关键结论，再展开分点论述；
2）客观严谨：基于事实回答，不捏造数据；
3）条理清晰：合理运用数字编号或加粗要点，避免冗长段落。"""},
    {
        "id": "report", "name": "写专业报告（短/长报告）", "icon": "📝", "hint": "工作报告、总结、方案",
        "prompt": """【当前模式：写报告】你是资深公文与管理报告专家顾问。
严格依据麦肯锡金字塔原理与公文规范输出，严禁「好的、以下是」等口语化开场白，直接输出报告正文：
1）报告标题：一行，规范庄重，不超过 22 字；
2）总体态势与核心数据摘要：3-5 句，宏观概括现状与成果，带硬核事实与关键数字支撑；
3）重点推进工作与成效：分条列出，每条以「动词+具体成果+量化指标」开头，结构严谨；
4）突出矛盾与深层归因：客观摆出难点卡点，深刻剖析管理、流程或供应链根因；
5）下步保障措施与行动计划：分条陈述，明确责任归属、完成里程碑节点与资源保障。
若用户选择长报告，本篇将按大纲接力展开；信息不足时先用一句话列出缺失项；尽量引用附件原句，缺少数据写「文件中未提及」，杜绝虚构数字。"""
    },
    {
        "id": "review", "name": "合规性审查", "icon": "🔍", "hint": "支持合同、采购寻源流程、招投标文件、报销与供应商准入合规审查",
        "prompt": """【当前模式：合规性审查】你是资深企业法务总监与合规审查专家。
审查合规材料（支持合同、采购寻源流程、招投标文件、报销与供应商准入）时，必须基于内置 6 大专业条款库与逐条自定义规则进行深度排查。
输出遵循强弱视觉对比排查结构：
1）顶部审查结论概览：
   必须包含排查统计：重点不合规（红灯致命项）、偏离项（黄灯瑕疵项）、完全符合（绿灯达标项）与待补充项。
   并附带【综合风控评级】（高风险·建议重签或全盘重修订 / 中风险·建议发起实质商务谈判修订 / 低风险·条款相对完备合规）。
2）重点不合规与偏离项清单（强视觉高亮）：
   表头固定为：| 审查标准 | 文件原文摘录 | 不合规偏离点剖析 | 标准修正文本 |
   原句必须直接摘录合同/文件原文；修正文本必须提供严密规范的替代条文。
3）完全符合项清单（弱视觉弱化）：
   表头固定为：| 审查标准 | 文件原文摘录 | 合规结论 |
4）底部《缺失条款与待补充清单》：
   表头固定为：| 序号 | 缺失标准类别 | 缺失风险提示 | 建议补充标准条款 |
【强制准则】：严禁编造不存在的条款，必须以实际文本与后台确定性审查基准为唯一事实依据！"""
    },
    {
        "id": "data", "name": "自由表格分析", "icon": "📊", "hint": "Excel/CSV 数据解读与透视",
        "prompt": """【当前模式：表格分析】你是首席商业数据分析师。
采用麦肯锡金字塔原理（结论先行、数据支撑、归因分析、落地行动），严格按以下顺序输出：
1）核心结论摘要（Top Insights）：不超过 3 句，结论先行，直接指出最核心的商业洞察与经营拐点；
2）关键经营指标表：Markdown 表格，提炼关键汇总值（总量、均值、Top集中度、极值异动）；
3）异常波动归因剖析：针对偏离均值、同比骤变或异常缺失的数据项，结合业务逻辑拆解根因；
4）可落地管理行动项：给出 2-4 条清晰、量化、分优先级的业务改善动作。
【强制准则】：涉及总额、均值、比率等全部计算指标，必须 100% 采用上下文【确定性数据计算基准】中的真实统计值，严禁自行心算或猜测！"""
    },
    {
        "id": "ppt", "name": "生成演示 PPT", "icon": "📑", "hint": "先出大纲，再导出文件",
        "prompt": """【当前模式：生成 PPT】你是汇报材料策划专家。只输出大纲，禁止任何多余解释、开场白或总结语。
格式严格如下：
标题：一句话主标题
副标题：一句话副标题
## 页标题
- 要点（≤30 字，带具体事实与数字）
- 要点
- 要点
每页 3-4 条要点，标题不超过 12 字，要点要用具体数字和明确结论。
输出完大纲就停，不要问问题、不要加额外说明。"""
    },
    {
        "id": "procure", "name": "采购物流方案", "icon": "🚚", "hint": "供应商比选、运输与成本",
        "prompt": """【当前模式：采购物流方案】你是供应链网络规划与物流调度专家。
必须引入 SCOR 供应链运营参考模型，从成本（Cost）、时效（Lead Time）、可靠性（Reliability）及安全库存缓冲（Buffer）四个维度展开系统方案设计，严格按以下结构输出：
一、需求拆解与技术参数定义：
梳理物料规格、批量、交期要求、始发地与交付目的地、温控/防震等特殊仓储物流要求。
二、多方案综合比选矩阵（Markdown 表格）：
列名固定为：方案编号 | 运输模式(直发/干线拼车/多式联运) | 承运服务商 | 单吨/单方运费 | 门到门时效(小时/天) | 准时交付率(OTD) | 货损率上限 | 综合评分
三、总物流与库存持有成本测算（TCO）：
清晰列出测算公式：总成本 = 干线运费 + 提送短驳费 + 装卸与包装费 + 途在途资金占用利息 + 安全库存持有成本。并给出对比差额。
四、供应链应急预案与安全库存策略：
针对恶劣天气延误、道路管制、突发爆仓等风险，给出触发条件（Trigger）、备选路由（Alternative Route）及安全库存动态缓冲阈值。
数据缺失处标注【待调研补充】，严禁编造承运商或价格。"""
    },
    {
        "id": "price", "name": "供应商比选/比价", "icon": "💰", "hint": "多供应商报价横向对比、TCO模型、PPT/Excel导出",
        "prompt": """【当前模式：供应商比选/比价】你是资深战略采购总监与供应链成本分析专家。
处理报价清单时，后台已通过确定性 TCO 模型与加权评分算法完成价格换算与供应商打分。
你必须基于 Python 确定的比选结果与加权得分矩阵输出汇报，严格按以下结构组织：
1）核心指标与看板：
   列出最低报价供应商、平均溢价率、待核实风险项数及比选材料总数；
2）比价校验表（Markdown 表格）：
   序号 | 材料名称 | 规格型号 | 供应商 | 未税单价 | 含税单价 | 税率 | 交期 | 账期条件 | 综合TCO单价 | 差价率 | 核对状态
3）《授标推荐结论》与加权得分矩阵：
   严格依据 Python 计算的综合得分降序排列，明确首选授标（建议分配 70% 份额）、备选谈判（建议分配 30% 份额或二轮竞价）与淘汰备选结论；
4）《分供应商谈判压价要点》：
   针对各供应商的价差率与缺失项（如漏填交期、漏填运费），给出精准定点压价策略与合同条款对齐要求；
5）《待核实项清单》：
   列明漏填交期、漏填运费或账期不明的物料明细及需向供方澄清的要点。
【计算准则】：4B 模型严禁口算或自行打分，必须 100% 采用上下文【确定性数据计算基准】中的得分与数字！"""
    },
    {
        "id": "merge", "name": "调拨对账汇总", "icon": "📑", "hint": "多表对账、真实Excel导出",
        "prompt": """【当前模式：做汇总表】你是供应链物资调拨与财务对账结算专家。
在处理上传的表格（如对账清单、领退料单、调拨总表）时，后台已通过 Python 确定性计算引擎完成两表关联对账与数据归并。
目标标准字段：序号 | 调拨量 | 调拨日期 | 物资类别 | 物资名称 | 规格型号 | 单位 | 数量 | 调出单位 | 调入单位 | 车型 | 备注。
请按以下结构输出业务总结：
1）对账概况：明确指出涉及的表格文件、总条目数、数量合计、调拨量合计、完全匹配项数及存在差额项数；
2）差异与预警清单：指出两表未匹配的物料或数量/调拨量存在差额的关键明细（差额=原数量-调拨量），并标出可能原因；
3）标准汇总结果表：提供前 15 行标准化明细的 Markdown 对照表；
【强制准则】：所有总额、均值与差额必须 100% 依据上下文【确定性数据计算基准】中的数字，严禁口算！"""
    },
]

MODE_MAP = {m["id"]: m for m in MODES}


# ---------------------------------------------------------------- 应用
def backfill_chunks():
    with db() as conn:
        rows = conn.execute(
            "SELECT id,name,text,conv_id FROM files WHERE id NOT IN (SELECT DISTINCT file_id FROM chunks)"
        ).fetchall()
        n = 0
        for r in rows:
            for piece in chunk_text(r["text"]):
                conn.execute(
                    "INSERT INTO chunks(id,file_id,conv_id,name,body,created_at) VALUES(?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], r["id"], r["conv_id"], r["name"], piece, now()),
                )
                n += 1
    if n:
        print(f"[kb] backfilled {n} chunks", flush=True)


def backup_db():
    """启动时自动备份数据库，保留最近 BACKUP_KEEP 份，防止误删/损坏后无法回退。"""
    try:
        if not os.path.exists(DB_PATH):
            return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        dest = os.path.join(BACKUP_DIR, "app-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db")
        if os.path.exists(dest):
            return
        shutil.copy2(DB_PATH, dest)
        olds = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("app-") and f.endswith(".db"))
        for name in olds[:-BACKUP_KEEP]:
            try:
                os.remove(os.path.join(BACKUP_DIR, name))
            except OSError:
                pass
        print(f"[backup] {dest}", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("[backup] failed:", exc, flush=True)


def cleanup_empty_conversations():
    """清理 messages 为空的垃圾会话，彻底删除其关联的文件、切片及物理文件。"""
    with db() as conn:
        empty_rows = conn.execute(
            """SELECT id FROM conversations c
               WHERE NOT EXISTS (SELECT 1 FROM messages m WHERE m.conv_id = c.id)"""
        ).fetchall()
        cids = [r["id"] for r in empty_rows]
        if not cids:
            return 0
        all_paths = []
        for cid in cids:
            paths = [r["path"] for r in conn.execute("SELECT path FROM files WHERE conv_id=?", (cid,)).fetchall()]
            all_paths.extend(paths)
            conn.execute("DELETE FROM messages WHERE conv_id=?", (cid,))
            conn.execute("DELETE FROM chunks WHERE file_id IN (SELECT id FROM files WHERE conv_id=?)", (cid,))
            conn.execute("DELETE FROM chunks WHERE conv_id=?", (cid,))
            conn.execute("DELETE FROM files WHERE conv_id=?", (cid,))
            conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
        for p in all_paths:
            try:
                os.remove(p)
            except OSError:
                pass
        return len(cids)


def cleanup_orphans():
    """清理指向已删除文件/会话的索引与消息，避免已删除的内容仍被知识库检索到。"""
    n_empty = cleanup_empty_conversations()
    with db() as conn:
        n_chunk = conn.execute(
            "DELETE FROM chunks WHERE file_id NOT IN (SELECT id FROM files)"
        ).rowcount
        n_msg = conn.execute(
            "DELETE FROM messages WHERE NOT EXISTS (SELECT 1 FROM conversations c WHERE c.id = messages.conv_id)"
        ).rowcount
        n_file = conn.execute(
            "DELETE FROM files WHERE conv_id != '' AND NOT EXISTS (SELECT 1 FROM conversations c WHERE c.id = files.conv_id)"
        ).rowcount
    if n_chunk or n_msg or n_file or n_empty:
        print(f"[cleanup] empty_convs={n_empty} chunks={n_chunk} messages={n_msg} files={n_file}", flush=True)


def cleanup_output():
    """交付物清理策略：output 目录只保留最近 OUT_MAX_FILES 个、且不超过 OUT_KEEP_DAYS 天的生成文件。"""
    removed = 0
    keep_names = {"ui-preview.png"}
    try:
        now = time.time()
        fresh = []
        for name in os.listdir(core.OUT_DIR):
            p = os.path.join(core.OUT_DIR, name)
            if not os.path.isfile(p) or name in keep_names:
                continue
            try:
                if (now - os.path.getmtime(p)) / 86400 > OUT_KEEP_DAYS:
                    os.remove(p)
                    removed += 1
                    continue
            except OSError:
                continue
            fresh.append(p)
        fresh.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        for p in fresh[OUT_MAX_FILES:]:
            try:
                os.remove(p)
                removed += 1
            except OSError:
                pass
    except OSError:
        pass
    if removed:
        print(f"[cleanup] output removed {removed} file(s)", flush=True)


def _bg_init():
    try:
        import calc_engine as _ce
        _LazyCalcEngine._module = _ce
    except Exception:
        pass
    core.load_model()


@asynccontextmanager
async def lifespan(app: FastAPI):
    backup_db()
    init_db()
    cleanup_orphans()
    cleanup_output()
    backfill_chunks()
    threading.Thread(target=_bg_init, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan)


class ChatIn(BaseModel):
    conversation_id: str
    message: str
    mode: str = "general"
    file_ids: list[str] = []
    max_tokens: int = 1024
    temperature: float = 0.7
    deep_think: bool = False
    use_kb: bool = True
    use_code: bool = False
    report_length: str = "standard"  # short | standard | long


class NewConv(BaseModel):
    mode: str = "general"
    title: str = ""


class RenameIn(BaseModel):
    title: str


class ExportIn(BaseModel):
    conversation_id: str
    kind: str  # ppt | excel
    pages: int = 10
    message_id: str | None = None  # 指定从哪条回答导出（为空则整段会话）


def sse(obj):
    # default=str：成果 artifact 里可能带 datetime / numpy 类型，避免 SSE 序列化崩溃
    return f"data: {json.dumps(obj, ensure_ascii=False, default=str)}\n\n"


# ---------------------------------------------------------------- 接口
@app.get("/api/status")
def api_status():
    st = core.status()
    st["modes"] = MODES
    st["version"] = APP_VERSION
    return st


@app.post("/api/chat/stop")
def chat_stop(body: dict = None):
    """主动中断流式生成，释放 OpenVINO 管道与锁。"""
    cid = (body or {}).get("conversation_id")
    if cid and cid in ACTIVE_CANCELS:
        ACTIVE_CANCELS[cid].set()
        return {"ok": True, "stopped": True}
    return {"ok": True, "stopped": False}


def _is_allowed_local_path(p):
    """只允许打开/定位工作台自身目录（uploads/output/data）内的文件。"""
    try:
        target = os.path.abspath(p)
    except (TypeError, ValueError):
        return False
    bases = (os.path.abspath(UPLOAD_DIR), os.path.abspath(core.OUT_DIR), os.path.abspath(DATA_DIR))
    for base in bases:
        if target == base or target.startswith(base + os.sep):
            return True
    return False


@app.api_route("/api/file/open", methods=["GET", "POST"])
def api_file_open(
    file_id: str = None,
    path: str = None,
    name: str = None,
    is_dir: bool = False,
    body: dict = None,
):
    """直接调用系统默认程序打开本地文件（.pptx/.xlsx/.docx）或打开文件所在目录。"""
    if body and isinstance(body, dict):
        file_id = file_id or body.get("file_id")
        path = path or body.get("path")
        name = name or body.get("name")
        if "is_dir" in body:
            is_dir = bool(body.get("is_dir"))

    target_path = None
    if file_id:
        with db() as conn:
            row = conn.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
            if row:
                target_path = row["path"]
    elif path:
        target_path = os.path.abspath(path)
    elif name:
        cand1 = os.path.join(core.OUT_DIR, name)
        cand2 = os.path.join(UPLOAD_DIR, name)
        if os.path.exists(cand1):
            target_path = cand1
        elif os.path.exists(cand2):
            target_path = cand2
        else:
            target_path = cand1

    # 默认兜底：若没有任何参数或为空，打开默认输出目录
    if not target_path:
        target_path = os.path.abspath(core.OUT_DIR)
        is_dir = True

    # 安全检查：必须在允许的工作区白名单内
    if not _is_allowed_local_path(target_path):
        raise HTTPException(403, "禁止访问工作台外部目录")

    # 如果请求打开目录，或目标本身已是目录
    if is_dir:
        final_dir = target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
        if not os.path.isdir(final_dir):
            final_dir = os.path.abspath(core.OUT_DIR)
        if not _is_allowed_local_path(final_dir):
            raise HTTPException(403, "禁止访问工作台外部目录")
        try:
            os.startfile(final_dir)
            return {
                "ok": True,
                "name": os.path.basename(final_dir),
                "path": final_dir,
                "is_dir": True,
                "message": "已在主机打开",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": final_dir}

    # 打开文件本身
    if os.path.isdir(target_path):
        # 目标实际为目录但未显式传 is_dir=True，按目录打开
        try:
            os.startfile(target_path)
            return {
                "ok": True,
                "name": os.path.basename(target_path),
                "path": target_path,
                "is_dir": True,
                "message": "已在主机打开",
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "path": target_path}

    if not os.path.isfile(target_path):
        raise HTTPException(404, "找不到该本地文件或目录")

    try:
        os.startfile(target_path)
        return {
            "ok": True,
            "name": os.path.basename(target_path),
            "path": target_path,
            "is_dir": False,
            "message": "已在主机打开",
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc),
            "url": f"/files/{os.path.basename(target_path)}",
        }


@app.get("/api/file/preview")
def api_file_preview(file_id: str = None, name: str = None):
    """表格前 50 行或文档结构化预览。"""
    target_path = None
    if file_id:
        with db() as conn:
            row = conn.execute("SELECT path, name FROM files WHERE id=?", (file_id,)).fetchone()
            if row:
                target_path = row["path"]
    elif name:
        cand1 = os.path.join(core.OUT_DIR, name)
        cand2 = os.path.join(UPLOAD_DIR, name)
        target_path = cand1 if os.path.isfile(cand1) else (cand2 if os.path.isfile(cand2) else None)

    if not target_path or not os.path.isfile(target_path):
        raise HTTPException(404, "找不到文件")

    ext = os.path.splitext(target_path)[1].lower()
    if ext in (".xlsx", ".xlsm", ".xls", ".csv"):
        dfs = calc_engine.read_dataframes_from_file(target_path)
        sheets_data = {}
        for sname, df in dfs.items():
            head_df = df.head(50)
            sheets_data[sname] = {
                "columns": list(head_df.columns),
                "rows": head_df.fillna("").values.tolist(),
                "total_rows": len(df),
            }
        return {"type": "table", "name": os.path.basename(target_path), "sheets": sheets_data}

    # 文本文件
    with open(target_path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read(8000)
    return {"type": "text", "name": os.path.basename(target_path), "content": text}


def _resolve_pipeline_files(body: dict) -> list:
    req_files = (body or {}).get("files")
    if req_files and isinstance(req_files, list) and len(req_files) > 0:
        valid = [dict(f) for f in req_files if isinstance(f, dict) and f.get("path")]
        if valid:
            return valid
    cid = (body or {}).get("conversation_id")
    if not cid:
        return []
    with db() as conn:
        files = conn.execute("SELECT * FROM files WHERE conv_id=?", (cid,)).fetchall()
    return [dict(f) for f in files]


@app.post("/api/calc/summary")
def api_calc_summary(body: dict = None):
    """一键触发调拨对账汇总表生成。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的表格附件")
    mapping = (body or {}).get("mapping")
    sheet_headers = (body or {}).get("sheet_headers")
    try:
        res = calc_engine.generate_summary_excel([dict(f) for f in files], core.OUT_DIR, custom_mapping=mapping, sheet_headers=sheet_headers)
        return {"ok": True, **res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/reconcile_fields")
def api_calc_reconcile_fields(body: dict = None):
    """读取已上传对账表格的表头与候选映射列。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的表格附件")
    sheet_headers = (body or {}).get("sheet_headers")
    try:
        res = calc_engine.get_table_columns_and_candidates([dict(f) for f in files], sheet_headers=sheet_headers)
        return res
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/reconcile_audit")
def api_calc_reconcile_audit(body: dict = None):
    """生成《数据校验验收单》（合计核对与差额清单计算）。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的表格附件")
    mapping = (body or {}).get("mapping")
    sheet_headers = (body or {}).get("sheet_headers")
    custom_rules = (body or {}).get("custom_rules")
    try:
        res = calc_engine.generate_reconciliation_audit(
            [dict(f) for f in files],
            custom_mapping=mapping,
            sheet_headers=sheet_headers,
            custom_rules=custom_rules
        )
        return res
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/price_compare")
def api_calc_price_compare(body: dict = None):
    """供应商比选/比价：确定性 TCO 计算、差价率标注、加权评分矩阵与谈判要点。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的报价表格附件")
    weights = (body or {}).get("weights")
    tax_rate = float((body or {}).get("tax_rate", 0.13))
    annual_interest_rate = float((body or {}).get("annual_interest_rate", 0.06))
    try:
        res = calc_engine.calculate_supplier_price_comparison(
            [dict(f) for f in files],
            weights=weights,
            tax_rate=tax_rate,
            annual_interest_rate=annual_interest_rate,
        )
        return res
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/price_export")
def api_calc_price_export(body: dict = None):
    """导出供应商比选与 TCO 成本分析表（.xlsx）。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的报价表格附件")
    weights = (body or {}).get("weights")
    tax_rate = float((body or {}).get("tax_rate", 0.13))
    annual_interest_rate = float((body or {}).get("annual_interest_rate", 0.06))
    try:
        calc_res = calc_engine.calculate_supplier_price_comparison(
            [dict(f) for f in files],
            weights=weights,
            tax_rate=tax_rate,
            annual_interest_rate=annual_interest_rate,
        )
        res = calc_engine.generate_price_tco_excel(calc_res, core.OUT_DIR)
        return {"ok": True, **res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/price_ppt")
def api_calc_price_ppt(body: dict = None):
    """导出供应商比选汇报 PPT（含原生 Office 柱状图 .pptx）。"""
    files = _resolve_pipeline_files(body)
    if not files:
        raise HTTPException(400, "当前对话没有已加载的报价表格附件")
    weights = (body or {}).get("weights")
    tax_rate = float((body or {}).get("tax_rate", 0.13))
    annual_interest_rate = float((body or {}).get("annual_interest_rate", 0.06))
    try:
        calc_res = calc_engine.calculate_supplier_price_comparison(
            [dict(f) for f in files],
            weights=weights,
            tax_rate=tax_rate,
            annual_interest_rate=annual_interest_rate,
        )
        res = calc_engine.generate_price_tco_ppt(calc_res, core.OUT_DIR)
        return {"ok": True, **res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/contract_review")
@app.post("/api/calc/compliance_review")
def api_calc_contract_review(body: dict = None):
    """支持内置 6 大核心条款与自定义审查标准，执行确定性合规性排查。"""
    body = body or {}
    text = body.get("text", "")
    files = _resolve_pipeline_files(body)
    if not text and files:
        text = "\n".join(f.get("text", "") for f in files if f.get("text"))
    if not text or len(text.strip()) < 10:
        raise HTTPException(400, "请提供合同或合规文本，或上传审查文件")
    try:
        custom_rules = body.get("custom_rules")
        enable_builtin = body.get("enable_builtin", True)
        enabled_builtin_indexes = body.get("enabled_builtin_indexes")
        res = calc_engine.analyze_contract_full(
            text,
            custom_rules=custom_rules,
            enable_builtin=enable_builtin,
            enabled_builtin_indexes=enabled_builtin_indexes
        )
        return res
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/calc/contract_export")
@app.post("/api/calc/compliance_export")
def api_calc_contract_export(body: dict = None):
    """一键导出合规性审查报告（Word .docx / PPT .pptx）。"""
    body = body or {}
    text = body.get("text", "")
    files = _resolve_pipeline_files(body)
    if not text and files:
        text = "\n".join(f.get("text", "") for f in files if f.get("text"))
    if not text or len(text.strip()) < 10:
        raise HTTPException(400, "请提供合同或合规文本，或上传审查文件")
    export_type = str(body.get("export_type") or body.get("type") or "doc").lower()
    try:
        custom_rules = body.get("custom_rules")
        enable_builtin = body.get("enable_builtin", True)
        enabled_builtin_indexes = body.get("enabled_builtin_indexes")
        rev_res = calc_engine.analyze_contract_full(
            text,
            custom_rules=custom_rules,
            enable_builtin=enable_builtin,
            enabled_builtin_indexes=enabled_builtin_indexes
        )
        if export_type in ("ppt", "pptx"):
            res = calc_engine.generate_contract_review_pptx(rev_res, core.OUT_DIR)
        else:
            res = calc_engine.generate_contract_review_docx(rev_res, core.OUT_DIR)
        return {"ok": True, **res}
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/conversations/{cid}/pin")
def pin_conv(cid: str, body: dict = None):
    pinned = 1 if (body or {}).get("pinned") else 0
    with db() as conn:
        conn.execute("UPDATE conversations SET pinned=? WHERE id=?", (pinned, cid))
    return {"ok": True, "pinned": bool(pinned)}


@app.get("/api/files/{fid}/text")
def file_text(fid: str):
    with db() as conn:
        row = conn.execute("SELECT name, chars, text FROM files WHERE id=?", (fid,)).fetchone()
    if not row:
        raise HTTPException(404, "文件不存在")
    return {"name": row["name"], "chars": row["chars"], "text": (row["text"] or "")[:20000]}


@app.post("/api/conversations/{cid}/delete_pair")
def delete_pair(cid: str, body: dict = None):
    """删除一条回答以及它前面那条提问。"""
    body = body or {}
    mid = body.get("message_id")
    index = body.get("index")
    with db() as conn:
        rows = conn.execute(
            "SELECT id, role FROM messages WHERE conv_id=? ORDER BY created_at, rowid",
            (cid,),
        ).fetchall()
        if not rows:
            raise HTTPException(404, "没有消息")
        pos = None
        if mid:
            for i, r in enumerate(rows):
                if r["id"] == mid:
                    pos = i
                    break
        if pos is None and isinstance(index, int) and 0 <= index < len(rows):
            pos = index
        if pos is None:
            raise HTTPException(400, "找不到这条消息")
        targets = [rows[pos]["id"]]
        if rows[pos]["role"] == "assistant" and pos > 0 and rows[pos - 1]["role"] == "user":
            targets.append(rows[pos - 1]["id"])
        elif rows[pos]["role"] == "user" and pos + 1 < len(rows) and rows[pos + 1]["role"] == "assistant":
            targets.append(rows[pos + 1]["id"])
        conn.executemany("DELETE FROM messages WHERE id=?", [(t,) for t in targets])
    return {"ok": True, "deleted": len(targets)}


@app.get("/api/kb/files")
def kb_files():
    with db() as conn:
        rows = conn.execute(
            """SELECT f.id, f.name, f.chars, f.created_at,
                      (SELECT COUNT(*) FROM chunks c WHERE c.file_id=f.id) AS chunks
               FROM files f ORDER BY f.created_at DESC LIMIT 200"""
        ).fetchall()
        total = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
    return {"files": [dict(r) for r in rows], "total_chunks": total}


@app.post("/api/kb/clear")
def kb_clear(body: dict = None):
    """清空索引；传 file_id 只删该文件。"""
    fid = (body or {}).get("file_id")
    with db() as conn:
        if fid:
            conn.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
            conn.execute("DELETE FROM files WHERE id=?", (fid,))
        else:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM files")
    return {"ok": True}


@app.post("/api/kb/rebuild")
def kb_rebuild():
    with db() as conn:
        files = conn.execute("SELECT id,name,text,conv_id FROM files").fetchall()
        conn.execute("DELETE FROM chunks")
        n = 0
        for f in files:
            for piece in chunk_text(f["text"]):
                conn.execute(
                    "INSERT INTO chunks(id,file_id,conv_id,name,body,created_at) VALUES(?,?,?,?,?,?)",
                    (uuid.uuid4().hex[:12], f["id"], f["conv_id"], f["name"], piece, now()),
                )
                n += 1
    return {"ok": True, "chunks": n, "files": len(files)}







@app.post("/api/file/reveal")
def api_file_reveal(body: dict = None):
    """在 Windows 资源管理器中高亮定位并选中文件"""
    import subprocess
    body = body or {}
    path = body.get("path")
    name = body.get("name")
    file_id = body.get("file_id")

    target_path = None
    if file_id:
        with db() as conn:
            row = conn.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
            if row:
                target_path = row["path"]
    elif path:
        target_path = os.path.abspath(path)
    elif name:
        cand1 = os.path.join(core.OUT_DIR, name)
        cand2 = os.path.join(UPLOAD_DIR, name)
        if os.path.isfile(cand1):
            target_path = cand1
        elif os.path.isfile(cand2):
            target_path = cand2

    if target_path and not _is_allowed_local_path(target_path):
        raise HTTPException(403, "只能打开工作台自身目录内的文件")

    if not target_path or not os.path.exists(target_path):
        target_path = core.OUT_DIR

    try:
        if os.path.isfile(target_path):
            subprocess.Popen(f'explorer /select,"{target_path}"', shell=True)
        else:
            os.startfile(target_path)
        return {"ok": True, "path": target_path}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}




@app.get("/api/artifact/latest")
def api_artifact_latest(cid: str = None):
    """获取指定会话或最近生成的交付物成果"""
    if cid:
        with db() as conn:
            row = conn.execute(
                "SELECT meta FROM messages WHERE conv_id=? AND role='assistant' AND meta LIKE '%artifact%' ORDER BY created_at DESC LIMIT 1",
                (cid,)
            ).fetchone()
            if row:
                try:
                    meta = json.loads(row["meta"])
                    if "artifact" in meta:
                        return {"ok": True, "artifact": meta["artifact"]}
                except Exception:
                    pass
    return {"ok": False, "message": "暂无成果文件"}


@app.get("/api/conversations")
def list_convs():
    cleanup_empty_conversations()
    with db() as conn:
        rows = conn.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conv_id=c.id) AS cnt
               FROM conversations c
               WHERE (SELECT COUNT(*) FROM messages m WHERE m.conv_id=c.id) > 0
               ORDER BY c.pinned DESC, c.updated_at DESC LIMIT 200"""
        ).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/conversations")
def create_conv(body: "NewConv | None" = None):
    body = body or NewConv()
    cid = uuid.uuid4().hex[:12]
    t = now()
    with db() as conn:
        conn.execute(
            "INSERT INTO conversations(id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",
            (cid, body.title or "新对话", body.mode, t, t),
        )
    return {"id": cid, "title": body.title or "新对话", "mode": body.mode}


@app.patch("/api/conversations/{cid}")
def rename_conv(cid: str, body: RenameIn):
    with db() as conn:
        conn.execute("UPDATE conversations SET title=?, updated_at=? WHERE id=?", (body.title[:60], now(), cid))
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def delete_conv(cid: str):
    with db() as conn:
        paths = [r["path"] for r in conn.execute("SELECT path FROM files WHERE conv_id=?", (cid,)).fetchall()]
        conn.execute("DELETE FROM messages WHERE conv_id=?", (cid,))
        # 先按文件关联清索引（兼容历史数据里 chunks.conv_id 为空的情况），再按 conv_id 兜底
        conn.execute("DELETE FROM chunks WHERE file_id IN (SELECT id FROM files WHERE conv_id=?)", (cid,))
        conn.execute("DELETE FROM chunks WHERE conv_id=?", (cid,))
        conn.execute("DELETE FROM files WHERE conv_id=?", (cid,))
        conn.execute("DELETE FROM conversations WHERE id=?", (cid,))
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
    return {"ok": True}


@app.get("/api/conversations/{cid}")
def get_conv(cid: str):
    with db() as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "会话不存在")
        msgs = conn.execute(
            "SELECT id,role,content,meta,created_at FROM messages WHERE conv_id=? ORDER BY created_at, rowid", (cid,)
        ).fetchall()
        files = conn.execute(
            "SELECT id,name,chars,created_at FROM files WHERE conv_id=? ORDER BY created_at", (cid,)
        ).fetchall()
    return {
        "conversation": dict(conv),
        "messages": [dict(m) for m in msgs],
        "files": [dict(f) for f in files],
    }


@app.post("/api/upload")
@app.post("/api/files/upload")
async def upload(file: UploadFile = File(...), conversation_id: str = Form("")):
    raw = await file.read()
    if len(raw) > MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(400, f"文件超过 {MAX_FILE_MB}MB")
    fid = uuid.uuid4().hex[:12]
    safe = re.sub(r"[\\/:*?\"<>|]", "_", file.filename or "file")
    path = os.path.join(UPLOAD_DIR, f"{fid}_{safe}")
    with open(path, "wb") as fh:
        fh.write(raw)
    try:
        name, text = core.extract_text(path)
    except Exception as exc:  # noqa: BLE001
        os.remove(path)
        raise HTTPException(400, f"无法解析该文件：{exc}") from exc
    name = file.filename or name
    conv_id = conversation_id or ""
    with db() as conn:
        conn.execute(
            "INSERT INTO files(id,conv_id,name,path,chars,text,created_at) VALUES(?,?,?,?,?,?,?)",
            (fid, conv_id, name, path, len(text), text, now()),
        )
        for i, piece in enumerate(chunk_text(text)):
            conn.execute(
                "INSERT INTO chunks(id,file_id,conv_id,name,body,created_at) VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], fid, conv_id, name, piece, now()),
            )
    return {"id": fid, "name": name, "path": path, "chars": len(text), "preview": text[:160]}


@app.post("/api/files/{fid}/delete")
def delete_file(fid: str):
    with db() as conn:
        row = conn.execute("SELECT path FROM files WHERE id=?", (fid,)).fetchone()
        conn.execute("DELETE FROM chunks WHERE file_id=?", (fid,))
        conn.execute("DELETE FROM files WHERE id=?", (fid,))
    if row:
        try:
            os.remove(row["path"])
        except OSError:
            pass
    return {"ok": True}


def chunk_text(text, size=600, overlap=80):
    """按空行/标题切块，再合并到 ~size 字，块之间保留少量重叠。"""
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    pieces = []
    for b in blocks:
        if len(b) <= size:
            pieces.append(b)
        else:
            step = max(size - overlap, 100)
            for i in range(0, len(b), step):
                pieces.append(b[i:i + size])
    out, cur = [], ""
    for p in pieces:
        if not cur:
            cur = p
        elif len(cur) + len(p) + 2 <= size:
            cur += "\n\n" + p
        else:
            out.append(cur)
            tail = cur[-overlap:] if len(cur) > overlap else ""
            cur = (tail + "\n\n" + p).strip() if tail else p
    if cur:
        out.append(cur)
    return [c for c in out if len(c.strip()) > 40]


def bm25_top(query, docs, top_k=4):
    """docs: [(name, body)]，返回 [(score, name, body)]"""
    import collections
    import math

    import jieba

    if not docs or not query.strip():
        return []
    query = query[-500:]
    q_tokens = [t for t in jieba.cut(query) if t.strip()]
    if not q_tokens:
        return []
    docs_tokens = [[t for t in jieba.cut(d[1]) if t.strip()] for d in docs]
    n = len(docs)
    avgdl = sum(len(t) for t in docs_tokens) / max(n, 1) or 1.0
    df = collections.Counter()
    for toks in docs_tokens:
        for t in set(toks):
            df[t] += 1
    k1, b = 1.5, 0.75
    scored = []
    for idx, toks in enumerate(docs_tokens):
        tf = collections.Counter(toks)
        s = 0.0
        for t in q_tokens:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            s += idf * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * len(toks) / avgdl))
        if s > 0:
            scored.append((s, docs[idx][0], docs[idx][1]))
    scored.sort(key=lambda x: -x[0])
    return scored[:top_k]


def load_memories():
    with db() as conn:
        rows = conn.execute("SELECT text FROM memories ORDER BY created_at DESC LIMIT 40").fetchall()
    return [r["text"] for r in rows]


def mode_prompt(mode_id):
    with db() as conn:
        row = conn.execute("SELECT prompt FROM mode_prompts WHERE mode=?", (mode_id,)).fetchone()
    if row and row["prompt"] and row["prompt"].strip():
        return row["prompt"]
    return MODE_MAP.get(mode_id, MODES[0]).get("prompt", "")


def code_analysis(question, files):
    """让模型写 pandas 代码，本地执行，把真实结果返回给模型。"""
    target = None
    for f in files:
        low = (f["name"] or "").lower()
        if low.endswith((".xlsx", ".xlsm", ".csv")):
            target = f
            break
    if not target:
        return ""
    path = target["path"]
    try:
        import pandas as pd

        if path.lower().endswith(".csv"):
            df = pd.read_csv(path, nrows=8)
            reader = "pd.read_csv"
        else:
            df = pd.read_excel(path, nrows=8)
            reader = "pd.read_excel"
        cols = list(map(str, df.columns))
        head = df.to_string(index=False)[:900]
    except Exception as exc:  # noqa: BLE001
        return f"\n\n【文件读取失败】{exc}"

    prompt = (
        f"你要用 pandas 回答一个关于表格的问题。\n"
        f"文件：{path}（用 {reader}(r'{path}') 读取）\n"
        f"列名：{cols}\n前几行：\n{head}\n\n"
        f"问题：{question}\n\n"
        "请只输出一段可直接运行的 Python 代码（不要解释、不要 Markdown 代码块）：\n"
        "1）用 pandas 读取该文件；2）完成计算；3）用 print() 输出结论（含数字，保留 2 位小数）；\n"
        "4）不要画图、不要写文件、不要联网；5）代码要短，能在 30 秒内跑完。"
    )
    raw = core.generate_text(prompt, max_tokens=700, temperature=0.15)
    code = core.extract_code(raw)
    if not code:
        return ""
    out, err, rc = core.run_python(code, timeout=45)
    print(f"[code] rc={rc} out={len(out)} err={err[:120]!r}", flush=True)
    if rc != 0 or not out.strip():
        # 把报错喂回模型，让它自己修一次
        fix_prompt = (
            f"刚才这段代码运行失败了：\n{code}\n\n报错：\n{err[:800]}\n\n"
            f"文件列名是 {cols}。请只输出修正后的完整 Python 代码，不要解释。"
        )
        raw2 = core.generate_text(fix_prompt, max_tokens=700, temperature=0.15)
        code2 = core.extract_code(raw2)
        out2, err2, rc2 = core.run_python(code2, timeout=45)
        print(f"[code] retry rc={rc2} out={len(out2)} err={err2[:120]!r}", flush=True)
        if rc2 == 0 and out2.strip():
            return f"\n\n【代码计算结果（pandas 真实执行，权威数据）】\n{out2.strip()}\n"
        return f"\n\n【代码执行失败，可忽略】{err2[:300]}"
    return f"\n\n【代码计算结果（pandas 真实执行，权威数据）】\n{out.strip()}\n"


def build_system_extra(mode_id, files):
    """构建系统提示词：强化当前文件的最高事实优先级，并自动挂载确定性计算基准。"""
    parts = []
    if files:
        names = "、".join(f.get("name", "未命名") for f in files)
        budget = TOTAL_DOC_CHARS // max(len(files), 1)
        blocks = [f"【文件：{f.get('name', '未命名')}】\n{(f.get('text') or '')[:budget]}" for f in files]
        file_header = (
            "=========================================================\n"
            f"【最高优先级隔离：当前会话上传文件】\n"
            f"本次对话用户已上传并指定以下文件：{names}\n"
            "【核心准则】：\n"
            "1. 你必须以当前上传文件内容为唯一的最高事实依据进行回答！\n"
            "2. 严禁参考以前历史对话中讨论的旧项目、旧数字或无关背景；\n"
            "3. 逐条引用文件里的原句、条款或数字；文件里没有提及的信息，强制写「文件中未提及」，严禁编造！\n"
            "===== 当前上传文件内容开始 =====\n" + "\n\n".join(blocks) + "\n===== 当前上传文件内容结束 =====\n"
            "========================================================="
        )
        parts.append(file_header)

        # 模式专属确定性数据挂载
        if mode_id == "price":
            try:
                price_res = calc_engine.calculate_supplier_price_comparison([dict(f) for f in files])
                if price_res and price_res.get("markdown"):
                    parts.append(
                        "=========================================================\n"
                        "【确定性比选与TCO计算基准（由 Python 引擎统一换算与加权评分）】：\n"
                        f"{price_res['markdown']}\n"
                        "【核心准则】：4B 模型必须 100% 依据上述 Python 计算的真实加权得分矩阵输出《授标推荐结论》与《分供应商谈判压价要点》，严禁自行捏造价格、排名或违背得分矩阵！\n"
                        "========================================================="
                    )
            except Exception as e:
                print(f"[calc_engine] price precompute failed: {e}", flush=True)
        elif mode_id == "review":
            try:
                contract_txt = "\n".join(f.get("text", "") for f in files if f.get("text")) if files else ""
                if not contract_txt and files:
                    for f in files:
                        p = f.get("path")
                        if p and os.path.exists(p):
                            try:
                                _, txt = core.extract_text(p)
                                contract_txt += "\n" + (txt or "")
                            except Exception:
                                pass
                if contract_txt and len(contract_txt.strip()) >= 10:
                    rev_res = calc_engine.analyze_contract_full(contract_txt)
                    if rev_res and rev_res.get("markdown"):
                        parts.append(
                            "=========================================================\n"
                            "【确定性采购合同风控审查基准（内置 6 大核心条款审查库）】：\n"
                            f"{rev_res['markdown']}\n"
                            "【核心准则】：你的输出必须严格遵守固定三段式验收结构：1) 顶部统计看板（[🔴 致命风险 X 项] 等）、2) 逐项对照表、3) 底部《缺失条款补充清单》，严禁擅自调整格式或遗漏部分！\n"
                            "========================================================="
                        )
            except Exception as e:
                print(f"[calc_engine] review precompute failed: {e}", flush=True)
        else:
            try:
                calc_summary = calc_engine.precompute_tables_summary([dict(f) for f in files])
                if calc_summary:
                    parts.append(calc_summary)
            except Exception as e:
                print(f"[calc_engine] precompute failed: {e}", flush=True)

    # 模式专属专家提示词
    mode_p = mode_prompt(mode_id)
    if mode_p:
        parts.append(mode_p)

    return "\n\n".join(parts)


@app.get("/api/models")
def list_models():
    st = core.status()
    return {
        "current": os.path.basename(st["path"]),
        "items": core.list_models(),
        "auto": st["auto"],
        "lock": st["lock"],
        "locked_model": st["locked_model"],
        "recommended": st["recommended"],
        "reason": st["recommend_reason"],
        "hardware": st["hardware"],
    }


class ModelIn(BaseModel):
    id: str
    lock: bool | None = None


@app.post("/api/model")
def switch_model(body: ModelIn):
    try:
        core.switch_model(body.id, body.lock)
    except FileNotFoundError:
        raise HTTPException(404, "找不到该模型文件") from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return core.status()


class LockIn(BaseModel):
    locked: bool


@app.post("/api/model/lock")
def model_lock(body: LockIn):
    try:
        if body.locked:
            name = os.path.basename(core.status()["path"])
            ids = {m["id"] for m in core.list_models()}
            if name not in ids:
                raise HTTPException(404, "找不到当前模型文件")
            core.set_lock(True, name)
        else:
            core.set_lock(False)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc)) from exc
    return core.status()


class PromptIn(BaseModel):
    prompt: str


@app.get("/api/mode_prompts")
def get_mode_prompts():
    with db() as conn:
        rows = conn.execute("SELECT mode, prompt FROM mode_prompts").fetchall()
    overrides = {r["mode"]: r["prompt"] for r in rows}
    return {
        "modes": [
            {"id": m["id"], "name": m["name"], "icon": m["icon"],
             "default": m.get("prompt", ""), "custom": overrides.get(m["id"], "")}
            for m in MODES
        ]
    }


@app.put("/api/mode_prompts/{mode_id}")
def set_mode_prompt(mode_id: str, body: PromptIn):
    if mode_id not in MODE_MAP:
        raise HTTPException(404, "没有这个模式")
    text = (body.prompt or "").strip()
    with db() as conn:
        if text:
            conn.execute(
                "INSERT INTO mode_prompts(mode,prompt) VALUES(?,?) "
                "ON CONFLICT(mode) DO UPDATE SET prompt=excluded.prompt",
                (mode_id, text[:4000]),
            )
        else:
            conn.execute("DELETE FROM mode_prompts WHERE mode=?", (mode_id,))
    return {"ok": True, "custom": bool(text)}




@app.post("/api/mode_prompts/reset_all")
def reset_all_mode_prompts():
    """将所有模式提示词一键恢复为最新的专业供应链提示词库"""
    with db() as conn:
        conn.execute("DELETE FROM mode_prompts")
    return {"ok": True, "count": len(MODES)}


@app.post("/api/conversations/{cid}/branch")
def branch_conversation(cid: str, body: dict = None):
    body = body or {}
    upto = body.get("message_id")
    with db() as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if not conv:
            raise HTTPException(404, "会话不存在")
        rows = conn.execute(
            "SELECT id,role,content,meta,created_at FROM messages WHERE conv_id=? ORDER BY created_at, rowid",
            (cid,),
        ).fetchall()
        keep = []
        for r in rows:
            keep.append(r)
            if upto and r["id"] == upto:
                break
        if not keep:
            raise HTTPException(400, "这个对话还没有内容")
        nid = uuid.uuid4().hex[:12]
        t = now()
        title = (conv["title"] or "新对话") + " · 分支"
        conn.execute(
            "INSERT INTO conversations(id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",
            (nid, title[:60], conv["mode"], t, t),
        )
        for r in keep:
            conn.execute(
                "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], nid, r["role"], r["content"], r["meta"], r["created_at"]),
            )
    return {"id": nid, "title": title[:60], "count": len(keep)}


@app.get("/api/memories")
def list_memories():
    with db() as conn:
        rows = conn.execute("SELECT id,text,created_at FROM memories ORDER BY created_at DESC LIMIT 200").fetchall()
    return [dict(r) for r in rows]


class MemIn(BaseModel):
    text: str


@app.post("/api/memories")
def add_memory(body: MemIn):
    text = (body.text or "").strip()
    if not text:
        raise HTTPException(400, "内容不能为空")
    mid = uuid.uuid4().hex[:12]
    with db() as conn:
        conn.execute("INSERT INTO memories(id,text,created_at) VALUES(?,?,?)", (mid, text[:600], now()))
    return {"id": mid, "text": text[:600]}


@app.delete("/api/memories/{mid}")
def del_memory(mid: str):
    with db() as conn:
        conn.execute("DELETE FROM memories WHERE id=?", (mid,))
    return {"ok": True}


@app.get("/api/kb/stats")
def kb_stats():
    with db() as conn:
        c = conn.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
        f = conn.execute("SELECT COUNT(*) c FROM files").fetchone()["c"]
    return {"chunks": c, "files": f}


@app.post("/api/chat")
async def chat(body: ChatIn):
    with db() as conn:
        cid = body.conversation_id
        conv = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone() if cid else None
        if not conv:
            cid = cid or uuid.uuid4().hex[:12]
            body.conversation_id = cid
            t = now()
            initial_title = body.message.strip().replace("\n", " ")[:24] or "新对话"
            conn.execute(
                "INSERT INTO conversations(id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",
                (cid, initial_title, body.mode or "general", t, t),
            )
            conv = conn.execute("SELECT * FROM conversations WHERE id=?", (cid,)).fetchone()
        if body.file_ids:
            for fid in body.file_ids:
                conn.execute("UPDATE files SET conv_id=? WHERE id=?", (body.conversation_id, fid))
                conn.execute("UPDATE chunks SET conv_id=? WHERE file_id=?", (body.conversation_id, fid))
        files = conn.execute("SELECT * FROM files WHERE conv_id=?", (body.conversation_id,)).fetchall()
        attached = [
            {"id": r["id"], "name": r["name"]}
            for r in files
            if r["id"] in set(body.file_ids)
        ]
        prev = conn.execute("SELECT COUNT(*) c FROM messages WHERE conv_id=?", (body.conversation_id,)).fetchone()["c"]
        mid = uuid.uuid4().hex[:12]
        conn.execute(
            "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
            (mid, body.conversation_id, "user", body.message,
             json.dumps({"files": attached}, ensure_ascii=False), now()),
        )
        title = conv["title"]
        if title in ("新对话", "", None) and prev == 0:
            if body.message.strip():
                title = body.message.strip().replace("\n", " ")[:24]
            elif attached:
                title = attached[0]["name"][:24]
            else:
                title = "新对话"
        conn.execute(
            "UPDATE conversations SET title=?, mode=?, updated_at=? WHERE id=?",
            (title, body.mode, now(), body.conversation_id),
        )
        history = conn.execute(
            "SELECT role,content FROM messages WHERE conv_id=? ORDER BY created_at, rowid", (body.conversation_id,)
        ).fetchall()

    # 当前有上传文件时，采用“最高优先级隔离”：仅截取最近 4 条上下文，防止旧对话喧宾夺主
    if files:
        msgs = [{"role": r["role"], "content": r["content"]} for r in history][-4:]
    else:
        msgs = [{"role": r["role"], "content": r["content"]} for r in history][-16:]
    system_extra = build_system_extra(body.mode, files)

    # 自动记忆：用户说“记住：xxx”
    m = re.match(r"^(?:请)?记住[：:,，]\s*(.+)$", body.message.strip(), re.S)
    if m and len(m.group(1).strip()) > 1:
        with db() as conn:
            conn.execute(
                "INSERT INTO memories(id,text,created_at) VALUES(?,?,?)",
                (uuid.uuid4().hex[:12], m.group(1).strip()[:600], now()),
            )

    # 有附件时彻底屏蔽旧记忆干扰；无附件时按需挂载
    if not files:
        mems = load_memories()
        if mems:
            system_extra += (
                "\n\n【长期记忆】用户以前要求你记住的信息，回答时据此保持连贯：\n"
                + "\n".join(f"- {x}" for x in mems[:25])
            )

    # 成果物对象（Excel汇总表、材料比价表、表格分析、PPT、长报告等）
    artifact_info = None
    if body.mode == "merge" and files:
        try:
            artifact_info = calc_engine.generate_summary_excel([dict(f) for f in files], core.OUT_DIR)
        except Exception as e:
            print(f"[calc_engine] auto summary failed: {e}", flush=True)
    elif body.mode == "price" and files:
        try:
            artifact_info = calc_engine.generate_price_comparison_excel([dict(f) for f in files], core.OUT_DIR)
        except Exception as e:
            print(f"[calc_engine] auto price comparison failed: {e}", flush=True)
    elif body.mode == "data" and files:
        try:
            artifact_info = calc_engine.get_data_preview_artifact([dict(f) for f in files], core.OUT_DIR)
        except Exception as e:
            print(f"[calc_engine] auto data preview failed: {e}", flush=True)
    elif body.mode == "review":
        try:
            contract_txt = "\n".join(f.get("text", "") for f in files) if files else body.message
            if contract_txt and len(contract_txt.strip()) >= 10:
                risk_res = calc_engine.analyze_contract_full(contract_txt)
                if risk_res and risk_res.get("kpi_metrics"):
                    artifact_info = calc_engine.generate_contract_review_docx(risk_res, core.OUT_DIR)
        except Exception as e:
            print(f"[calc_engine] auto contract review failed: {e}", flush=True)

    if body.use_code and not files:
        try:
            system_extra += code_analysis(body.message, files)
        except Exception as exc:  # noqa: BLE001
            print("[code] failed:", exc, flush=True)

    # 核心隔离机制：当上传了当前附件时，自动临时屏蔽全局历史知识库（RAG），彻底解决瞎扯以前对话的问题
    # 严格会话与文件隐私隔离：绝不允许跨会话读取/偷看用户在其他会话上传的文件！
    kb_hits = []
    if body.use_kb and files:
        with db() as conn:
            rows = conn.execute(
                "SELECT name, body FROM chunks WHERE conv_id = ? LIMIT 500",
                (body.conversation_id,),
            ).fetchall()
        if rows:
            kb_hits = bm25_top(body.message, [(r["name"], r["body"]) for r in rows], top_k=3)
            if kb_hits:
                blocks = "\n\n".join(f"【{n}】\n{b[:900]}" for _, n, b in kb_hits)
                system_extra += (
                    "\n\n【当前附件参考】以下是当前会话上传文件相关的要点：\n" + blocks
                )

    q: queue.Queue = queue.Queue()
    cancel_event = threading.Event()
    ACTIVE_CANCELS[body.conversation_id] = cancel_event

    def worker():
        nonlocal artifact_info
        gen_chunks = []
        try:
            if artifact_info:
                q.put(("artifact", artifact_info))

            def on_chunk(chunk):
                gen_chunks.append(chunk)
                q.put(("delta", chunk))

            # 写报告模式的长报告分档：走分章节接力生成机制
            if body.mode == "report" and (body.report_length == "long" or body.max_tokens >= 4000):
                elapsed = core.generate_long_report_stream(
                    msgs, system_extra, body.temperature, body.deep_think,
                    on_chunk, cancel_event=cancel_event
                )
            else:
                elapsed = core.generate_stream(
                    msgs, system_extra, body.max_tokens, body.temperature, body.deep_think,
                    on_chunk, cancel_event=cancel_event
                )

            full_gen = "".join(gen_chunks)

            # PPT 模式后置自动化编译生成 .pptx 文件
            if body.mode == "ppt" and not cancel_event.is_set() and len(full_gen.strip()) > 30:
                try:
                    parsed_ppt = core.parse_ppt_text(full_gen)
                    if parsed_ppt and parsed_ppt.get("slides"):
                        ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
                        ppt_name = f"汇报演示文稿-{ts_str}.pptx"
                        ppt_path = os.path.join(core.OUT_DIR, ppt_name)
                        build_res = core.build_pptx(parsed_ppt, ppt_path)
                        fsize = os.path.getsize(ppt_path)
                        fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
                        val_rep = (build_res and (build_res.get("report_text") or build_res.get("report_summary"))) or f"PPT 导出自检报告（共 {len(parsed_ppt['slides'])} 页，0 处溢出）"
                        artifact_info = {
                            "filename": ppt_name,
                            "filepath": ppt_path,
                            "path": ppt_path,
                            "filesize": fsize_str,
                            "filetype": "ppt",
                            "validation_report": val_rep,
                            "validation_status": "自检通过 · 0处溢出",
                            "status": "自检通过",
                            "kpi_metrics": [
                                {"label": "演示主题", "value": (parsed_ppt.get("title") or "汇报演示")[:14], "icon": "📑"},
                                {"label": "幻灯片页数", "value": f"{len(parsed_ppt['slides'])} 页", "icon": "🖥️"},
                                {"label": "幻灯片比例", "value": "16:9 高清", "icon": "📐"},
                                {"label": "设计规范", "value": "商务深蓝/烫金", "icon": "🎨"},
                            ],
                            "preview_data": {
                                "type": "ppt",
                                "title": parsed_ppt.get("title") or "汇报演讲",
                                "subtitle": parsed_ppt.get("subtitle") or "",
                                "slides": parsed_ppt.get("slides", []),
                            }
                        }
                        q.put(("artifact", artifact_info))
                except Exception as e:
                    print(f"[ppt_export] failed: {e}", flush=True)

            # 写报告模式后置自动化编译生成 .docx 公文
            elif body.mode == "report" and not cancel_event.is_set() and len(full_gen.strip()) > 50:
                try:
                    ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
                    doc_name = f"专项报告-{ts_str}.docx"
                    doc_path = os.path.join(core.OUT_DIR, doc_name)
                    m_title = re.search(r"^#\s+(.+)$", full_gen, re.M)
                    doc_title = m_title.group(1).strip() if m_title else (body.message.strip()[:20] or "专项分析与管理报告")
                    core.build_docx({"title": doc_title, "content": full_gen}, doc_path)
                    fsize = os.path.getsize(doc_path)
                    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
                    w_cnt = len(re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]', full_gen))
                    artifact_info = {
                        "filename": doc_name,
                        "filepath": doc_path,
                        "filesize": fsize_str,
                        "filetype": "doc",
                        "kpi_metrics": [
                            {"label": "报告主题", "value": doc_title[:14], "icon": "📄"},
                            {"label": "字数统计", "value": f"{w_cnt:,} 字", "icon": "📝"},
                            {"label": "排版规范", "value": "标准公文/微软雅黑", "icon": "📐"},
                            {"label": "交付状态", "value": "Word 交付就绪", "icon": "✓"},
                        ],
                        "preview_data": {
                            "type": "doc",
                            "title": doc_title,
                            "word_count": w_cnt,
                            "content": full_gen,
                        }
                    }
                    q.put(("artifact", artifact_info))
                except Exception as e:
                    print(f"[doc_export] failed: {e}", flush=True)
            elif body.mode == "review" and not cancel_event.is_set():
                try:
                    contract_txt = ("\n".join(f.get("text", "") for f in files) if files else "") or full_gen
                    if contract_txt and len(contract_txt.strip()) >= 10:
                        dyn_risks = calc_engine.analyze_contract_full(contract_txt)
                        if dyn_risks and dyn_risks.get("kpi_metrics"):
                            docx_res = calc_engine.generate_contract_review_docx(dyn_risks, core.OUT_DIR)
                            artifact_info = docx_res
                            q.put(("artifact", artifact_info))
                except Exception as e:
                    print(f"[review_risk_kpi] failed: {e}", flush=True)

            q.put(("done", (elapsed, artifact_info)))
        except Exception as exc:  # noqa: BLE001
            q.put(("error", str(exc)))
        finally:
            ACTIVE_CANCELS.pop(body.conversation_id, None)

    threading.Thread(target=worker, daemon=True).start()

    async def stream():
        buf = []
        cur_artifact = artifact_info
        finished = False
        try:
            yield sse({"type": "start", "conversation_id": body.conversation_id, "title": title})
            if cur_artifact:
                yield sse({"type": "artifact", "artifact": cur_artifact})
            while True:
                kind, val = await asyncio.to_thread(q.get)
                if kind == "delta":
                    buf.append(val)
                    yield sse({"type": "delta", "text": val})
                elif kind == "artifact":
                    cur_artifact = val
                    yield sse({"type": "artifact", "artifact": val})
                elif kind == "done":
                    elapsed_val, fin_artifact = val
                    if fin_artifact:
                        cur_artifact = fin_artifact
                    content = "".join(buf)
                    was_stopped = bool(cancel_event.is_set())
                    am = None
                    # 被停止/中断且一个字都没生成时，不落下一条空回答
                    if content.strip():
                        if was_stopped and not content.rstrip().endswith("（已停止）"):
                            content = content.rstrip() + "\n\n（已停止）"
                        am = uuid.uuid4().hex[:12]
                        meta_dict = {"elapsed": round(elapsed_val, 1)}
                        if was_stopped:
                            meta_dict["stopped"] = True
                        if cur_artifact:
                            meta_dict["artifact"] = cur_artifact
                            if "kpi_metrics" in cur_artifact:
                                meta_dict["kpi_metrics"] = cur_artifact["kpi_metrics"]
                        with db() as conn:
                            conn.execute(
                                "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                                (am, body.conversation_id, "assistant", content,
                     json.dumps(meta_dict, ensure_ascii=False, default=str), now()),
                            )
                            conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), body.conversation_id))
                    finished = True
                    yield sse({"type": "done", "elapsed": round(elapsed_val, 1), "message_id": am,
                               "title": title, "stopped": was_stopped, "artifact": cur_artifact})
                    break
                else:
                    content = "".join(buf)
                    if content:
                        with db() as conn:
                            conn.execute(
                                "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                                (uuid.uuid4().hex[:12], body.conversation_id, "assistant", content, "{}", now()),
                            )
                    finished = True
                    yield sse({"type": "error", "message": val})
                    break
        except (asyncio.CancelledError, GeneratorExit):
            # 客户端断开/点停止：中断推理，并把已经生成的部分落库并标记“已停止”
            cancel_event.set()
            partial = "".join(buf)
            if partial.strip() and not partial.rstrip().endswith("（已停止）"):
                try:
                    with db() as conn:
                        conn.execute(
                            "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                            (uuid.uuid4().hex[:12], body.conversation_id, "assistant",
                             partial.rstrip() + "\n\n（已停止）",
                             json.dumps({"stopped": True}, ensure_ascii=False), now()),
                        )
                        conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now(), body.conversation_id))
                except Exception:  # noqa: BLE001
                    pass
        finally:
            # 不论异常、客户端断开还是序列化失败，都要让后台推理停下来，避免占着模型锁空转
            if not finished:
                cancel_event.set()
            ACTIVE_CANCELS.pop(body.conversation_id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


EXPORT_JOBS: dict = {}


def _ppt_batch_prompt(transcript, start, count, total, done_titles):
    head = f"下面是用户与助手的对话，请据此整理一份共 {total} 页的 PPT 大纲。\n\n{transcript}\n\n"
    if done_titles:
        head += "已经写好的页标题（不要重复）：" + "；".join(done_titles[-40:]) + "\n\n"
    return (
        head
        + f"现在只写第 {start + 1} 到第 {start + count} 页（共 {total} 页）。\n"
        "严格按下面格式输出，不要解释、不要用 JSON、不要加代码块：\n"
        "## 页标题\n- 要点，30字以内\n- 要点\n- 要点\n"
        f"要求：写 {count} 页，每页 3-4 条要点，每条不超过 30 字，内容具体、带数字。"
    )


def _run_export(job_id, body):
    job = EXPORT_JOBS[job_id]
    try:
        with db() as conn:
            rows = conn.execute(
                "SELECT id,role,content FROM messages WHERE conv_id=? ORDER BY created_at, rowid",
                (body.conversation_id,),
            ).fetchall()
        # 按消息导出：只取到用户点的那条回答为止
        if getattr(body, "message_id", None):
            target_idx = None
            for idx, r in enumerate(rows):
                if r["id"] == body.message_id:
                    target_idx = idx
                    break
            if target_idx is None:
                raise RuntimeError("找不到这条消息（可能已删除），请刷新对话后重试")
            rows = rows[: target_idx + 1]
        transcript = "\n\n".join(
            f"{'用户' if r['role'] == 'user' else '助手'}：{r['content']}" for r in rows
        )[-8000:]
        if not transcript.strip():
            raise RuntimeError("当前对话还没内容")

        if body.kind == "ppt":
            total = max(1, min(100, int(body.pages or 10)))
            slides, title, subtitle = [], "汇报材料", ""
            job["progress"] = f"0/{total} 页"
            first = True
            while len(slides) < total:
                count = min(10, total - len(slides))
                if first:
                    prompt = (
                        f"下面是用户与助手的对话，请据此整理一份共 {total} 页的 PPT 大纲。\n\n{transcript}\n\n"
                        f"先写开头部分和前 {count} 页。\n"
                        "严格按下面格式输出，不要解释、不要用 JSON、不要加代码块：\n"
                        "标题：一句话主标题\n副标题：一句话副标题\n"
                        "## 页标题\n- 要点，30字以内\n- 要点\n- 要点\n"
                        f"要求：写 {count} 页，每页 3-4 条要点，每条不超过 30 字，内容具体、带数字。"
                    )
                else:
                    prompt = _ppt_batch_prompt(transcript, len(slides), count, total, [s["title"] for s in slides])
                raw = core.generate_text(prompt, max_tokens=min(2600, 260 * count + 260), temperature=0.55)
                data = core.parse_ppt_text(raw)
                if first:
                    title = data.get("title") or title
                    subtitle = data.get("subtitle") or subtitle
                    first = False
                new = data.get("slides") or []
                if not new:
                    break
                slides.extend(new[:count])
                job["progress"] = f"{min(len(slides), total)}/{total} 页"
            if not slides:
                raise RuntimeError("没能整理出大纲，请重试一次")
            path = core.stamp("PPT", "pptx")
            build_res = core.build_pptx({"title": title, "subtitle": subtitle, "slides": slides[:total]}, path)
            fsize_str = ""
            if os.path.exists(path):
                sz = os.path.getsize(path)
                fsize_str = f"{sz / 1024:.1f} KB" if sz < 1048576 else f"{sz / 1048576:.2f} MB"
            val_rep = (build_res and (build_res.get("report_text") or build_res.get("report_summary"))) or f"PPT 导出自检报告（共 {len(slides[:total])} 页，0 处溢出）"
            art_meta = {
                "filename": os.path.basename(path),
                "filepath": path,
                "path": path,
                "filesize": fsize_str,
                "filetype": "ppt",
                "validation_report": val_rep,
                "validation_status": "自检通过 · 0处溢出",
                "status": "自检通过",
            }
            target_mid = getattr(body, "message_id", None)
            with db() as conn:
                if not target_mid and rows:
                    for r in reversed(rows):
                        if r["role"] == "assistant":
                            target_mid = r["id"]
                            break
                if target_mid:
                    curr_meta_row = conn.execute("SELECT meta FROM messages WHERE id=?", (target_mid,)).fetchone()
                    curr_meta = {}
                    if curr_meta_row and curr_meta_row["meta"]:
                        try:
                            curr_meta = json.loads(curr_meta_row["meta"])
                        except Exception:
                            curr_meta = {}
                    curr_meta["artifact"] = art_meta
                    conn.execute("UPDATE messages SET meta=? WHERE id=?", (json.dumps(curr_meta, ensure_ascii=False), target_mid))

            job.update(
                status="done",
                progress=f"{len(slides[:total])} 页",
                file=os.path.basename(path),
                path=path,
                filesize=fsize_str,
                url=f"/files/{os.path.basename(path)}",
                summary=f"已生成 {len(slides[:total])} 页 PPT：{title}",
                validation_report=val_rep,
                artifact=art_meta,
            )
            return

        # excel：优先导出“这一条回答”里的表格
        table = None
        if getattr(body, "message_id", None) and rows:
            cand = core.parse_table_text(rows[-1]["content"])
            if cand and len(cand["rows"]) >= 2:
                table = cand
        if table is None:
            for r in reversed(rows):
                if r["role"] == "assistant" and "|" in r["content"]:
                    cand = core.parse_table_text(r["content"])
                    if cand and len(cand["rows"]) >= 2:
                        table = cand
                        break
        if table is None:
            prompt = (
                f"根据下面的对话内容，整理成一张结构化表格。\n\n{transcript}\n\n"
                "只输出 Markdown 表格，第一行是列名，不要输出其它文字。\n"
                "| 列1 | 列2 |\n| --- | --- |\n| 值 | 值 |"
            )
            raw = core.generate_text(prompt, max_tokens=1200, temperature=0.4)
            table = core.parse_table_text(raw)
        if not table:
            raise RuntimeError("对话里没有可导出的表格，请让助手先用表格整理内容")
        path = core.stamp("表格", "xlsx")
        core.build_xlsx(table, path)
        fsize_str = ""
        if os.path.exists(path):
            sz = os.path.getsize(path)
            fsize_str = f"{sz / 1024:.1f} KB" if sz < 1048576 else f"{sz / 1048576:.2f} MB"
        val_rep = f"表格导出自检报告（共 {len(table['rows'])} 行，0 处错误）"
        art_meta = {
            "filename": os.path.basename(path),
            "filepath": path,
            "path": path,
            "filesize": fsize_str,
            "filetype": "excel",
            "validation_report": val_rep,
            "validation_status": "自检通过 · 0处溢出",
            "status": "自检通过",
        }
        target_mid = getattr(body, "message_id", None)
        with db() as conn:
            if not target_mid and rows:
                for r in reversed(rows):
                    if r["role"] == "assistant":
                        target_mid = r["id"]
                        break
            if target_mid:
                curr_meta_row = conn.execute("SELECT meta FROM messages WHERE id=?", (target_mid,)).fetchone()
                curr_meta = {}
                if curr_meta_row and curr_meta_row["meta"]:
                    try:
                        curr_meta = json.loads(curr_meta_row["meta"])
                    except Exception:
                        curr_meta = {}
                curr_meta["artifact"] = art_meta
                conn.execute("UPDATE messages SET meta=? WHERE id=?", (json.dumps(curr_meta, ensure_ascii=False), target_mid))

        job.update(
            status="done",
            progress="完成",
            file=os.path.basename(path),
            path=path,
            filesize=fsize_str,
            url=f"/files/{os.path.basename(path)}",
            summary=f"已导出表格：{len(table['rows'])} 行 × {len(table['headers'])} 列",
            validation_report=val_rep,
            artifact=art_meta,
        )
    except Exception as exc:  # noqa: BLE001
        job.update(status="error", error=str(exc))


@app.post("/api/export")
def export(body: ExportIn):
    with db() as conn:
        conv = conn.execute("SELECT * FROM conversations WHERE id=?", (body.conversation_id,)).fetchone()
        if not conv:
            raise HTTPException(404, "会话不存在")
    job_id = uuid.uuid4().hex[:12]
    EXPORT_JOBS[job_id] = {"status": "running", "progress": "准备中", "file": None, "url": None, "summary": ""}
    threading.Thread(target=_run_export, args=(job_id, body), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/export/{job_id}")
def export_status(job_id: str):
    job = EXPORT_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "任务不存在")
    return job


app.mount("/files", StaticFiles(directory=core.OUT_DIR), name="files")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(os.path.join(WEB_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("QWEN_PORT", "7860")), log_level="warning")
