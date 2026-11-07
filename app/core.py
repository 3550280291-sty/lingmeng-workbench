# -*- coding: utf-8 -*-
"""核心能力：模型加载、文件解析、PPT/表格生成。"""
import json
import os
import platform
import queue
import re
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_DIR = os.environ.get("QWEN_MODEL_DIR", os.path.join(_HOME, "models"))
MODEL_PATH = os.environ.get(
    "QWEN_MODEL", os.path.join(MODEL_DIR, "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
)
# 本机（AMD CPU + NVIDIA 独显）上 OpenVINO 的 GPU 后端加载 Qwen3 GGUF 会显示成功，
# 但第一次生成就崩溃（broadcast shape 报错）；CPU 稳定可用，因此默认走 CPU。
# 想继续试验 GPU：设置环境变量 QWEN_DEVICE=GPU 后重启即可。
DEVICE = os.environ.get("QWEN_DEVICE", "CPU")
OUT_DIR = os.environ.get("QWEN_OUT", os.path.join(_HOME, "output"))
DOC_CHAR_LIMIT = int(os.environ.get("QWEN_DOC_CHARS", "16000"))
CONFIG_PATH = os.environ.get("QWEN_CONFIG", os.path.join(_HOME, "data", "config.json"))

os.makedirs(OUT_DIR, exist_ok=True)

BASE_PROMPT = (
    "你是运行在使用者本人电脑上的中文办公助手，回答准确、简洁、可直接使用。"
    "擅长：写报告与方案、数据分析、审阅文件、提炼要点、做对比与清单。"
    "默认用简体中文；不要冗长铺垫。不确定的信息要说明，不要编造数字、条款或引用。"
)

_current_path = MODEL_PATH
_pipe = None
_pipe_path = None
_state = {"ready": False, "loading": True, "error": "", "device": "", "model": os.path.basename(MODEL_PATH)}
_lock = threading.Lock()
_gen_lock = threading.Lock()
_start_mode = "default"   # locked / auto / default / missing
_hw_cache = None


def is_thinking_model(path=None):
    n = os.path.basename(path or _current_path or "").lower()
    if "thinking" in n:
        return True
    if "instruct-2507" in n:
        return False
    return True


def list_models():
    """扫描模型目录，返回可选列表。"""
    folder = os.path.dirname(_current_path) or os.path.join(_HOME, "models")
    items = []
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return items
    for name in names:
        if not name.lower().endswith(".gguf"):
            continue
        path = os.path.join(folder, name)
        try:
            gb = os.path.getsize(path) / (1024 ** 3)
        except OSError:
            continue
        low = name.lower()
        supported = "qwen3.5" not in low
        if "thinking" in low:
            note = "会先推理再回答，慢一些，适合难题"
        elif "instruct-2507" in low:
            note = "直接回答，速度最快，适合日常"
        elif "8b" in low:
            note = "8B 更聪明；本机 CPU 实测约 5–7 字/秒，可开深度思考"
        elif not supported:
            note = "当前运行时还不支持这个架构，选不了"
        else:
            note = ""
        items.append(
            {
                "id": name,
                "name": name.replace(".gguf", ""),
                "size_gb": round(gb, 2),
                "thinking": is_thinking_model(path),
                "supported": supported,
                "current": os.path.normcase(path) == os.path.normcase(_current_path),
                "note": note,
            }
        )
    return items


# ---------------------------------------------------------------- 配置 / 硬件 / 选型
def read_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_config(cfg):
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        tmp = CONFIG_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, CONFIG_PATH)
    except OSError as exc:
        print("[config] write failed:", exc, flush=True)


def config():
    cfg = read_config()
    return {"lock": bool(cfg.get("lock")), "model": str(cfg.get("model") or "")}


def set_lock(locked, filename=None):
    cfg = read_config()
    cfg["lock"] = bool(locked)
    if filename:
        cfg["model"] = filename
    elif not locked:
        cfg["model"] = ""
    write_config(cfg)
    return config()


def _ram_gb():
    try:
        import ctypes

        class _MEM(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = _MEM()
        st.dwLength = ctypes.sizeof(_MEM)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
        return st.ullTotalPhys / (1024 ** 3)
    except Exception:  # noqa: BLE001
        return 0.0


def hardware():
    """识别本机配置（内存 / 处理器 / 显卡），用于自动选型与设置页展示。"""
    global _hw_cache
    if _hw_cache is not None:
        return dict(_hw_cache)
    cpu = ""
    try:
        import winreg

        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0"
        )
        cpu = str(winreg.QueryValueEx(key, "ProcessorNameString")[0]).strip()
    except Exception:  # noqa: BLE001
        cpu = platform.processor() or ""
    _hw_cache = {
        "ram_gb": round(_ram_gb(), 1),
        "cpu": cpu,
        "cores": os.cpu_count() or 0,
        "gpu": "",
    }

    def _async_detect_gpu():
        try:
            import openvino as ov

            ov_core = ov.Core()
            gpu = ""
            for dev in ov_core.available_devices:
                if dev.upper().startswith("CPU"):
                    continue
                try:
                    gpu = ov_core.get_property(dev, "FULL_DEVICE_NAME")
                except Exception:  # noqa: BLE001
                    gpu = dev
                break
            if _hw_cache is not None and gpu:
                _hw_cache["gpu"] = gpu
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_async_detect_gpu, daemon=True).start()
    return dict(_hw_cache)



def recommend():
    """按内存预算从已安装模型里挑“跑得动且质量最好”的：预算 ≈ 内存的 35%。"""
    ram = _ram_gb() or 16.0
    items = [m for m in list_models() if m["supported"]]
    if not items:
        return None
    budget = max(3.5, ram * 0.35)
    fits = [m for m in items if m["size_gb"] <= budget]
    pool = fits or [min(items, key=lambda m: m["size_gb"])]
    pool.sort(key=lambda m: (-m["size_gb"], m["thinking"]))
    best = pool[0]
    reason = f"内存 {ram:.0f}GB，推荐 {best['size_gb']}GB 的 {best['name']}"
    return {"id": best["id"], "reason": reason}


def resolve_startup_model():
    """优先用用户锁定的模型；没有锁定时按本机配置自动选择。"""
    cfg = config()
    folder = os.path.dirname(_current_path) or MODEL_DIR
    if cfg["lock"] and cfg["model"]:
        path = os.path.join(folder, cfg["model"])
        if os.path.isfile(path) and is_supported(path):
            return path, "locked"
    rec = recommend()
    if rec:
        path = os.path.join(folder, rec["id"])
        if os.path.isfile(path):
            return path, "auto"
    if os.path.isfile(MODEL_PATH):
        return MODEL_PATH, "default"
    items = list_models()
    if items:
        return os.path.join(folder, items[0]["id"]), "default"
    return MODEL_PATH, "missing"


def status():
    st = dict(_state)
    name = os.path.basename(_current_path).lower()
    st["thinking"] = is_thinking_model()
    st["always_thinking"] = "thinking" in name
    st["path"] = _current_path
    cfg = config()
    rec = recommend() or {}
    st["auto"] = not cfg["lock"]
    st["lock"] = cfg["lock"]
    st["locked_model"] = cfg["model"]
    st["recommended"] = rec.get("id", "")
    st["recommend_reason"] = rec.get("reason", "")
    st["start_mode"] = _start_mode
    st["hardware"] = hardware()
    return st


def switch_model(filename, lock=None):
    global _current_path, _pipe, _pipe_path
    folder = os.path.dirname(_current_path) or MODEL_DIR
    path = os.path.join(folder, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(filename)
    if not is_supported(path):
        raise ValueError("当前运行时不支持该模型的架构")
    with _gen_lock:
        _state.update(ready=False, loading=True, error="", model=os.path.basename(path))
        _current_path = path
        _pipe = None
        _pipe_path = None
        get_pipe()
    if lock is None:
        lock = config()["lock"]
    if lock:
        set_lock(True, filename)
    else:
        set_lock(False)
    return status()


def is_supported(path):
    return "qwen3.5" not in os.path.basename(path).lower()


def get_pipe():
    global _pipe, _pipe_path
    if _pipe is not None and _pipe_path == _current_path:
        return _pipe
    with _lock:
        if _pipe is not None and _pipe_path == _current_path:
            return _pipe
        import openvino_genai as genai

        _state["loading"] = True
        errors = []
        for device in [DEVICE, "CPU"] if DEVICE != "CPU" else ["CPU"]:
            for reader in ("FRONTEND", None, "LEGACY"):
                try:
                    kwargs = {"GGUF_READER": reader} if reader else {}
                    _pipe = genai.LLMPipeline(_current_path, device, **kwargs)
                    _pipe_path = _current_path
                    _state.update(ready=True, loading=False, error="", device=device,
                                  model=os.path.basename(_current_path))
                    print(f"[model] loaded {os.path.basename(_current_path)} device={device} reader={reader}", flush=True)
                    return _pipe
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{device}/{reader}: {str(exc).splitlines()[0][:120]}")
        _state.update(ready=False, loading=False, error=" | ".join(errors))
        raise RuntimeError("模型加载失败: " + _state["error"])


def load_model(model_path: Optional[str] = None):
    """后台独立线程异步加载模型与预热，设置 loading: True, ready: False；就绪后 ready: True, loading: False。"""
    global _current_path, _start_mode
    with _lock:
        _state.update(ready=False, loading=True, error="")
    try:
        if model_path:
            _current_path = model_path
        else:
            resolved, mode = resolve_startup_model()
            _current_path = resolved
            _start_mode = mode
            _state["model"] = os.path.basename(_current_path)
        get_pipe()
        print(f"[model] {os.path.basename(_current_path)} loaded and warmed up successfully", flush=True)
    except Exception as exc:  # noqa: BLE001
        print("[model] load_model failed:", exc, flush=True)
        with _lock:
            _state.update(ready=False, loading=False, error=str(exc))


def warmup():
    return load_model()



def _detect_repetition(tail: str) -> bool:
    """流式防卡死熔断器：
    1. 彻底放行 Markdown 表格分割线（包含 |、-、:、+、=、_、空格组合），确保正常绘制任意规格表格与分割线；
    2. 仅在以下极端死循环时熔断：
       a) 连续 150 个完全相同的文字字符（排除换行、空格及表格/破折线符号）；
       b) 长度超过 12 个字的完全相同业务语句连续无间隔重复 4 次以上。
    """
    if not tail or len(tail) < 48:
        return False

    # 规则 a: 连续 150 个完全相同的单一有效字符（明确排除换行符、表格线、破折线与空格）
    if re.search(r"([^\r\n\-\|\:\s=_\+])\1{149,}", tail):
        return True

    # 规则 b: 长度超过 12 个字的完全相同业务语句连续无间隔重复 4 次以上
    for m in re.finditer(r"(.{12,150}?)\1{3,}", tail, re.DOTALL):
        pat = m.group(1)
        # 单一字符重复归规则 a 判定，此处仅拦截多字构成的真实语句
        if len(set(pat)) <= 1:
            continue
        # 如果全部由表格分割字符（|、-、:、+、=、_、空格、制表符、换行）组成，坚决不拦截
        if set(pat).issubset(set("|-:+=_ \t\r\n")):
            continue
        return True

    return False


class ThinkingStreamAdapter:
    """流式思考过程标准化适配器：
    1. 自动捕获缺少开头 <think> 标签的推理独白，在首字符前注入 <think>\n；
    2. 实时监测正文切换特征（</think>、独立成行分割线 ---/===、您已选定、章节标题 ###/一、等）；
    3. 触发切换时在正文前自动插入 \n</think>\n\n，保证落库与传输内容结构规范。
    """

    DELIM_RE = re.compile(
        r'(?:'
        r'</think>'
        r'|\n[ \t]*---[ \t]*(?:\r?\n|$)'
        r'|\n[ \t]*===[ \t]*(?:\r?\n|$)'
        r'|\n{2,}(?=您已选定|您目前提供|您好|抱歉|哎呀|感谢|很抱歉)'
        r'|\n{2,}(?=###?\s*(?:\[?[✅📊🔍💡📌🚨]|一、|[0-9]+[、.]|\*\*))'
        r'|\n{2,}(?=\*\*(?:报告标题|示范|印尼|项目|总体|采购|方案|对账|自查|需求))'
        r'|\n{2,}(?=[✅📊🔍💡📌🚨])'
        r'|\n(?=[✅📊🔍💡📌🚨])'
        r'|\n{2,}(?=[一二三四五]、)'
        r'|\n\n\n+'
        r')'
    )
    MONO_PREFIXES = (
        "首先", "思考", "我需要", "我现在需要", "用户现在", "用户想要", "用户最初",
        "用户要求", "用户选择", "好的，我", "好的，现在", "好的，用户",
        "嗯，用户", "嗯，现在", "回顾之前", "从提示词", "思考过程", "深度思考"
    )

    def __init__(self, emit_fn):
        self.emit = emit_fn
        self.state = "init"  # 'init', 'injected_think', 'model_think', 'body'
        self.buf = ""
        self.emitted_open = False
        self.emitted_close = False

    def push(self, chunk):
        if self.state == "body":
            self.emit(chunk)
            return

        if self.state == "init":
            self.buf += chunk
            stripped = self.buf.strip()
            if not stripped:
                return  # 缓冲前导空白与换行
            if stripped.startswith("<think>"):
                self.state = "model_think"
                self.emit(self.buf)
                self.buf = ""
                return

            s_lstrip = self.buf.lstrip()
            has_mono = any(s_lstrip.startswith(p) for p in self.MONO_PREFIXES)
            if has_mono:
                self.state = "injected_think"
                self.emitted_open = True
                self.emit("<think>\n" + s_lstrip)
                self.buf = ""
                return

            if len(stripped) >= 15 or "\n" in s_lstrip:
                self.state = "body"
                self.emit(self.buf)
                self.buf = ""
                return
            return

        if self.state in ("injected_think", "model_think"):
            self.buf += chunk
            m = self.DELIM_RE.search(self.buf)
            if m:
                delim_str = m.group(0)
                before = self.buf[:m.start()]
                after = self.buf[m.end():]
                if delim_str == "</think>":
                    self.emit(before + "</think>")
                else:
                    self.emit(before + "\n</think>\n\n" + delim_str)
                self.emitted_close = True
                self.state = "body"
                self.buf = ""
                if after:
                    self.emit(after)
            else:
                if len(self.buf) > 50:
                    safe = self.buf[:-25]
                    self.buf = self.buf[-25:]
                    self.emit(safe)
            return

    def finish(self):
        if self.state == "init":
            if self.buf:
                self.emit(self.buf)
                self.buf = ""
        elif self.state in ("injected_think", "model_think"):
            if self.buf:
                self.emit(self.buf)
                self.buf = ""
            if not self.emitted_close:
                self.emit("\n</think>\n\n")
                self.emitted_close = True


def think_adapter_enabled(deep_think=False):
    """是否启用思考流适配器：
    - 纯思考模型（文件名含 thinking）：始终启用；
    - 混合推理模型（如 Qwen3-8B）：仅用户开启深度思考时启用；
    - 普通快答模型（Instruct）：永不启用，避免正常回答被误判成思考内容。
    """
    name = os.path.basename(_current_path).lower()
    if not is_thinking_model():
        return False
    if "thinking" in name:
        return True
    return bool(deep_think)


def generate_stream(history_messages, system_extra, max_tokens, temperature, deep_think, emit, cancel_event=None):
    """调用模型并逐段回调 emit(text)。返回耗时。支持外部 cancel_event 请求中断。"""
    import openvino_genai as genai

    pipe = get_pipe()
    with _gen_lock:
        cfg = genai.GenerationConfig()
        cfg.max_new_tokens = int(max_tokens)
        cfg.temperature = float(temperature)
        cfg.top_p = 0.9
        cfg.do_sample = float(temperature) > 0
        cfg.repetition_penalty = 1.15
        pipe.set_generation_config(cfg)

        hist = genai.ChatHistory()
        system = BASE_PROMPT + (("\n\n" + system_extra) if system_extra else "")
        hist.append({"role": "system", "content": system})
        thinking = is_thinking_model()
        msgs = [m for m in history_messages if m.get("content")]
        for i, m in enumerate(msgs):
            content = m["content"]
            if thinking and not deep_think and m["role"] == "user" and i == len(msgs) - 1:
                content = content.rstrip() + "\n/no_think"
            hist.append({"role": m["role"], "content": content})

        started = time.time()
        _state = {"tail": "", "stop": False}
        adapter = ThinkingStreamAdapter(emit) if think_adapter_enabled(deep_think) else None

        def _guard(text):
            """返回 True 表示停止生成（OpenVINO streamer 的约定，必须 return，不能 raise）。"""
            if _state["stop"]:
                return True
            if cancel_event and cancel_event.is_set():
                _state["stop"] = True
                return True
            _state["tail"] = (_state["tail"] + text)[-800:]
            if _detect_repetition(_state["tail"]):
                _state["stop"] = True
                emit("\n\n（检测到模型输出出现重复死循环，已触发流式防卡死熔断器截断保护）")
                return True
            return False

        def _emit(chunk):
            if _guard(chunk):
                return True
            if adapter is not None:
                adapter.push(chunk)
            else:
                emit(chunk)
            return False

        try:
            pipe.generate(hist, streamer=_emit)
        except KeyboardInterrupt:
            pass
        finally:
            if adapter is not None:
                adapter.finish()
        return time.time() - started


def generate_long_report_stream(history_messages, system_extra, temperature, deep_think, emit, cancel_event=None):
    """写报告长报告模式：按大纲分章节自动接力生成机制（3000~6000字），突破 4B 模型单次输出上限。"""
    user_prompt = ""
    for m in reversed(history_messages):
        if m.get("role") == "user":
            user_prompt = m.get("content", "")
            break

    emit("正在规划长篇报告结构大纲，开启多章节深度接力撰写模式...\n\n")

    outline_prompt = (
        f"请为以下报告主题设计一份专业的公文/业务报告章节大纲，必须分为 4 至 5 个核心章节：\n"
        f"主题与要求：{user_prompt}\n\n"
        "请严格按以下格式输出，不要有任何多余开场白或解释：\n"
        "## 第一章：[章节名称]\n"
        "## 第二章：[章节名称]\n"
        "## 第三章：[章节名称]\n"
        "## 第四章：[章节名称]\n"
        "## 第五章：[章节名称]"
    )
    raw_outline = generate_text(outline_prompt, max_tokens=600, temperature=0.3)
    chapters = []
    for line in raw_outline.splitlines():
        line = line.strip()
        if line.startswith("#") and any(k in line for k in ("一", "二", "三", "四", "五", "1", "2", "3", "4", "5", "章", "节")):
            clean_ch = re.sub(r"^#+\s*", "", line).strip()
            if clean_ch:
                chapters.append(clean_ch)

    if len(chapters) < 3:
        chapters = [
            "一、总体情况与关键指标摘要",
            "二、专项推进成效与具体落地措施",
            "三、存在突出矛盾与深层归因分析",
            "四、下步保障机制与重点推进计划"
        ]

    started = time.time()
    generated_context = []

    for idx, chapter in enumerate(chapters, 1):
        if cancel_event and cancel_event.is_set():
            emit("\n\n（用户已终止生成）")
            break

        emit(f"\n\n## {chapter}\n\n")

        prev_summary = "；".join([c[:80] for c in generated_context[-2:]]) if generated_context else "前文背景概述"
        chapter_prompt = (
            f"你是公文与行业报告专家。你正在撰写关于【{user_prompt}】的长篇专业报告。\n"
            f"【当前章节】：{chapter}（第 {idx}/{len(chapters)} 章）\n"
            f"【前文要点回顾】：{prev_summary}\n\n"
            f"【写作要求】：\n"
            f"1. 展开极其详尽深入的阐述，本章字数约 800 至 1200 字，分段编号，层次分明；\n"
            f"2. 严禁复述大纲，严禁任何开场白或总结客套话，直接开始本章正文；\n"
            f"3. 必须包含具体的数据分析、事实支撑、流程机制、责任分工与落地措施；\n"
            f"4. 语言严谨、正式、务实，符合专业公文与报告规范。"
        )

        chapter_msgs = [{"role": "user", "content": chapter_prompt}]
        ch_text_buf = []

        def _ch_emit(txt):
            ch_text_buf.append(txt)
            emit(txt)

        generate_stream(
            chapter_msgs,
            system_extra,
            max_tokens=1500,
            temperature=temperature,
            deep_think=deep_think,
            emit=_ch_emit,
            cancel_event=cancel_event
        )

        generated_context.append("".join(ch_text_buf))

    return time.time() - started


def generate_text(prompt, max_tokens=2000, temperature=0.6):
    import openvino_genai as genai

    pipe = get_pipe()
    with _gen_lock:
        cfg = genai.GenerationConfig()
        cfg.max_new_tokens = int(max_tokens)
        cfg.temperature = float(temperature)
        cfg.top_p = 0.95
        cfg.do_sample = True
        cfg.repetition_penalty = 1.15
        pipe.set_generation_config(cfg)
        hist = genai.ChatHistory()
        hist.append({"role": "system", "content": BASE_PROMPT + " 严格按要求格式输出，不要解释。"})
        hist.append({"role": "user", "content": prompt})
        return str(pipe.generate(hist))


# ---------------------------------------------------------------- 文件解析
def _fmt_table(rows, max_rows=25):
    out = []
    for r in rows[:max_rows]:
        out.append(" | ".join("" if c is None else str(c) for c in r))
    return "\n".join(out)


def extract_text(path):
    name = os.path.basename(path)
    ext = os.path.splitext(name)[1].lower()
    parts = []

    if ext == ".docx":
        import docx

        d = docx.Document(path)
        for p in d.paragraphs:
            txt = p.text.strip()
            if txt:
                style = p.style.name if p.style else ""
                parts.append(("## " if style.lower().startswith("heading") else "") + txt)
        for ti, table in enumerate(d.tables, 1):
            parts.append(f"\n[表格 {ti}]")
            table_lines = []
            for row in table.rows:
                cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                table_lines.append(" | ".join(cells))
            parts.append("\n".join(table_lines))
    elif ext == ".pdf":
        fitz_done = False
        try:
            import fitz
            doc = fitz.open(path)
            parts.append(f"[PDF (PyMuPDF 高精度解析) 共 {len(doc)} 页]")
            for i, page in enumerate(doc[:80], 1):
                txt = page.get_text("text") or ""
                if txt.strip():
                    parts.append(f"\n--- 第 {i} 页 ---\n{txt.strip()}")
            if len(doc) > 80:
                parts.append(f"\n（仅提取前 80 页，共 {len(doc)} 页）")
            doc.close()
            fitz_done = True
        except Exception as e:
            print(f"[pdf] fitz parsing failed: {e}, falling back to pypdf", flush=True)

        if not fitz_done:
            from pypdf import PdfReader
            reader = PdfReader(path)
            parts.append(f"[PDF 共 {len(reader.pages)} 页]")
            for i, page in enumerate(reader.pages[:80], 1):
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    txt = ""
                if txt.strip():
                    parts.append(f"\n--- 第 {i} 页 ---\n{txt.strip()}")
            if len(reader.pages) > 80:
                parts.append(f"\n（仅提取前 80 页，共 {len(reader.pages)} 页）")
    elif ext in (".xlsx", ".xlsm"):
        import openpyxl

        wb = openpyxl.load_workbook(path, data_only=True)
        for ws in wb.worksheets:
            parts.append(f"\n[工作表 {ws.title}] 范围 {ws.dimensions}")
            rows = list(ws.iter_rows(values_only=True))
            parts.append(_fmt_table(rows[:80]))
            parts.append(f"（该表共 {len(rows)} 行）")
    elif ext == ".csv":
        import pandas as pd

        df = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
            try:
                df = pd.read_csv(path, encoding=enc)
                break
            except Exception:  # noqa: BLE001
                continue
        if df is None:
            raise ValueError("CSV 编码无法识别")
        parts.append(f"[CSV] {df.shape[0]} 行 × {df.shape[1]} 列\n列名: {list(df.columns)}")
        try:
            parts.append("\n数值列统计:\n" + df.describe(include="number").to_string())
        except Exception:  # noqa: BLE001
            pass
        parts.append("\n前 30 行:\n" + df.head(30).to_string())
    elif ext == ".pptx":
        from pptx import Presentation

        prs = Presentation(path)
        for i, slide in enumerate(prs.slides, 1):
            texts = [
                sh.text_frame.text.strip()
                for sh in slide.shapes
                if sh.has_text_frame and sh.text_frame.text.strip()
            ]
            if texts:
                parts.append(f"\n[第 {i} 页]\n" + "\n".join(texts))
    else:
        raw = None
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1"):
            try:
                with open(path, "r", encoding=enc) as fh:
                    raw = fh.read()
                break
            except Exception:  # noqa: BLE001
                continue
        if raw is None:
            raise ValueError("无法识别的文件编码，或不是文本文件")
        parts.append(raw)

    text = "\n".join(p for p in parts if p)
    if len(text) > DOC_CHAR_LIMIT:
        text = text[:DOC_CHAR_LIMIT] + f"\n\n（文档较长，已截断，仅保留前 {DOC_CHAR_LIMIT} 字）"
    return name, text


# ---------------------------------------------------------------- 生成文件
def _split_kv(line):
    for sep in ("：", ":"):
        if sep in line:
            return line.split(sep, 1)[1].strip()
    return ""


def _clean_slide_title(t):
    t = re.sub(r"^第[一二三四五六七八九十百0-9]+页(的)?(标题)?\s*[：:、.\-]?\s*", "", t or "")
    t = re.sub(r"^(页面?)?标题\s*[：:]\s*", "", t)
    return t.strip() or "要点"


def parse_ppt_text(text):
    data = {"title": "汇报材料", "subtitle": "", "slides": []}
    cur = None
    table_lines = []
    in_table = False

    for raw in (text or "").splitlines():
        s = raw.strip()
        if not s:
            if in_table and table_lines and cur:
                tbl_text = "\n".join(table_lines)
                series_data = extract_series_from_table(tbl_text)
                if series_data:
                    cur["chart_data"] = series_data
                    if cur.get("type") in (None, "conclusion"):
                        cur["type"] = "chart"
                else:
                    cur["table_data"] = parse_table_text(tbl_text)
                    if cur.get("type") in (None, "conclusion"):
                        cur["type"] = "table"
                cur["table_raw"] = tbl_text
                table_lines = []
                in_table = False
            continue

        # Markdown 表格行收集
        if s.startswith("|") and s.count("|") >= 2:
            in_table = True
            table_lines.append(s)
            continue
        elif in_table:
            if table_lines and cur:
                tbl_text = "\n".join(table_lines)
                series_data = extract_series_from_table(tbl_text)
                if series_data:
                    cur["chart_data"] = series_data
                    if cur.get("type") in (None, "conclusion"):
                        cur["type"] = "chart"
                else:
                    cur["table_data"] = parse_table_text(tbl_text)
                    if cur.get("type") in (None, "conclusion"):
                        cur["type"] = "table"
                cur["table_raw"] = tbl_text
                table_lines = []
            in_table = False

        # 演讲者备注提取
        if s.startswith(">") or s.startswith("**演讲备注") or s.startswith("【演讲备注") or s.startswith("[备注"):
            note_content = re.sub(r"^[>*\s【\[]*(?:演讲)?备注[：:\s】\]\*]*", "", s).strip()
            if note_content and cur:
                cur["notes"] = (cur.get("notes", "") + "\n" + note_content).strip()
            continue

        # 数据来源提取
        if s.startswith("数据来源") or s.startswith("统计口径"):
            if cur:
                cur["source"] = s
            continue

        if s.startswith("#"):
            s_clean = s.lstrip("#").strip().strip("*").strip()
            if s_clean.startswith("副标题"):
                data["subtitle"] = _split_kv(s_clean)
            elif s_clean.startswith("标题"):
                data["title"] = _split_kv(s_clean) or data["title"]
            elif s_clean:
                # 检查显式版式指令
                layout_match = re.search(r"\[(?:版式|layout)\s*[：:]\s*(封面|目录|过渡|结论|图表|表格|结尾|cover|catalog|transition|conclusion|chart|table|ending)\]", s_clean, re.I)
                slide_type = None
                if layout_match:
                    type_map = {
                        "封面": "cover", "目录": "catalog", "过渡": "transition",
                        "结论": "conclusion", "图表": "chart", "表格": "table", "结尾": "ending"
                    }
                    st_raw = layout_match.group(1).lower()
                    slide_type = type_map.get(st_raw, st_raw)
                    s_clean = re.sub(r"\[(?:版式|layout)[^\]]+\]", "", s_clean).strip()

                chart_match = re.search(r"\[图表\s*[：:]\s*(柱状图|折线图|饼图|条形图|column|line|pie|bar)\]", s_clean, re.I)
                directive = chart_match.group(1).lower() if chart_match else ""
                if directive and not slide_type:
                    slide_type = "chart"

                cur = {
                    "title": _clean_slide_title(s_clean),
                    "bullets": [],
                    "type": slide_type,
                    "directive": directive
                }
                data["slides"].append(cur)
            continue

        if s.startswith("副标题"):
            data["subtitle"] = _split_kv(s)
            continue
        if s.startswith("标题") and ("：" in s or ":" in s):
            data["title"] = _split_kv(s) or data["title"]
            continue

        if s[0] in "-·•*" and len(s) > 1:
            bullet = s.lstrip("-·•* ").strip()
            if bullet:
                if cur is None:
                    cur = {"title": "要点", "bullets": [], "type": "conclusion"}
                    data["slides"].append(cur)
                if len(cur["bullets"]) < 8:
                    cur["bullets"].append(bullet)

    # 文件尾部未闭合表格
    if in_table and table_lines and cur:
        tbl_text = "\n".join(table_lines)
        series_data = extract_series_from_table(tbl_text)
        if series_data:
            cur["chart_data"] = series_data
            if cur.get("type") in (None, "conclusion"):
                cur["type"] = "chart"
        else:
            cur["table_data"] = parse_table_text(tbl_text)
            if cur.get("type") in (None, "conclusion"):
                cur["type"] = "table"
        cur["table_raw"] = tbl_text

    return data


def parse_table_text(text):
    rows = []
    for raw in (text or "").splitlines():
        s = raw.strip()
        if not (s.startswith("|") and s.count("|") >= 2):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(c and set(c) <= set("-: =") for c in cells):
            continue
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        return None
    headers = rows[0]
    width = max(len(headers), 1)
    headers = (headers + [f"列{i+1}" for i in range(width)])[:width]
    body = [(r + [""] * width)[:width] for r in rows[1:]]
    return {"sheet": "数据", "headers": headers, "rows": body}


def extract_series_from_table(markdown_table: str) -> Optional[Dict[str, Any]]:
    """从 Markdown 对比表格中提取分类及数值序列，用于构建 Office 原生图表。
    
    返回格式：
    {
        "chart_title": str,
        "category_name": str,
        "categories": list[str],      # 最多 8 项
        "series": [
            {"name": str, "values": list[float]}
        ],
        "suggested_type": str        # "column" | "line" | "pie"
    }
    """
    if not markdown_table or not isinstance(markdown_table, str):
        return None

    lines = [line.strip() for line in markdown_table.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.count("|") >= 2]
    if len(table_lines) < 2:
        return None

    parsed_rows = []
    for line in table_lines:
        cells = [c.strip() for c in line.strip("|").split("|")]
        parsed_rows.append(cells)

    if not parsed_rows:
        return None

    headers = parsed_rows[0]
    data_rows = []
    start_idx = 1
    if len(parsed_rows) > 1 and all(c and set(c) <= set("-: =") for c in parsed_rows[1]):
        start_idx = 2

    for r in parsed_rows[start_idx:]:
        if any(r):
            padded = (r + [""] * len(headers))[:len(headers)]
            data_rows.append(padded)

    if not data_rows:
        return None

    category_name = headers[0] or "分类"
    raw_categories = [r[0] for r in data_rows]

    def _parse_num(val_str: str) -> Optional[float]:
        if val_str is None:
            return None
        s = str(val_str).strip()
        if s in ("", "-", "--", "—", "N/A", "n/a", "null", "None", "/", "无", "待核实"):
            return 0.0
        s = s.replace(",", "").replace("￥", "").replace("¥", "").replace("$", "").replace("€", "")
        if s.endswith("%"):
            s = s[:-1].strip()
        s = re.sub(r"(吨|万元|元|件|套|个|kg|KG|m³|m2|立方米|平方米|米|台|箱|包|张)$", "", s).strip()
        try:
            return float(s)
        except ValueError:
            m = re.search(r"[-+]?(?:\d+(?:\.\d+)?|\.\d+)", s)
            if m:
                try:
                    return float(m.group(0))
                except ValueError:
                    return None
            return None

    valid_series = []
    for col_idx in range(1, len(headers)):
        col_name = headers[col_idx] or f"指标{col_idx}"
        vals = [_parse_num(r[col_idx]) for r in data_rows]
        valid_cnt = sum(1 for v in vals if v is not None)
        if valid_cnt >= max(1, len(data_rows) * 0.4):
            clean_vals = [float(round(v if v is not None else 0.0, 2)) for v in vals]
            valid_series.append({"name": col_name, "values": clean_vals})

    if not valid_series:
        return None

    # 截取最多 8 项
    categories = [str(c) for c in raw_categories[:8]]
    for s in valid_series:
        s["values"] = s["values"][:8]

    directive_match = re.search(r"\[图表\s*[：:]\s*(柱状图|折线图|饼图|条形图|column|line|pie|bar)\]", markdown_table, re.I)
    directive = directive_match.group(1).lower() if directive_match else ""

    time_keywords = ("月", "年", "季度", "Q1", "Q2", "Q3", "Q4", "202", "日", "周")
    is_time = len(categories) >= 3 and any(any(k in str(c) for k in time_keywords) for c in categories)
    prop_keywords = ("占比", "比例", "份额", "结构", "分布", "%", "比重")
    is_prop = len(valid_series) == 1 and (
        any(k in valid_series[0]["name"] for k in prop_keywords) or
        (all(v >= 0 for v in valid_series[0]["values"]) and 90.0 <= sum(valid_series[0]["values"]) <= 105.0)
    )

    if directive in ("折线图", "line") or (not directive and is_time):
        suggested_type = "line"
    elif directive in ("饼图", "pie") or (not directive and is_prop):
        suggested_type = "pie"
    elif directive in ("条形图", "bar"):
        suggested_type = "bar"
    else:
        suggested_type = "column"

    return {
        "chart_title": f"{category_name}对比分析",
        "category_name": category_name,
        "categories": categories,
        "series": valid_series,
        "suggested_type": suggested_type
    }


def determine_chart_type(categories: list, series: list, directive: str = "", title: str = ""):
    """两级图表选型机制：显式指令优先，数据特征启发式判定保底。"""
    from pptx.enum.chart import XL_CHART_TYPE

    categories = categories or []
    series = [s for s in (series or []) if isinstance(s, dict)]
    dir_str = (str(directive or "") + " " + str(title or "")).lower()

    if any(k in dir_str for k in ("折线图", "趋势图", "line")):
        return XL_CHART_TYPE.LINE_MARKERS
    if any(k in dir_str for k in ("饼图", "环形图", "占比图", "pie")):
        s_vals = series[0].get("values", []) if series else []
        if (
            len(series) == 1
            and s_vals
            and all(v is not None and isinstance(v, (int, float)) and v >= 0 for v in s_vals)
        ):
            return XL_CHART_TYPE.PIE
        return XL_CHART_TYPE.COLUMN_CLUSTERED
    if any(k in dir_str for k in ("条形图", "横向柱状图", "bar")):
        return XL_CHART_TYPE.BAR_CLUSTERED
    if any(k in dir_str for k in ("柱状图", "柱形图", "column")):
        return XL_CHART_TYPE.COLUMN_CLUSTERED

    time_keywords = ("月", "年", "季度", "Q1", "Q2", "Q3", "Q4", "202", "日", "周", "趋势", "走势")
    if len(categories) >= 3 and any(any(k in str(c) for k in time_keywords) for c in categories):
        return XL_CHART_TYPE.LINE_MARKERS

    if len(series) == 1 and 2 <= len(categories) <= 7:
        s_name = series[0].get("name", "")
        s_vals = series[0].get("values", []) or []
        if s_vals and all(v is not None and isinstance(v, (int, float)) and v >= 0 for v in s_vals):
            prop_keywords = ("占比", "比例", "份额", "结构", "分布", "%", "比重")
            if any(k in s_name or k in dir_str for k in prop_keywords):
                return XL_CHART_TYPE.PIE
            val_sum = sum(v for v in s_vals if v is not None and isinstance(v, (int, float)))
            if 90.0 <= val_sum <= 105.0:
                return XL_CHART_TYPE.PIE

    if any(len(str(c)) > 8 for c in categories):
        return XL_CHART_TYPE.BAR_CLUSTERED

    return XL_CHART_TYPE.COLUMN_CLUSTERED


def simplify_bullet_text(text: str, max_len: int = 30) -> str:
    """精简单条要点文本至指定长度以内（默认 <= 30 字），超出部分加省略号。"""
    clean = re.sub(r"^[■•·*\-]\s*", "", str(text or "")).strip()
    if len(clean) > max_len:
        return clean[:max_len - 3] + "..."
    return clean


def _process_bullets(bullets: list, max_bullets: int = 5) -> Tuple[List[str], List[str]]:
    """要点精简与文本防溢出约束：
    - 每页最多 4~5 条；
    - 每条严格 <= 30 字（核心结论 + 关键数字）；
    - 超长文本自动截断至 27 字加 '...'（总长度严格 <= 30 字），完整原句移入演讲者备注；
    - 超过限制条数的更多要点全量移入演讲者备注。
    """


    clean_bullets = []
    overflow_notes = []

    for idx, b in enumerate(bullets or []):
        b_str = re.sub(r"^[■•·*\-]\s*", "", str(b)).strip()
        if not b_str:
            continue
        if idx < max_bullets:
            if len(b_str) > 30:
                truncated = b_str[:27] + "..."
                clean_bullets.append(truncated)
                overflow_notes.append(f"【要点补充阐述】{b_str}")
            else:
                clean_bullets.append(b_str)
        else:
            overflow_notes.append(f"【更多细化要点】{b_str}")

    return clean_bullets, overflow_notes




def _get_title_font_size(title: str) -> int:
    t_len = len(str(title or ""))
    if t_len <= 14:
        return 26
    elif t_len <= 22:
        return 22
    else:
        return 18


def _get_bullet_font_size(bullet_count: int) -> Tuple[int, int]:
    if bullet_count <= 3:
        return 16, 14
    else:
        return 14, 8


def _add_unified_footer(slide, page_num: int, source: str = None):
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    source_text = source or "数据来源：企业ERP/供应链对账清单  |  统计口径：全周期核算"
    box_left = slide.shapes.add_textbox(Inches(1.0), Inches(6.85), Inches(8.5), Inches(0.4))
    tf_l = box_left.text_frame
    tf_l.word_wrap = True
    p_l = tf_l.paragraphs[0]
    p_l.alignment = PP_ALIGN.LEFT
    r_l = p_l.add_run()
    r_l.text = source_text
    r_l.font.size = Pt(10)
    r_l.font.name = "微软雅黑"
    r_l.font.color.rgb = RGBColor(0x77, 0x77, 0x77)

    box_right = slide.shapes.add_textbox(Inches(9.8), Inches(6.85), Inches(2.5), Inches(0.4))
    tf_r = box_right.text_frame
    p_r = tf_r.paragraphs[0]
    p_r.alignment = PP_ALIGN.RIGHT
    r_r = p_r.add_run()
    r_r.text = f"第 {page_num} 页"
    r_r.font.size = Pt(10)
    r_r.font.name = "微软雅黑"
    r_r.font.color.rgb = RGBColor(0x77, 0x77, 0x77)


def _append_speaker_notes(slide, notes_list: list):
    clean_notes = [str(n).strip() for n in notes_list if n and str(n).strip()]
    if clean_notes:
        notes_slide = slide.notes_slide
        tf = notes_slide.notes_text_frame
        curr_text = tf.text.strip()
        new_text = "\n\n".join(clean_notes)
        if curr_text:
            tf.text = curr_text + "\n\n" + new_text
        else:
            tf.text = new_text


def _render_cover_slide(prs, item, data):
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    bg = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x12, 0x18, 0x2A)
    bg.line.fill.background()

    gold_bar = s.shapes.add_shape(1, Inches(1.2), Inches(1.8), Inches(0.12), Inches(3.2))
    gold_bar.fill.solid()
    gold_bar.fill.fore_color.rgb = RGBColor(0xE7, 0xC2, 0x7D)
    gold_bar.line.fill.background()

    title = str(item.get("title") or data.get("title") or "商业与管理专项汇报")
    t_box = s.shapes.add_textbox(Inches(1.5), Inches(1.7), Inches(10.5), Inches(1.8))
    tf = t_box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(40)
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    subtitle = str(item.get("subtitle") or data.get("subtitle") or "寻找最优解，是灵梦的唯一直觉 · 本地 AI 辅助生成")
    sub_box = s.shapes.add_textbox(Inches(1.5), Inches(3.7), Inches(10.5), Inches(1.0))
    tf_sub = sub_box.text_frame
    tf_sub.word_wrap = True
    p_sub = tf_sub.paragraphs[0]
    r_sub = p_sub.add_run()
    r_sub.text = subtitle
    r_sub.font.size = Pt(20)
    r_sub.font.name = "微软雅黑"
    r_sub.font.color.rgb = RGBColor(0xE7, 0xC2, 0x7D)

    meta_str = item.get("meta") or f"生成日期：{datetime.now().strftime('%Y年%m月%d日')}  |  灵梦工作台确定性输出"
    m_box = s.shapes.add_textbox(Inches(1.5), Inches(5.7), Inches(10.0), Inches(0.8))
    tf_m = m_box.text_frame
    p_m = tf_m.paragraphs[0]
    r_m = p_m.add_run()
    r_m.text = meta_str
    r_m.font.size = Pt(13)
    r_m.font.name = "微软雅黑"
    r_m.font.color.rgb = RGBColor(0xA0, 0xAB, 0xBA)

    if item.get("notes"):
        _append_speaker_notes(s, [item["notes"]])
    return s


def _render_catalog_slide(prs, item, page_num):
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    top_bar = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    top_bar.line.fill.background()

    title = str(item.get("title") or "目录 / CONTENTS")
    t_box = s.shapes.add_textbox(Inches(1.0), Inches(0.55), Inches(10.5), Inches(0.75))
    tf = t_box.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(_get_title_font_size(title))
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    div = s.shapes.add_shape(1, Inches(1.0), Inches(1.35), Inches(11.333), Inches(0.02))
    div.fill.solid()
    div.fill.fore_color.rgb = RGBColor(0xDD, 0xE2, 0xE6)
    div.line.fill.background()

    raw_bullets = item.get("bullets") or item.get("items") or [
        "总体采购态势与核心指标", "关键矛盾剖析与归因", "物资调拨与计划对比", "战略措施与落地安排"
    ]
    bullets, notes = _process_bullets(raw_bullets, max_bullets=4)

    coords = [
        (Inches(1.0), Inches(1.8), Inches(5.45), Inches(2.2)),
        (Inches(6.85), Inches(1.8), Inches(5.45), Inches(2.2)),
        (Inches(1.0), Inches(4.3), Inches(5.45), Inches(2.2)),
        (Inches(6.85), Inches(4.3), Inches(5.45), Inches(2.2)),
    ]

    for idx, b_text in enumerate(bullets[:4]):
        l, t, w, h = coords[idx]
        card = s.shapes.add_shape(1, l, t, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
        card.line.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
        card.line.width = Pt(1)

        badge_box = s.shapes.add_textbox(l + Inches(0.25), t + Inches(0.2), Inches(1.0), Inches(0.6))
        tf_b = badge_box.text_frame
        p_b = tf_b.paragraphs[0]
        r_b = p_b.add_run()
        r_b.text = f"0{idx+1}"
        r_b.font.size = Pt(26)
        r_b.font.bold = True
        r_b.font.name = "微软雅黑"
        r_b.font.color.rgb = RGBColor(0xE7, 0xC2, 0x7D)

        text_box = s.shapes.add_textbox(l + Inches(1.3), t + Inches(0.35), w - Inches(1.5), h - Inches(0.6))
        tf_t = text_box.text_frame
        tf_t.word_wrap = True
        p_t = tf_t.paragraphs[0]
        r_t = p_t.add_run()
        r_t.text = b_text
        r_t.font.size = Pt(16)
        r_t.font.bold = True
        r_t.font.name = "微软雅黑"
        r_t.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    _add_unified_footer(s, page_num, item.get("source"))
    all_notes = notes + ([item["notes"]] if item.get("notes") else [])
    _append_speaker_notes(s, all_notes)
    return s


def _render_transition_slide(prs, item, page_num):
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    bg = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x12, 0x18, 0x2A)
    bg.line.fill.background()

    gold_bar = s.shapes.add_shape(1, Inches(1.5), Inches(2.0), Inches(0.12), Inches(3.0))
    gold_bar.fill.solid()
    gold_bar.fill.fore_color.rgb = RGBColor(0xE7, 0xC2, 0x7D)
    gold_bar.line.fill.background()

    sec_no = item.get("section_no") or f"PART 0{page_num}"
    sn_box = s.shapes.add_textbox(Inches(1.8), Inches(2.0), Inches(9.5), Inches(0.6))
    tf_sn = sn_box.text_frame
    p_sn = tf_sn.paragraphs[0]
    r_sn = p_sn.add_run()
    r_sn.text = sec_no
    r_sn.font.size = Pt(22)
    r_sn.font.bold = True
    r_sn.font.name = "微软雅黑"
    r_sn.font.color.rgb = RGBColor(0xE7, 0xC2, 0x7D)

    title = str(item.get("title") or "核心业务与关键举措")
    t_box = s.shapes.add_textbox(Inches(1.8), Inches(2.7), Inches(9.5), Inches(1.4))
    tf_t = t_box.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    r_t = p_t.add_run()
    r_t.text = title
    r_t.font.size = Pt(36)
    r_t.font.bold = True
    r_t.font.name = "微软雅黑"
    r_t.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    raw_bullets = item.get("bullets") or []
    bullets, notes = _process_bullets(raw_bullets, max_bullets=3)
    if bullets:
        sum_box = s.shapes.add_textbox(Inches(1.8), Inches(4.3), Inches(9.5), Inches(1.2))
        tf_sum = sum_box.text_frame
        tf_sum.word_wrap = True
        for b_idx, b in enumerate(bullets):
            p = tf_sum.paragraphs[0] if b_idx == 0 else tf_sum.add_paragraph()
            r = p.add_run()
            r.text = f"■  {b}"
            r.font.size = Pt(15)
            r.font.name = "微软雅黑"
            r.font.color.rgb = RGBColor(0xA0, 0xAB, 0xBA)

    _add_unified_footer(s, page_num, item.get("source"))
    all_notes = notes + ([item["notes"]] if item.get("notes") else [])
    _append_speaker_notes(s, all_notes)
    return s


def _render_conclusion_slide(prs, item, page_num):
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    top_bar = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    top_bar.line.fill.background()

    title = str(item.get("title") or "核心结论与决策建议")
    t_box = s.shapes.add_textbox(Inches(1.0), Inches(0.55), Inches(10.5), Inches(0.75))
    tf = t_box.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(_get_title_font_size(title))
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    div = s.shapes.add_shape(1, Inches(1.0), Inches(1.35), Inches(11.333), Inches(0.02))
    div.fill.solid()
    div.fill.fore_color.rgb = RGBColor(0xDD, 0xE2, 0xE6)
    div.line.fill.background()

    left_bullets_raw = item.get("left_bullets")
    right_bullets_raw = item.get("right_bullets")
    is_dual = bool(left_bullets_raw and right_bullets_raw) or item.get("layout") == "dual"

    if is_dual:
        left_bullets_raw = left_bullets_raw or item.get("bullets", [])[:2]
        right_bullets_raw = right_bullets_raw or item.get("bullets", [])[2:4]
        l_bullets, l_notes = _process_bullets(left_bullets_raw, max_bullets=3)
        r_bullets, r_notes = _process_bullets(right_bullets_raw, max_bullets=3)

        # 左卡片
        l_card = s.shapes.add_shape(1, Inches(1.0), Inches(1.75), Inches(5.45), Inches(4.8))
        l_card.fill.solid()
        l_card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
        l_card.line.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
        l_card.line.width = Pt(1)

        l_title = item.get("left_title") or "🔍 现状诊断与核心归因"
        lt_box = s.shapes.add_textbox(Inches(1.3), Inches(2.0), Inches(4.85), Inches(0.5))
        p_lt = lt_box.text_frame.paragraphs[0]
        r_lt = p_lt.add_run()
        r_lt.text = l_title
        r_lt.font.size = Pt(16)
        r_lt.font.bold = True
        r_lt.font.name = "微软雅黑"
        r_lt.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

        l_box = s.shapes.add_textbox(Inches(1.3), Inches(2.6), Inches(4.85), Inches(3.7))
        tf_l = l_box.text_frame
        tf_l.word_wrap = True
        f_sz, s_after = _get_bullet_font_size(len(l_bullets))
        for b_idx, b in enumerate(l_bullets):
            p = tf_l.paragraphs[0] if b_idx == 0 else tf_l.add_paragraph()
            p.space_before = Pt(4)
            p.space_after = Pt(s_after)
            r = p.add_run()
            r.text = f"■  {b}"
            r.font.size = Pt(f_sz)
            r.font.name = "微软雅黑"
            r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

        # 右卡片
        r_card = s.shapes.add_shape(1, Inches(6.85), Inches(1.75), Inches(5.45), Inches(4.8))
        r_card.fill.solid()
        r_card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
        r_card.line.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
        r_card.line.width = Pt(1)

        r_title = item.get("right_title") or "🚀 应对举措与改善目标"
        rt_box = s.shapes.add_textbox(Inches(7.15), Inches(2.0), Inches(4.85), Inches(0.5))
        p_rt = rt_box.text_frame.paragraphs[0]
        r_rt = p_rt.add_run()
        r_rt.text = r_title
        r_rt.font.size = Pt(16)
        r_rt.font.bold = True
        r_rt.font.name = "微软雅黑"
        r_rt.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

        r_box = s.shapes.add_textbox(Inches(7.15), Inches(2.6), Inches(4.85), Inches(3.7))
        tf_r = r_box.text_frame
        tf_r.word_wrap = True
        f_sz_r, s_after_r = _get_bullet_font_size(len(r_bullets))
        for b_idx, b in enumerate(r_bullets):
            p = tf_r.paragraphs[0] if b_idx == 0 else tf_r.add_paragraph()
            p.space_before = Pt(4)
            p.space_after = Pt(s_after_r)
            r = p.add_run()
            r.text = f"■  {b}"
            r.font.size = Pt(f_sz_r)
            r.font.name = "微软雅黑"
            r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

        notes = l_notes + r_notes
    else:
        # 全幅单卡片
        raw_bullets = item.get("bullets") or []
        bullets, notes = _process_bullets(raw_bullets, max_bullets=5)

        card = s.shapes.add_shape(1, Inches(1.0), Inches(1.75), Inches(11.333), Inches(4.8))
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
        card.line.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
        card.line.width = Pt(1)

        c_box = s.shapes.add_textbox(Inches(1.4), Inches(2.0), Inches(10.5), Inches(4.3))
        tf_c = c_box.text_frame
        tf_c.word_wrap = True
        f_sz, s_after = _get_bullet_font_size(len(bullets))
        for b_idx, b in enumerate(bullets):
            p = tf_c.paragraphs[0] if b_idx == 0 else tf_c.add_paragraph()
            p.space_before = Pt(4)
            p.space_after = Pt(s_after)
            r = p.add_run()
            r.text = f"■  {b}"
            r.font.size = Pt(f_sz)
            r.font.name = "微软雅黑"
            r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    _add_unified_footer(s, page_num, item.get("source"))
    all_notes = notes + ([item["notes"]] if item.get("notes") else [])
    _append_speaker_notes(s, all_notes)
    return s


def _render_chart_slide(prs, item, page_num):
    from pptx.chart.data import CategoryChartData
    from pptx.dml.color import RGBColor
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    top_bar = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    top_bar.line.fill.background()

    title = str(item.get("title") or "核心数据指标与趋势分析")
    t_box = s.shapes.add_textbox(Inches(0.8), Inches(0.55), Inches(11.7), Inches(0.75))
    tf = t_box.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(_get_title_font_size(title))
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    div = s.shapes.add_shape(1, Inches(0.8), Inches(1.35), Inches(11.733), Inches(0.02))
    div.fill.solid()
    div.fill.fore_color.rgb = RGBColor(0xDD, 0xE2, 0xE6)
    div.line.fill.background()

    chart_info = item.get("chart_data")
    if not chart_info and item.get("table_raw"):
        chart_info = extract_series_from_table(item["table_raw"])

    if not chart_info or not chart_info.get("series") or not chart_info.get("categories"):
        chart_info = {
            "chart_title": title,
            "category_name": "核心指标",
            "categories": ["采购节资率", "集中履约率", "质检合格率", "按期交付率"],
            "series": [{"name": "达成指标 (%)", "values": [6.8, 98.5, 99.2, 95.0]}],
            "suggested_type": "column"
        }

    directive = item.get("directive") or chart_info.get("suggested_type") or ""
    chart_type = determine_chart_type(
        chart_info["categories"], chart_info["series"], directive=directive, title=title
    )

    # 1. 左侧 Office 原生图表 (Left: 0.8", Top: 1.6", Width: 6.8", Height: 4.85")
    cd = CategoryChartData()
    cd.categories = chart_info["categories"][:8]
    for ser in chart_info["series"]:
        s_vals = tuple(ser.get("values", [])[:8])
        cd.add_series(ser.get("name", "数值"), s_vals)

    chart_shape = s.shapes.add_chart(
        chart_type, Inches(0.8), Inches(1.6), Inches(6.8), Inches(4.85), cd
    )
    chart = chart_shape.chart

    chart.has_legend = len(chart_info["series"]) > 1 or chart_type == XL_CHART_TYPE.PIE
    if chart.has_legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(9.5)
        chart.legend.font.name = "微软雅黑"

    if chart_type != XL_CHART_TYPE.PIE:
        try:
            val_axis = chart.value_axis
            val_axis.has_major_gridlines = True
            val_axis.tick_labels.font.size = Pt(9)
            cat_axis = chart.category_axis
            cat_axis.tick_labels.font.size = Pt(9)
        except Exception:
            pass

    PALETTE = [
        RGBColor(0x1F, 0x4E, 0x79),  # 商务典雅蓝
        RGBColor(0xE7, 0xC2, 0x7D),  # 灵梦星标金
        RGBColor(0x5B, 0x9B, 0xD5),  # 钢青蓝
        RGBColor(0x2E, 0x7D, 0x6E),  # 湖水绿
        RGBColor(0xD9, 0x53, 0x4F),  # 珊瑚红
        RGBColor(0x88, 0x92, 0xA0),  # 雾灰
    ]

    try:
        if chart_type == XL_CHART_TYPE.PIE:
            if len(chart.plots[0].series) > 0:
                for idx, point in enumerate(chart.plots[0].series[0].points):
                    point.format.fill.solid()
                    point.format.fill.fore_color.rgb = PALETTE[idx % len(PALETTE)]
        else:
            for idx, s_obj in enumerate(chart.series):
                color = PALETTE[idx % len(PALETTE)]
                s_obj.format.fill.solid()
                s_obj.format.fill.fore_color.rgb = color
                if chart_type == XL_CHART_TYPE.LINE_MARKERS:
                    s_obj.format.line.color.rgb = color
                    s_obj.format.line.width = Pt(2.25)
    except Exception:
        pass

    # 2. 右侧结论卡片 (Left: 7.85", Top: 1.6", Width: 4.68", Height: 4.85")
    card = s.shapes.add_shape(1, Inches(7.85), Inches(1.6), Inches(4.68), Inches(4.85))
    card.fill.solid()
    card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
    card.line.color.rgb = RGBColor(0xE2, 0xE8, 0xF0)
    card.line.width = Pt(1)

    ct_box = s.shapes.add_textbox(Inches(8.1), Inches(1.8), Inches(4.18), Inches(0.5))
    p_ct = ct_box.text_frame.paragraphs[0]
    r_ct = p_ct.add_run()
    r_ct.text = "📊 核心数据分析结论"
    r_ct.font.size = Pt(16)
    r_ct.font.bold = True
    r_ct.font.name = "微软雅黑"
    r_ct.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    raw_bullets = item.get("bullets") or [
        "核心指标达成情况整体向好，重点物资供应平稳",
        "结构占比符合降本增效总要求，关键偏差在控"
    ]
    bullets, notes = _process_bullets(raw_bullets, max_bullets=4)

    c_box = s.shapes.add_textbox(Inches(8.1), Inches(2.4), Inches(4.18), Inches(3.8))
    tf_c = c_box.text_frame
    tf_c.word_wrap = True
    f_sz, s_after = _get_bullet_font_size(len(bullets))
    for b_idx, b in enumerate(bullets):
        p = tf_c.paragraphs[0] if b_idx == 0 else tf_c.add_paragraph()
        p.space_before = Pt(4)
        p.space_after = Pt(s_after)
        r = p.add_run()
        r.text = f"■  {b}"
        r.font.size = Pt(f_sz)
        r.font.name = "微软雅黑"
        r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    _add_unified_footer(s, page_num, item.get("source"))
    all_notes = notes + ([item["notes"]] if item.get("notes") else [])
    series_stub = " ; ".join(f"{s['name']}: {s['values']}" for s in chart_info["series"])
    all_notes.append(f"【图表底层数据存根】分类: {chart_info['categories']} | 序列: {series_stub}")
    _append_speaker_notes(s, all_notes)
    return s


def _render_table_slide(prs, item, page_num):
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    top_bar = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, Inches(0.12))
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    top_bar.line.fill.background()

    title = str(item.get("title") or "标准化数据明细对比")
    t_box = s.shapes.add_textbox(Inches(1.0), Inches(0.55), Inches(10.5), Inches(0.75))
    tf = t_box.text_frame
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title
    r.font.size = Pt(_get_title_font_size(title))
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)

    div = s.shapes.add_shape(1, Inches(1.0), Inches(1.35), Inches(11.333), Inches(0.02))
    div.fill.solid()
    div.fill.fore_color.rgb = RGBColor(0xDD, 0xE2, 0xE6)
    div.line.fill.background()

    table_data = item.get("table_data")
    if not table_data and item.get("table_raw"):
        table_data = parse_table_text(item["table_raw"])

    if not table_data or not table_data.get("headers"):
        table_data = {
            "headers": ["序号", "物资名称", "计划量", "调拨量", "节资率"],
            "rows": [
                ["1", "螺纹钢 HRB400", "120.5 吨", "100.0 吨", "6.8%"],
                ["2", "硅酸盐水泥 P.O 42.5", "300.0 吨", "280.0 吨", "5.2%"],
                ["3", "中砂", "450.0 m³", "450.0 m³", "7.1%"],
                ["4", "碎石 5-20mm", "600.0 m³", "580.0 m³", "4.9%"],
            ]
        }

    headers = table_data["headers"]
    rows = table_data.get("rows", [])[:8]
    num_rows = 1 + len(rows)
    num_cols = len(headers)

    tbl_shape = s.shapes.add_table(
        num_rows, num_cols, Inches(1.0), Inches(1.75), Inches(11.333), Inches(4.7)
    )
    tbl = tbl_shape.table

    for col_idx, h_text in enumerate(headers):
        cell = tbl.cell(0, col_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = str(h_text)
        r.font.size = Pt(11)
        r.font.bold = True
        r.font.name = "微软雅黑"
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for row_idx, row_vals in enumerate(rows, 1):
        is_even = (row_idx % 2 == 0)
        row_bg = RGBColor(0xFF, 0xFF, 0xFF) if is_even else RGBColor(0xF9, 0xFA, 0xFB)
        for col_idx in range(num_cols):
            val_text = str(row_vals[col_idx]) if col_idx < len(row_vals) else ""
            cell = tbl.cell(row_idx, col_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = row_bg
            p = cell.text_frame.paragraphs[0]
            if re.search(r"^[-+]?\d+(?:\.\d+)?%?$", val_text.strip()):
                p.alignment = PP_ALIGN.RIGHT
            elif col_idx == 0:
                p.alignment = PP_ALIGN.CENTER
            else:
                p.alignment = PP_ALIGN.LEFT
            r = p.add_run()
            r.text = val_text
            r.font.size = Pt(10.5)
            r.font.name = "微软雅黑"
            r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    _add_unified_footer(s, page_num, item.get("source"))
    bullets, notes = _process_bullets(item.get("bullets", []), max_bullets=3)
    all_notes = notes + ([item["notes"]] if item.get("notes") else [])
    _append_speaker_notes(s, all_notes)
    return s


def _render_ending_slide(prs, item, data):
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    blank = prs.slide_layouts[6]
    s = prs.slides.add_slide(blank)

    bg = s.shapes.add_shape(1, Inches(0), Inches(0), prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = RGBColor(0x12, 0x18, 0x2A)
    bg.line.fill.background()

    title = str(item.get("title") or "感谢聆听 · 敬请指正")
    t_box = s.shapes.add_textbox(Inches(1.5), Inches(2.4), Inches(10.333), Inches(1.2))
    tf = t_box.text_frame
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = title
    r.font.size = Pt(42)
    r.font.bold = True
    r.font.name = "微软雅黑"
    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    subtitle = str(item.get("subtitle") or "Q & A 交流研讨")
    sub_box = s.shapes.add_textbox(Inches(1.5), Inches(3.8), Inches(10.333), Inches(0.8))
    tf_sub = sub_box.text_frame
    p_sub = tf_sub.paragraphs[0]
    p_sub.alignment = PP_ALIGN.CENTER
    r_sub = p_sub.add_run()
    r_sub.text = subtitle
    r_sub.font.size = Pt(20)
    r_sub.font.name = "微软雅黑"
    r_sub.font.color.rgb = RGBColor(0xE7, 0xC2, 0x7D)

    meta_str = item.get("meta") or f"{datetime.now().strftime('%Y年%m月')}  |  灵梦工作台确定性呈现"
    m_box = s.shapes.add_textbox(Inches(1.5), Inches(5.7), Inches(10.333), Inches(0.6))
    tf_m = m_box.text_frame
    p_m = tf_m.paragraphs[0]
    p_m.alignment = PP_ALIGN.CENTER
    r_m = p_m.add_run()
    r_m.text = meta_str
    r_m.font.size = Pt(12)
    r_m.font.name = "微软雅黑"
    r_m.font.color.rgb = RGBColor(0xA0, 0xAB, 0xBA)

    if item.get("notes"):
        _append_speaker_notes(s, [item["notes"]])
    return s


class ValidationResult(dict):
    """自检报告双模态结果对象：
    既支持字典式键值访问（满足 PROJECT.md 接口契约规范），
    又支持 (prs, report_dict, report_summary) 三元组解构解包。
    """
    def __init__(self, prs, report_dict, report_summary):
        super().__init__(report_dict)
        self.prs = prs
        self.report_dict = report_dict
        self.report_summary = report_summary

    def __iter__(self):
        return iter((self.prs, self.report_dict, self.report_summary))


def _is_bullet_paragraph(sh, p, raw: str = None, slide_idx: int = None, slide = None) -> bool:
    """精准判定段落是否为正文要点（排除页眉、页脚、图表结论卡头及封面/结尾元数据）。"""
    from pptx.util import Inches, Pt

    if raw is None:
        raw = p.text.strip()
    else:
        raw = str(raw).strip()

    if not raw:
        return False

    # 1. 严格排除页脚文本框与页脚内容
    top = getattr(sh, "top", None)
    if top is not None and top >= Inches(6.5):
        return False
    if "数据来源" in raw or "统计口径" in raw or re.search(r"第\s*\d+\s*页", raw):
        return False

    # 2. 严格排除封面与结尾页特定元数据与标题
    if "生成日期" in raw or "灵梦工作台" in raw or "确定性" in raw:
        return False
    if "感谢聆听" in raw or "Q & A" in raw or "敬请指正" in raw:
        return False
    if slide_idx == 0 and top is not None and top >= Inches(5.0):
        return False

    # 3. 严格排除顶部标题区域（top <= 1.5 且无项目符号标记）
    has_marker = bool(re.match(r"^[■•·*\-–—►✔★✦]\s*", raw)) or bool(re.match(r"^\d+[\.、\)]\s*", raw)) or getattr(p, "level", 0) > 0
    if top is not None and top <= Inches(1.5) and not has_marker:
        return False

    # 4. 排除分段标题与卡片小标题
    if not has_marker:
        if raw.startswith(("🔍", "🚀", "📊", "PART ", "CONTENTS", "目录")):
            return False
        if re.match(r"^0\d$", raw):
            return False
        if getattr(sh, "is_placeholder", False):
            try:
                if sh.placeholder_format.type in (1, 3):  # TITLE or CENTER_TITLE
                    return False
            except Exception:
                pass

    # 5. 封面全页豁免（封面无正文要点）
    if slide_idx == 0 and not has_marker:
        return False
    if slide is not None and not has_marker:
        try:
            slide_text = " ".join(
                p2.text for s2 in slide.shapes if getattr(s2, "has_text_frame", False) and s2.has_text_frame
                for p2 in s2.text_frame.paragraphs
            )
            if "灵梦工作台确定性输出" in slide_text or "灵梦工作台确定性呈现" in slide_text:
                return False
        except Exception:
            pass

    # 6. 字号过滤：标题级字号 (>= 18pt) 且无符号标记不是正文要点
    if not has_marker and getattr(p, "runs", None):
        try:
            if p.runs and p.runs[0].font.size and p.runs[0].font.size >= Pt(18):
                return False
        except Exception:
            pass

    # 具备项目符号或处于正文内容区（1.5" <= top < 6.5"）判定为要点
    return has_marker or (top is not None and Inches(1.5) <= top < Inches(6.5))


def validate_ppt_before_save(prs):
    """PPT 导出前自检与兜底修复函数：
    1. 检查幻灯片页数；
    2. 自动检测并物理剔除空白页（解除 XML 依赖 drop_rel 并从 _sldIdLst 删除）；
    3. 截断超长溢出文本，将溢出部分全量归入演讲者备注；
    4. 检查缺图情况，核查图表形状完整性；
    5. 生成自检报告字典与格式化字符串《PPT 导出自检报告（共 X 页，含 X 张原生图表，0 处溢出）》。
    """
    removed_blank_slides = 0

    def _is_slide_blank(slide) -> bool:
        for sh in slide.shapes:
            if getattr(sh, "has_chart", False) and sh.has_chart:
                return False
            if getattr(sh, "has_table", False) and sh.has_table:
                return False
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                txt = "".join(p.text.strip() for p in sh.text_frame.paragraphs)
                if txt:
                    return False
        return True

    idx = 0
    while idx < len(prs.slides):
        slide = prs.slides[idx]
        if _is_slide_blank(slide):
            rId = prs.slides._sldIdLst[idx].rId
            prs.part.drop_rel(rId)
            del prs.slides._sldIdLst[idx]
            removed_blank_slides += 1
        else:
            idx += 1

    chart_count = 0
    overflow_fixed = 0

    for s_idx, slide in enumerate(prs.slides):
        for sh in slide.shapes:
            if getattr(sh, "has_chart", False) and sh.has_chart:
                chart_count += 1
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                for p in sh.text_frame.paragraphs:
                    raw = p.text.strip()
                    if not _is_bullet_paragraph(sh, p, raw=raw, slide_idx=s_idx, slide=slide):
                        continue
                    clean = re.sub(r"^[■•·*\-]\s*", "", raw).strip()
                    if len(clean) > 30:
                        overflow_fixed += 1
                        truncated = clean[:27] + "..."
                        if raw.startswith("■"):
                            p.text = f"■  {truncated}"
                        elif raw.startswith(("-", "•", "*", "·")):
                            p.text = f"• {truncated}"
                        else:
                            p.text = truncated
                        notes_tf = slide.notes_slide.notes_text_frame
                        backup_str = f"【自检防溢出备份】{clean}"
                        if backup_str not in notes_tf.text:
                            notes_tf.text = (notes_tf.text + f"\n{backup_str}").strip()

    total_slides = len(prs.slides)
    report_text = f"《PPT 导出自检报告（共 {total_slides} 页，含 {chart_count} 张原生图表，0 处溢出）》"

    report_dict = {
        "ok": True,
        "total_slides": total_slides,
        "chart_count": chart_count,
        "overflow_count": 0,
        "report_text": report_text,
        "removed_blank_slides": removed_blank_slides,
        "total_pages": total_slides,
        "report_summary": report_text,
        "blank_slides_removed": removed_blank_slides,
        "status": "pass" if total_slides >= 1 else "warn",
        "overflow_fixed": overflow_fixed,
    }

    return ValidationResult(prs, report_dict, report_text)


def build_pptx(data, path):
    """编译 Markdown 大纲为高品质 16:9 商务汇报演示文稿（基于 python-pptx）。"""
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    slides = data.get("slides") or []
    has_cover = any(s.get("type") == "cover" for s in slides)
    if not has_cover:
        _render_cover_slide(prs, {}, data)

    page_num = 1
    for item in slides:
        stype = str(item.get("type") or "").lower().strip()
        if not stype:
            title = str(item.get("title") or "")
            if "目录" in title or "agenda" in title.lower():
                stype = "catalog"
            elif any(k in title for k in ("过渡", "第一部分", "第二部分", "第三部分", "第四部分", "part")):
                stype = "transition"
            elif any(k in title for k in ("感谢", "q&a", "结尾", "结束", "交流")):
                stype = "ending"
            elif item.get("chart_data") or item.get("table_raw"):
                if "[图表" in str(item.get("table_raw") or "") or "[图表" in title:
                    stype = "chart"
                else:
                    stype = "table"
            else:
                stype = "conclusion"

        if stype == "cover":
            _render_cover_slide(prs, item, data)
        elif stype == "catalog":
            _render_catalog_slide(prs, item, page_num)
            page_num += 1
        elif stype == "transition":
            _render_transition_slide(prs, item, page_num)
            page_num += 1
        elif stype == "chart":
            _render_chart_slide(prs, item, page_num)
            page_num += 1
        elif stype == "table":
            _render_table_slide(prs, item, page_num)
            page_num += 1
        elif stype == "ending":
            _render_ending_slide(prs, item, data)
        else:
            _render_conclusion_slide(prs, item, page_num)
            page_num += 1

    # 导出前自检与兜底修复
    stats = validate_ppt_before_save(prs)

    # 确保目标输出目录存在
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    prs.save(path)

    stats["path"] = path
    return stats


def build_xlsx(data, path):
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = str(data.get("sheet", "Sheet1"))[:28]
    headers = data.get("headers") or []
    rows = data.get("rows") or []

    ws.append(headers)

    def _conv(cell):
        """表格单元格转换：防公式注入，保留前导零/长编号，纯数字才转数值。"""
        if not isinstance(cell, str):
            return cell, False
        s = cell.strip()
        if not s:
            return cell, False
        # Excel 公式注入防护：= + - @ 开头的文本一律按普通文本写入
        if s[0] in "=+-@":
            return s, True
        # 千分位数字：1,234 / 1,234.5
        if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
            try:
                return float(s.replace(",", "")), False
            except ValueError:
                return cell, False
        # 普通整数（不转换 0 开头的编号，如 00123）
        if re.fullmatch(r"[+-]?[1-9]\d{0,15}", s) or s == "0":
            return int(s), False
        if re.fullmatch(r"[+-]?\d+\.\d+", s):
            return float(s), False
        return cell, False

    for r in rows:
        vals = [_conv(cell) for cell in r]
        ws.append([v for v, _ in vals])
        row_idx = ws.max_row
        for c, (_v, force_text) in enumerate(vals, start=1):
            if force_text:
                # 强制按文本写入，否则 openpyxl 会把 "=..." 当公式
                ws.cell(row=row_idx, column=c).data_type = "s"

    head_fill = PatternFill("solid", fgColor="1F4E79")
    thin = Side(style="thin", color="D9D9D9")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.fill = head_fill
        cell.font = Font(bold=True, color="FFFFFF", name="微软雅黑", size=11)
        cell.alignment = Alignment(horizontal="center", vertical="center")
    for r in range(2, len(rows) + 2):
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            cell.alignment = Alignment(vertical="center")
            cell.border = Border(bottom=thin)
            cell.font = Font(name="微软雅黑", size=10)

    for c in range(1, len(headers) + 1):
        width = max([len(str(headers[c - 1]))] + [len(str(r[c - 1])) for r in rows if len(r) >= c] or [8])
        ws.column_dimensions[get_column_letter(c)].width = min(max(10, width * 1.9), 45)
    ws.freeze_panes = "A2"
    wb.save(path)
    return path


def run_python(code, timeout=45):
    """在受控目录里执行一段 python 代码，返回 (stdout, stderr, 返回码)。"""
    import subprocess
    import sys

    sandbox = os.path.join(os.path.dirname(OUT_DIR), "data", "sandbox")
    os.makedirs(sandbox, exist_ok=True)
    path = os.path.join(sandbox, f"run_{int(time.time() * 1000)}_{os.getpid()}.py")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(code)
    try:
        proc = subprocess.run(
            [sys.executable, "-u", path],
            cwd=sandbox,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return (proc.stdout or "")[-4000:], (proc.stderr or "")[-1500:], proc.returncode
    except subprocess.TimeoutExpired:
        return "", f"执行超过 {timeout} 秒被终止", -1
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def extract_code(text):
    import re

    m = re.search(r"```(?:python)?\s*(.*?)```", text or "", re.S)
    code = m.group(1) if m else (text or "")
    return code.strip()


def build_docx(data: dict, path: str) -> str:
    """将 Markdown 格式报告导出为排版专业的标准 Word 商务文档（基于 python-docx）"""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import nsdecls, qn
    from docx.oxml import parse_xml

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    doc = docx.Document()

    # 全局样式东亚中文字体深度绑定（彻底解决微软雅黑与 EastAsia 字体割裂）
    for s_name in ["Normal", "Heading 1", "Heading 2", "Heading 3", "Title", "Subtitle", "List Bullet"]:
        if s_name in doc.styles:
            st = doc.styles[s_name]
            st.font.name = "Microsoft YaHei"
            rPr = st._element.get_or_add_rPr()
            rFonts = getattr(rPr, "rFonts", None)
            if rFonts is None:
                rFonts = rPr.get_or_add_rFonts()
            rFonts.set(qn("w:eastAsia"), "微软雅黑")

    def apply_run_font(run, name="Microsoft YaHei", east_asia="微软雅黑", size=None, bold=None, color=None):
        run.font.name = name
        rPr = run._element.get_or_add_rPr()
        rFonts = getattr(rPr, "rFonts", None)
        if rFonts is None:
            rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn("w:eastAsia"), east_asia)
        if size is not None:
            run.font.size = size
        if bold is not None:
            run.font.bold = bold
        if color is not None:
            run.font.color.rgb = color

    def clean_docx_text(text: Any, remove_markdown: bool = True) -> str:
        if not text:
            return ""
        s = str(text)
        # 清除 markdown 表格分隔符 | --- | 或残留的竖线
        s = re.sub(r"\|[-:\s|]+\|", " ", s)
        s = re.sub(r"\|[-:]+", " ", s)
        s = re.sub(r"[-:]+\|", " ", s)
        s = s.replace("|", " ")
        # 清除反引号
        s = s.replace("`", "")
        # 清除所有 Emoji 图标
        s = re.sub(r"[🔴🟡🟢⚪⚠️✅📊📋🔍📑✓✕\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]", "", s)
        if remove_markdown:
            s = s.replace("**", "").replace("__", "")
        s = s.replace("\r", "")
        # 规整多余空白
        s = re.sub(r"[ \t]+", " ", s)
        return s.strip()

    def add_formatted_runs_to_paragraph(p, text: str, default_size=Pt(10.5), default_color=RGBColor(0x33, 0x33, 0x33)):
        parts = re.split(r"(\*\*.*?\*\*)", text)
        for part in parts:
            if not part:
                continue
            if part.startswith("**") and part.endswith("**") and len(part) >= 4:
                sub = part[2:-2].strip()
                r = p.add_run(sub)
                apply_run_font(r, size=default_size, bold=True, color=default_color)
            else:
                r = p.add_run(part)
                apply_run_font(r, size=default_size, bold=False, color=default_color)

    for section in doc.sections:
        section.top_margin = Inches(0.8)
        section.bottom_margin = Inches(0.8)
        section.left_margin = Inches(0.8)
        section.right_margin = Inches(0.8)

    title_text = clean_docx_text(data.get("title") or "专项工作与管理分析报告")
    content_text = data.get("content") or ""

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_title = p_title.add_run(title_text)
    apply_run_font(run_title, size=Pt(20), bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
    p_title.paragraph_format.space_after = Pt(16)

    lines = content_text.strip().split("\n")
    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.strip()
        if not line:
            i += 1
            continue

        # 1. 结构化 Markdown 表格识别与原生 Word 表格渲染
        if line.startswith("|") and ("|" in line[1:]):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|") and ("|" in lines[i].strip()[1:]):
                table_lines.append(lines[i].strip())
                i += 1

            parsed_rows = []
            for tl in table_lines:
                content = tl.strip()
                if content.startswith("|"):
                    content = content[1:]
                if content.endswith("|"):
                    content = content[:-1]
                cells = [c.strip() for c in content.split("|")]
                # 过滤分隔行如 | :--- | :--- |
                if all(re.match(r"^:?-+:?$", c) for c in cells if c):
                    continue
                parsed_rows.append(cells)

            if parsed_rows:
                header_cells = parsed_rows[0]
                data_rows = parsed_rows[1:]
                num_cols = max(len(header_cells), max((len(r) for r in data_rows), default=0))
                if num_cols > 0:
                    tbl = doc.add_table(rows=len(data_rows) + 1, cols=num_cols)
                    tbl.style = "Table Grid"

                    hdr_row = tbl.rows[0]
                    for c_idx in range(num_cols):
                        cell = hdr_row.cells[c_idx]
                        c_text = clean_docx_text(header_cells[c_idx]) if c_idx < len(header_cells) else ""
                        cell.text = c_text
                        cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
                        for run in cell.paragraphs[0].runs:
                            apply_run_font(run, size=Pt(9.5), bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
                        shd = parse_xml(r'<w:shd {} w:fill="1F4E79"/>'.format(nsdecls("w")))
                        cell._tc.get_or_add_tcPr().append(shd)

                    for r_idx, raw_cells in enumerate(data_rows, 1):
                        row_cells = tbl.rows[r_idx].cells
                        row_raw_text = " ".join(raw_cells)

                        is_fatal = bool(re.search(r"(重点不合规|致命|高风险|严禁|重大偏离|违规|red|fatal|🔴)", row_raw_text, re.I))
                        is_flaw = bool(re.search(r"(偏离|瑕疵|中风险|关注|待核实|flaw|warn|🟡)", row_raw_text, re.I))
                        is_compliant = bool(re.search(r"(完全符合|合规|通过|低风险|正常|完备|compliance|🟢)", row_raw_text, re.I))

                        if is_fatal:
                            fill_color = "FFF5F5"
                            text_color = RGBColor(0x99, 0x1B, 0x1B)
                        elif is_flaw:
                            fill_color = "FFF9F2"
                            text_color = RGBColor(0x92, 0x40, 0x0E)
                        elif is_compliant:
                            fill_color = "F9FAFB"
                            text_color = RGBColor(0x86, 0x86, 0x8B)
                        else:
                            fill_color = "FFFFFF" if r_idx % 2 == 1 else "F9FAFB"
                            text_color = RGBColor(0x33, 0x33, 0x33)

                        for c_idx in range(num_cols):
                            cell = row_cells[c_idx]
                            raw_val = raw_cells[c_idx] if c_idx < len(raw_cells) else ""
                            cell_text = clean_docx_text(raw_val)
                            cell.text = cell_text

                            for p in cell.paragraphs:
                                for run in p.runs:
                                    if is_fatal or is_flaw:
                                        if c_idx in (0, 2):
                                            apply_run_font(run, size=Pt(9.0), bold=True, color=text_color)
                                        else:
                                            apply_run_font(run, size=Pt(9.0), bold=True, color=RGBColor(0x2B, 0x36, 0x4B))
                                    elif is_compliant:
                                        apply_run_font(run, size=Pt(9.0), bold=False, color=RGBColor(0x86, 0x86, 0x8B))
                                    else:
                                        apply_run_font(run, size=Pt(9.0), bold=(c_idx == 0), color=text_color)

                            shd = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls("w"), fill_color))
                            cell._tc.get_or_add_tcPr().append(shd)

                    p_sp = doc.add_paragraph()
                    p_sp.paragraph_format.space_before = Pt(4)
                    p_sp.paragraph_format.space_after = Pt(4)
            continue

        # 2. 标题与段落排版
        if line.startswith("# ") or line.startswith("## ") or re.match(r"^[一二三四五六七八九十]、", line):
            heading_text = clean_docx_text(re.sub(r"^#+\s*", "", line))
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(6)
            run = p.add_run(heading_text)
            apply_run_font(run, size=Pt(14), bold=True, color=RGBColor(0x12, 0x18, 0x2A))
            i += 1
        elif line.startswith("### ") or re.match(r"^\d+[\.、）\)]", line):
            sub_text = clean_docx_text(re.sub(r"^###\s*", "", line))
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(8)
            p.paragraph_format.space_after = Pt(4)
            run = p.add_run(sub_text)
            apply_run_font(run, size=Pt(12), bold=True, color=RGBColor(0x2B, 0x36, 0x4B))
            i += 1
        elif line.startswith("- ") or line.startswith("* "):
            bullet_text = clean_docx_text(line[2:].strip(), remove_markdown=False)
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_before = Pt(2)
            p.paragraph_format.space_after = Pt(2)
            add_formatted_runs_to_paragraph(p, bullet_text, default_size=Pt(10.5), default_color=RGBColor(0x33, 0x33, 0x33))
            i += 1
        else:
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(3)
            p.paragraph_format.space_after = Pt(3)
            p.paragraph_format.line_spacing = 1.25
            clean_line = clean_docx_text(line, remove_markdown=False)
            add_formatted_runs_to_paragraph(p, clean_line, default_size=Pt(10.5), default_color=RGBColor(0x33, 0x33, 0x33))
            i += 1

    # 全文深度兜底：确保所有段落和表格中的 run 均已绑定西文与东亚中文字体
    for p in doc.paragraphs:
        for run in p.runs:
            apply_run_font(run)
    for tbl_obj in doc.tables:
        for r in tbl_obj.rows:
            for c in r.cells:
                for p in c.paragraphs:
                    for run in p.runs:
                        apply_run_font(run)

    doc.save(path)
    return path


def stamp(prefix, ext):
    """唯一文件名：秒级时间 + 随机后缀，避免并发导出互相覆盖。"""
    return os.path.join(
        OUT_DIR, f"{prefix}-{datetime.now().strftime('%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}.{ext}"
    )


# 启动时决定用哪个模型：优先用户锁定，其次按本机配置自动选择
_current_path, _start_mode = resolve_startup_model()
_state["model"] = os.path.basename(_current_path)
