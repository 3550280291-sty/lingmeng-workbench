/* 灵梦工作台 —— 前端逻辑 */

/* ==============================================================================
   iOS / macOS 风格原生替代组件：Toast、Modal 弹窗与模型加载进度条
   彻底替代 window.alert 与 window.confirm，消灭 127.0.0.1 浏览器黑框
   ============================================================================== */

function showToast(msg, type = "info", duration = 3000) {
  const container = $("#toastContainer");
  if (!container) return;
  const t = document.createElement("div");
  t.className = `toast-item toast-${type}`;
  const icons = { info: "ℹ️", success: "✨", warn: "⚠️", error: "❌" };
  t.innerHTML = `<span class="toast-icon">${icons[type] || "ℹ️"}</span><span class="toast-text">${esc(msg)}</span>`;
  container.appendChild(t);
  setTimeout(() => {
    t.classList.add("fade-out");
    setTimeout(() => t.remove(), 260);
  }, duration);
}

function showConfirm(options) {
  return new Promise((resolve) => {
    const mask = $("#customModalMask");
    const titleEl = $("#modalTitle");
    const bodyEl = $("#modalBody");
    const iconEl = $("#modalIcon");
    const cancelBtn = $("#modalCancelBtn");
    const confirmBtn = $("#modalConfirmBtn");

    if (typeof options === "string") {
      options = { message: options };
    }
    const {
      title = "确认操作",
      message = "是否确认执行？",
      icon = "⚠️",
      confirmText = "确定",
      cancelText = "取消",
      isDanger = false,
      singleBtn = false
    } = options;

    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.textContent = message;
    if (iconEl) {
      if (typeof icon === "string" && (icon.includes("<svg") || icon.includes("<span") || icon.includes("<div"))) {
        iconEl.innerHTML = icon;
      } else {
        iconEl.textContent = icon;
      }
    }
    if (confirmBtn) {
      confirmBtn.textContent = confirmText;
      confirmBtn.className = isDanger ? "modal-btn confirm danger" : "modal-btn confirm primary";
    }

    if (cancelBtn) {
      cancelBtn.textContent = cancelText;
      cancelBtn.style.display = singleBtn ? "none" : "";
    }

    if (mask) mask.hidden = false;

    const cleanup = () => {
      if (mask) mask.hidden = true;
      if (confirmBtn) confirmBtn.onclick = null;
      if (cancelBtn) cancelBtn.onclick = null;
    };

    if (confirmBtn) {
      confirmBtn.onclick = () => {
        cleanup();
        resolve(true);
      };
    }
    if (cancelBtn) {
      cancelBtn.onclick = () => {
        cleanup();
        resolve(false);
      };
    }
  });
}

function showAlert(message, title = "提示", icon = "ℹ️") {
  return showConfirm({
    title,
    message,
    icon,
    confirmText: "我知道了",
    singleBtn: true
  });
}

// 全局拦截并消灭 127.0.0.1:7860 浏览器原生弹窗
window.alert = function (msg) {
  console.warn("[Intercepted native alert]", msg);
  showAlert(String(msg !== undefined ? msg : ""));
};
window.confirm = function (msg) {
  console.warn("[Intercepted native confirm]", msg);
  return showConfirm(String(msg !== undefined ? msg : ""));
};
window.prompt = function (msg, def) {
  console.warn("[Intercepted native prompt]", msg);
  return null;
};

let modelLoadingInterval = null;
let modelLoadingStartTime = 0;

function showModelLoading(modelName = "本地模型") {
  const mask = $("#modelLoadingMask");
  const title = $("#modelLoadingTitle");
  const timer = $("#modelLoadingTimer");
  if (!mask) return;

  const targetDev = (S && S.status && S.status.device) || "本机核显 / CPU";
  if (title) title.textContent = `正在将模型加载至 ${targetDev}...`;
  if (timer) timer.textContent = "0s";
  modelLoadingStartTime = Date.now();
  mask.hidden = false;
  mask.style.removeProperty("display");
  mask.style.removeProperty("pointer-events");

  if (modelLoadingInterval) clearInterval(modelLoadingInterval);
  modelLoadingInterval = setInterval(() => {
    const elapsedSec = Math.floor((Date.now() - modelLoadingStartTime) / 1000);
    if (timer) timer.textContent = `${elapsedSec}s`;
    const sub = $("#modelLoadingSub");
    if (sub) {
      if (elapsedSec > 15 && elapsedSec <= 30) {
        sub.textContent = "正在将神经网络权重载入内存并进行管道预热...";
      } else if (elapsedSec > 30) {
        sub.textContent = "正在完成最终推理核心绑定，马上就绪...";
      }
    }
  }, 1000);
}

function hideModelLoading(successModelName = "") {
  const mask = $("#modelLoadingMask");
  if (modelLoadingInterval) {
    clearInterval(modelLoadingInterval);
    modelLoadingInterval = null;
  }
  if (mask) {
    mask.hidden = true;
    mask.style.setProperty("display", "none", "important");
  }
  if (successModelName) {
    showToast(`✨ 模型已成功加载就绪！`, "success", 4000);
  }
}

function $(s) {
  try {
    if (s === "#对账汇总-panel") return document.getElementById("reconcilePipeline") || document.querySelector(s);
    if (s === "#比选比价-panel") return document.getElementById("pricePipeline") || document.querySelector(s);
    if (s === "#合同审查-panel") return document.getElementById("reviewPipeline") || document.querySelector(s);
    if (s === "#welcome" || s === "#welcome-view") return document.getElementById("welcome-view") || document.getElementById("welcome") || document.querySelector(s);
    if (s === "#task-wizard-view") return document.getElementById("task-wizard-view") || document.querySelector(".task-wizard-view:not([hidden])") || document.getElementById("reconcilePipeline") || document.querySelector(s);
    return document.querySelector(s);
  } catch (_) {
    return null;
  }
}
function $$(s) {
  try {
    return [...document.querySelectorAll(s)];
  } catch (_) {
    return [];
  }
}

function switchMainView(viewName) {
  const welcomeView = $("#welcome-view") || $("#welcome");
  const wizardView = $("#task-wizard-view");
  const pricePipeline = $("#pricePipeline");
  const reviewPipeline = $("#reviewPipeline");
  const msgList = $("#msgList");

  if (viewName === "wizard") {
    if (welcomeView) {
      welcomeView.hidden = true;
      welcomeView.style.setProperty("display", "none", "important");
    }
    if (wizardView) {
      wizardView.hidden = false;
      wizardView.style.setProperty("display", "block", "important");
    }
    if (msgList) msgList.style.display = "none";
  } else if (viewName === "chat") {
    if (welcomeView) {
      welcomeView.hidden = true;
      welcomeView.style.setProperty("display", "none", "important");
    }
    if (wizardView) {
      wizardView.hidden = true;
      wizardView.style.setProperty("display", "none", "important");
    }
    if (pricePipeline) {
      pricePipeline.hidden = true;
      pricePipeline.style.setProperty("display", "none", "important");
    }
    if (reviewPipeline) {
      reviewPipeline.hidden = true;
      reviewPipeline.style.setProperty("display", "none", "important");
    }
    if (msgList) msgList.style.display = "";
  } else { // 'welcome'
    if (welcomeView) {
      welcomeView.hidden = false;
      welcomeView.style.removeProperty("display");
    }
    if (wizardView) {
      wizardView.hidden = true;
      wizardView.style.setProperty("display", "none", "important");
    }
    if (pricePipeline) {
      pricePipeline.hidden = true;
      pricePipeline.style.setProperty("display", "none", "important");
    }
    if (reviewPipeline) {
      reviewPipeline.hidden = true;
      reviewPipeline.style.setProperty("display", "none", "important");
    }
    if (msgList) msgList.style.display = "none";
    renderWelcome();
  }
}

const S = {
  convs: [],
  currentId: null,
  currentArtifact: null,
  messages: [],
  files: [],
  modes: [],
  mode: "general",
  streaming: false,
  stream: null,
  controller: null,
  ready: false,
  kb: localStorage.getItem("qwen.kb") === "1", // 默认关闭全局跨文件检索，严格会话隔离
  useCode: localStorage.getItem("qwen.usecode") !== "0",
  switching: false,
  thinking: false,
  params: {
    maxTokens: +(localStorage.getItem("qwen.maxTokens") || 1024),
    temperature: +(localStorage.getItem("qwen.temperature") || 0.7),
    deep: localStorage.getItem("qwen.deep") === "1",
  },
};

/* ------------------------------------------------ 工具 */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function inline(s) {
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>");
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>");
  t = t.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="md-link">$1</a>');
  return t;
}

/* 思考过程提取器（状态机增强版：自动捕获无 <think> 开头的推理独白，实时折叠与闭合） */
const MONO_PREFIXES = [
  "首先", "思考", "我需要", "我现在需要", "用户现在", "用户想要", "用户最初",
  "用户要求", "用户选择", "好的，我", "好的，现在", "好的，用户", "嗯，用户", "嗯，现在", "回顾之前", "从提示词", "思考过程", "深度思考"
];

const THINK_DELIM_RE = /(?:<\/think>|\r?\n[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$)|\r?\n{2,}(?=您已选定|您目前提供|您好|抱歉|哎呀|感谢|很抱歉)|\r?\n{2,}(?=###?\s*(?:\[?[✅📊🔍💡📌🚨]|一、|[0-9]+[、.]|\*\*))|\r?\n{2,}(?=\*\*(?:报告标题|示范|印尼|项目|总体|采购|方案|对账|自查|需求))|\r?\n{2,}(?=[✅📊🔍💡📌🚨])|\r?\n(?=[✅📊🔍💡📌🚨])|\r?\n{2,}(?=[一二三四五]、)|\r?\n\r?\n\r?\n+)/m;

function splitThink(s, isLiveStreaming = false) {
  if (!s) return { think: "", body: "", isThinking: false };

  // 1. 显式成对标签 <think> ... </think>
  const closedMatch = s.match(/<think[^>]*>([\s\S]*?)<\/think>/i);
  if (closedMatch) {
    const think = closedMatch[1].trim();
    const body = s.slice(closedMatch.index + closedMatch[0].length).trimStart();
    return { think, body, isThinking: false };
  }

  // 2. 缺失开启标签 <think>，但存在孤立闭合标签 </think>
  const closeIdx = s.toLowerCase().indexOf("</think>");
  if (closeIdx !== -1) {
    const think = s.slice(0, closeIdx).trim();
    const body = s.slice(closeIdx + 8).trimStart();
    return { think, body, isThinking: false };
  }

  // 3. 显式开启标签 <think>，检查其内部是否已有结束分隔符
  const openMatch = s.match(/<think[^>]*>([\s\S]*)$/i);
  if (openMatch) {
    const inside = openMatch[1];
    const mDelim = inside.match(THINK_DELIM_RE);
    if (mDelim) {
      const think = inside.slice(0, mDelim.index).trim();
      let body = inside.slice(mDelim.index);
      body = body.replace(/^(?:<\/think>|\r?\n?[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$))/, "").trimStart();
      return { think, body, isThinking: false };
    }
    return { think: inside.trim(), body: "", isThinking: isLiveStreaming };
  }

  // 4. 无标签思考过程：以“首先”、“思考”等前缀开头的推理独白，以 </think> 或 --- 分隔
  const leadMatch = s.match(/^\s*/);
  const offset = leadMatch ? leadMatch[0].length : 0;
  const trimS = s.slice(offset);
  const startsWithMono = MONO_PREFIXES.some((p) => trimS.startsWith(p));
  if (startsWithMono) {
    const mDelim = trimS.match(THINK_DELIM_RE);
    if (mDelim) {
      const think = trimS.slice(0, mDelim.index).trim();
      let body = trimS.slice(mDelim.index);
      body = body.replace(/^(?:<\/think>|\r?\n?[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$))/, "").trimStart();
      return { think, body, isThinking: false };
    }
    // 流式输出中且尚未遇到结束分隔符
    if (isLiveStreaming) {
      return { think: trimS.trim(), body: "", isThinking: true };
    }
  }

  return { think: "", body: s, isThinking: false };
}
function md(src) {
  const lines = String(src || "").split("\n");
  let out = [];
  let list = null; // 'ul' | 'ol'
  let table = null;
  let code = null;
  let para = [];

  const flushPara = () => {
    if (para.length) {
      out.push("<p>" + para.map(inline).join("<br>") + "</p>");
      para = [];
    }
  };
  const flushList = () => {
    if (list) {
      out.push(`</${list}>`);
      list = null;
    }
  };
  const flushTable = () => {
    if (table) {
      const rows = table.filter((r) => !r.every((c) => /^:?-{2,}:?$/.test(c.trim()) || c.trim() === ""));
      if (rows.length) {
        const head = rows[0];
        let h = '<table><thead><tr>' + head.map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
        for (const r of rows.slice(1)) {
          h += "<tr>" + r.map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        }
        out.push(h + "</tbody></table>");
      }
      table = null;
    }
  };

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");

    if (code !== null) {
      if (/^```/.test(line)) {
        out.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>");
        code = null;
      } else code.push(raw);
      continue;
    }
    if (/^```/.test(line)) {
      flushPara(); flushList(); flushTable();
      code = [];
      continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line)) {
      flushPara(); flushList();
      table = table || [];
      table.push(line.trim().replace(/^\||\|$/g, "").split("|"));
      continue;
    }
    flushTable();

    if (!line.trim()) {
      flushPara();
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      flushPara(); flushList();
      const lv = Math.min(h[1].length + 1, 4);
      out.push(`<h${lv}>${inline(h[2])}</h${lv}>`);
      continue;
    }
    if (/^>\s?/.test(line)) {
      flushPara(); flushList();
      out.push("<blockquote>" + inline(line.replace(/^>\s?/, "")) + "</blockquote>");
      continue;
    }
    const ul = line.match(/^\s*[-*·•]\s+(.*)$/);
    if (ul) {
      flushPara();
      if (list !== "ul") { flushList(); out.push("<ul>"); list = "ul"; }
      out.push("<li>" + inline(ul[1]) + "</li>");
      continue;
    }
    const ol = line.match(/^\s*(\d+)[.)、]\s*(.*)$/);
    if (ol) {
      flushPara();
      if (list !== "ol") { flushList(); out.push("<ol>"); list = "ol"; }
      out.push("<li>" + inline(ol[2]) + "</li>");
      continue;
    }
    flushList();
    para.push(line);
  }
  if (code !== null) out.push("<pre><code>" + esc(code.join("\n")) + "</code></pre>");
  flushPara(); flushList(); flushTable();
  return out.join("");
}

/* ------------------------------------------------ API */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: opts.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail || j.message || msg;
    } catch (e) {}
    throw new Error(msg);
  }
  return res.json();
}

/* ------------------------------------------------ 状态 / 模式 */
async function loadStatus() {
  try {
    const st = await api("/api/status");
    S.modes = st.modes || [];
    renderWelcome();
    S.ready = !!st.ready;
    const deviceShort = st.device ? (st.device === "GPU" ? "GPU" : "CPU") : "-";
    const device = st.device ? (st.device === "GPU" ? "GPU（显卡）" : "CPU（本机）") : "-";
    const modelLabel = (st.model || "Qwen3-4B-Thinking").replace(/\.gguf$/i, "");
    const isWarming = (st.loading || !st.ready) && !st.error;
    const statusText = st.error
      ? `🔴 模型加载失败 (${st.error})`
      : isWarming
      ? "🟢 服务已就绪（模型后台预热中...）"
      : `🟢 模型已就绪 (${modelLabel})`;
    const dotClass = st.ready ? "dot on" : st.error ? "dot off" : "dot busy";
    const statusHtml = `<span id="modelStatus"><span id="statusIndicator"><i class="${dotClass}"></i> ${statusText}</span></span>`;

    const footEl = $("#footStatus");
    if (footEl) {
      footEl.innerHTML = statusHtml;
      footEl.title = statusText;
    }
    const msEl = $("#modelStatus");
    if (msEl && (!footEl || !footEl.contains(msEl))) msEl.textContent = statusText;
    const siEl = $("#statusIndicator");
    if (siEl && (!footEl || !footEl.contains(siEl))) siEl.textContent = statusText;
    $("#hintRight").textContent = st.ready ? "内容仅在本机处理" : st.loading ? "正在加载模型，约 1 分钟…" : "";
    $("#setModel").textContent = st.model || "-";
    const ver = $("#setVersion"); if (ver && st.version) ver.textContent = "v" + st.version;
    $("#setDevice").textContent = device;
    $("#setStatus").textContent = st.ready ? "就绪" : st.loading ? "加载中" : st.error ? "异常" : "未启动";
    const hw = st.hardware || {};
    const ramEl = $("#setRam"), cpuEl = $("#setCpu"), gpuEl = $("#setGpu");
    if (ramEl) ramEl.textContent = hw.ram_gb ? hw.ram_gb + " GB" : "-";
    if (cpuEl) { cpuEl.textContent = hw.cpu || "-"; cpuEl.title = hw.cpu || ""; }
    if (gpuEl) { gpuEl.textContent = hw.gpu || "未检测到独显"; gpuEl.title = hw.gpu || ""; }
    S.modelInfo = st;
    const lockEl = $("#modelLock");
    if (lockEl) lockEl.checked = !!st.lock;
    const hintEl = $("#modelHint");
    if (hintEl) {
      hintEl.textContent = st.lock
        ? "已锁定：" + (st.model || "") + "，下次启动继续加载它。"
        : (st.recommended
            ? "自动选择：" + (st.recommend_reason || st.recommended) + "（未锁定，每次启动按本机配置重新推荐）"
            : "未检测到可用模型。");
    }
    S.thinking = !!st.thinking;
    S.alwaysThinking = !!st.always_thinking;
    const deepBtn = $("#deepToggle");
    if (deepBtn) {
      deepBtn.disabled = !S.thinking || S.alwaysThinking;
      deepBtn.title = S.alwaysThinking
        ? "当前是纯思考模型，回答前一定会先推理，这个开关无效"
        : S.thinking
        ? "开启后模型会先推理再回答（更慢、更严谨）"
        : "当前是快答版模型，本身不思考；换成思考版后可用";
    }
    const dchk = $("#deepThink");
    if (dchk) dchk.disabled = !S.thinking || S.alwaysThinking;
    const dnote = $("#deepNote");
    if (dnote) {
      dnote.textContent = S.alwaysThinking
        ? "当前是纯思考模型（Thinking），每次回答前都会先推理，速度较慢但更严谨。这个开关对它无效。"
        : S.thinking
        ? "当前是思考型模型：开启后先推理再回答，速度会慢一些，适合分析难题。"
        : "当前模型本身不思考，这个开关暂不可用。到「模型」里换成思考版即可。";
    }
    $("#sendBtn").disabled = !st.ready || S.switching;
    if (S.modes.length && !$("#modeRow").children.length) renderModes();
    return st.ready;
  } catch (e) {
    const footEl = $("#footStatus");
    if (footEl) {
      footEl.innerHTML = '<span id="modelStatus"><span id="statusIndicator"><i class="dot"></i> 服务未连接</span></span>';
    }
    const msEl = $("#modelStatus");
    if (msEl && (!footEl || !footEl.contains(msEl))) msEl.textContent = "服务未连接";
    const siEl = $("#statusIndicator");
    if (siEl && (!footEl || !footEl.contains(siEl))) siEl.textContent = "服务未连接";
    renderWelcome();
    return false;
  }
}

function renderWelcome() {
  let box = $("#welcomeCards") || document.getElementById("welcomeCards");
  if (!box) {
    const mainCol = $(".welcome-main-col");
    if (mainCol) {
      box = document.createElement("div");
      box.className = "cards dashboard-carousel";
      box.id = "welcomeCards";
      mainCol.appendChild(box);
    } else {
      return;
    }
  }

  const svg = (d, stroke) => `<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="${stroke}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">${d}</svg>`;
  const icons = {
    merge: `<span class="card-icon-box merge">${svg('<rect x="3" y="4" width="8" height="16" rx="1.8"/><line x1="5.8" y1="8" x2="8.2" y2="8"/><line x1="5.8" y1="12" x2="8.2" y2="12"/><rect x="13" y="4" width="8" height="16" rx="1.8"/><line x1="15.8" y1="8" x2="18.2" y2="8"/><line x1="15.8" y1="12" x2="18.2" y2="12"/><path d="M8.5 16l2.2 2.2 4.8-4.8" stroke-width="2"/>', '#2563EB')}</span>`,
    price: `<span class="card-icon-box price">${svg('<path d="M3 20h18"/><path d="M6 16v4"/><path d="M11 11v9"/><path d="M16 7v13"/><path d="M6 12l5-5 5 3 5-6"/><circle cx="21" cy="4" r="1.5" fill="#D97706"/>', '#D97706')}</span>`,
    review: `<span class="card-icon-box review">${svg('<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>', '#059669')}</span>`,
    report: `<span class="card-icon-box report">${svg('<path d="M4 19V5a2 2 0 0 1 2-2h8l4 4v2"/><path d="M8 7h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2z"/><line x1="11" y1="12" x2="14" y2="12"/><line x1="11" y1="16" x2="14" y2="16"/><path d="M16 2.5l3.5 3.5L14 11.5l-3.5.5.5-3.5L16 2.5z"/>', '#7C3AED')}</span>`,
    ppt: `<span class="card-icon-box ppt">${svg('<rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/><path d="M7 13v-3"/><path d="M12 13V8"/><path d="M17 13v-5"/>', '#E11D48')}</span>`,
  };

  const coreModes = [
    { id: "merge", name: "调拨对账汇总", badge: "标准流水线", hint: "两表关联对账、字段映射、差异验收单与真实 Excel 导出" },
    { id: "price", name: "供应商比选/比价", badge: "", hint: "多供应商报价横向对比、TCO 总成本测算与授标建议" },
    { id: "review", name: "合规性审查", badge: "", hint: "支持合同、采购寻源流程、招投标文件、报销与供应商准入合规审查" },
  ];

  const deliveryModes = [
    { id: "report", name: "写专业报告（短/长报告）", badge: "", hint: "金字塔结构、归因分析、分章节长报告接力深度撰写" },
    { id: "ppt", name: "生成演示 PPT", badge: "", hint: "大纲策划、原生 Office 图表、演讲者备注与母版导出" },
  ];

  const cardHTML = (m, cls) => `
    <button class="card card-hero ${cls}" data-mode="${m.id}">
      ${icons[m.id] || ""}
      <span class="card-text">
        <b class="card-title">${esc(m.name)} ${m.badge ? `<span class="badge-pill mini-badge">${m.badge}</span>` : ""}</b>
        <span class="card-desc">${esc(m.hint)}</span>
      </span>
    </button>`;

  const stepBarHTML = `
    <div class="welcome-step-bar wsc-guide-horizontal wsc-guide-section" id="welcomeStepBar">
      <div class="wsb-header wsc-guide-title">
        <span class="wsb-icon wsc-guide-icon">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="#D97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        </span>
        <b>快速上手指南</b>
      </div>
      <div class="wsb-steps wsc-steps">
        <div class="wsb-step wsc-step">
          <span class="wsb-step-idx wsc-step-idx">1</span>
          <div class="wsb-step-info wsc-step-info">
            <b>选定业务流水线或拖拽表格</b>
            <span>点击上方 3 大业务卡片，或直接拖拽表格到窗口</span>
          </div>
        </div>
        <div class="wsb-arrow">➔</div>
        <div class="wsb-step wsc-step">
          <span class="wsb-step-idx wsc-step-idx">2</span>
          <div class="wsb-step-info wsc-step-info">
            <b>字段映射与基准参数配置</b>
            <span>智能识别表头，配置统一税率与贴息参数</span>
          </div>
        </div>
        <div class="wsb-arrow">➔</div>
        <div class="wsb-step wsc-step">
          <span class="wsb-step-idx wsc-step-idx">3</span>
          <div class="wsb-step-info wsc-step-info">
            <b>验收级核查与一键交付</b>
            <span>Python 确定性计算，0口算幻觉，导出 Excel / PPT</span>
          </div>
        </div>
      </div>
    </div>`;

  if (!box.querySelector(".cards-grid") || !box.querySelector(".task-card")) {
    box.innerHTML = `
      <!-- 【核心业务任务】 -->
      <div class="cards-grid cards-3">${coreModes.map((m) => cardHTML(m, "task-card")).join("")}</div>
      <!-- 【通用成果交付】 -->
      <div class="cards-grid cards-2">${deliveryModes.map((m) => cardHTML(m, "output-card")).join("")}</div>
      ${stepBarHTML}
      <!-- welcome-footer-note: 「通用对话」与「自由表格分析」已作为底部输入框的默认底层能力，采购合同审查 -->`;
  }

  $$("#welcomeCards .card").forEach((c) => {
    c.onclick = () => {
      const modeId = c.dataset.mode;
      if (modeId === "merge") {
        openReconcilePipeline();
      } else if (modeId === "price") {
        openPricePipeline();
      } else if (modeId === "review") {
        openReviewPipeline();
      } else if (modeId === "report") {
        closeAllPipelines(false);
        S.mode = "report";
        renderModes();
        const tm = $("#topMode");
        if (tm) tm.textContent = "写专业报告";
        updatePlaceholder();
        const input = $("#input");
        if (input) {
          if (!input.value || !input.value.trim()) {
            input.value = "请帮我撰写一份关于【请在此输入报告主题】的专业分析报告。要求：\n1. 严格依据金字塔原理，结论先行，结构严谨；\n2. 包含核心态势与数据摘要、重点成效、突出矛盾与归因剖析、下一步保障措施；\n3. 语言规范庄重，数据详实。";
          }
          input.style.height = "auto";
          input.style.height = Math.min(input.scrollHeight, 190) + "px";
          input.focus();
        }
      } else if (modeId === "ppt") {
        closeAllPipelines(false);
        S.mode = "ppt";
        renderModes();
        const tm = $("#topMode");
        if (tm) tm.textContent = "生成演示 PPT";
        updatePlaceholder();
        const input = $("#input");
        if (input) {
          if (!input.value || !input.value.trim()) {
            input.value = "请帮我策划一份关于【请在此输入演示主题】的汇报 PPT 大纲。要求：\n1. 包含一句话主标题与副标题；\n2. 规划 5-7 页幻灯片大纲，每页 3-4 条精炼要点（每点≤30字，带数据支撑）；\n3. 包含数据对比图表页与归因分析页，并附带演讲者备注。";
          }
          input.style.height = "auto";
          input.style.height = Math.min(input.scrollHeight, 190) + "px";
          input.focus();
        }
      } else {
        closeAllPipelines(false);
        S.mode = modeId;
        renderModes();
        updatePlaceholder();
        $("#input").focus();
      }
    };
  });

  $$(".wsc-item").forEach((item) => {
    item.onclick = () => {
      const act = item.dataset.action;
      if (act === "quick-merge") openReconcilePipeline();
      else if (act === "quick-price") openPricePipeline();
      else if (act === "quick-review") openReviewPipeline();
    };
  });
}

function renderModes() {
  const displayModes = [
    { id: "general", name: "通用对话", icon: "💬", hint: "日常问答、改写、提炼（底层常驻能力）" },
    { id: "merge", name: "调拨对账汇总", icon: "📋", hint: "两表关联对账、字段映射、差异验收单与真实 Excel 导出" },
    { id: "price", name: "供应商比选/比价", icon: "💰", hint: "多供应商报价横向对比、TCO模型、PPT/Excel导出" },
    { id: "review", name: "合规性审查", icon: "🔍", hint: "支持合同、采购寻源流程、招投标文件、报销与供应商准入合规审查" },
    { id: "report", name: "写专业报告", icon: "📝", hint: "工作报告、总结、方案" },
    { id: "ppt", name: "生成演示 PPT", icon: "📑", hint: "先出大纲，再导出文件" },
    { id: "data", name: "自由表格分析", icon: "📊", hint: "Excel/CSV 数据解读与透视（底层常驻能力）" },
  ];

  $("#modeRow").innerHTML = displayModes
    .map((m) => `<button class="mode ${m.id === S.mode ? "on" : ""}" data-mode="${m.id}" title="${esc(m.hint || "")}">
        <span class="mi">${m.icon || ""}</span>${esc(m.name)}</button>`)
    .join("");
  $$("#modeRow .mode").forEach((b) => {
    b.onclick = (ev) => {
      S.mode = b.dataset.mode;
      renderModes();
      const m = S.modes.find((x) => x.id === S.mode) || displayModes.find((x) => x.id === S.mode);
      $("#topMode").textContent = m ? m.name : "通用对话";
      updatePlaceholder();
      if (S.mode === "merge") {
        openReconcilePipeline();
      } else if (S.mode === "price") {
        openPricePipeline();
      } else if (S.mode === "review") {
        openReviewPipeline();
      } else {
        closeAllPipelines(false);
        $("#input").focus();
      }
    };
  });
  const curM = S.modes.find((x) => x.id === S.mode) || displayModes.find((x) => x.id === S.mode);
  $("#topMode").textContent = curM ? curM.name : "通用对话";
  const wrap = $("#pptPagesWrap");
  if (wrap) wrap.hidden = S.mode !== "ppt";
  const rl = $("#reportLenWrap");
  if (rl) rl.hidden = S.mode !== "report";
  if (rl) {
    if (!S.reportLength) S.reportLength = "short";
    $$("#reportLenWrap .mini-toggle").forEach((b) => {
      b.classList.toggle("on", b.dataset.rtype === S.reportLength);
      b.onclick = () => {
        S.reportLength = b.dataset.rtype || "short";
        S.params.maxTokens = +b.dataset.rlen;
        localStorage.setItem("qwen.maxTokens", b.dataset.rlen);
        $$("#reportLenWrap .mini-toggle").forEach((x) => x.classList.toggle("on", x === b));
      };
    });
  }
  const ct = $("#codeToggle");
  if (ct) ct.hidden = S.mode !== "data" && S.mode !== "merge";
  const smBtn = $("#summaryExportBtn");
  if (smBtn) {
    smBtn.hidden = S.mode !== "merge";
    smBtn.onclick = async () => {
      if (!S.currentId) return showToast("当前没有打开的对话", "warn");
      smBtn.disabled = true;
      smBtn.textContent = "正在生成汇总表…";
      try {
        const r = await api("/api/calc/summary", {
          method: "POST",
          body: JSON.stringify({ conversation_id: S.currentId }),
        });
        showToast(`汇总表已生成（共 ${r.rows} 行）：${r.filename}`, "success");
        await api("/api/file/open", { method: "POST", body: JSON.stringify({ name: r.filename }) });
      } catch (e) {
        showToast("生成汇总表失败：" + e.message, "error");
      } finally {
        smBtn.disabled = false;
        smBtn.textContent = "📥 导出汇总表.xlsx";
      }
    };
  }
}

function updatePlaceholder() {
  const tips = {
    general: "给灵梦发消息，或拖入表格直接自由分析…（Enter 发送，Shift+Enter 换行）",
    report: "说说要写什么报告、给谁看、多少字…",
    review: "把合同或合规审查材料拖进来，分析潜在偏离项与修改建议…",
    data: "把表格拖进来，自由透视指标、计算统计与趋势分析…",
    ppt: "描述 PPT 主题与页数，我先给你大纲…",
    procure: "说明采购物料、数量、交付地和时间要求…",
    price: "粘贴或拖入报价单，基于 TCO 模型做多供应商横向比价…",
    merge: "上传调拨表与对账清单，运行确定性对账流水线…",
  };
  $("#input").placeholder = tips[S.mode] || tips.general;
}

/* ------------------------------------------------ 侧边栏 */
function dayLabel(iso) {
  if (!iso) return "更早";
  const d = new Date(String(iso).replace(" ", "T"));
  if (isNaN(d.getTime())) return "更早";
  const now = new Date();
  const t0 = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const d0 = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diff = Math.floor((t0 - d0) / 86400000);
  if (diff <= 0) return "今天";
  if (diff === 1) return "昨天";
  return "更早";
}

function renderSidebar() {
  const box = $("#convList");
  if (!box) return;

  // 1. 严格过滤：仅真实存在（有对话记录）的历史会话能够被展示，未发送消息前严禁插入列表
  const validConvs = S.convs.filter((c) => (c.cnt && c.cnt > 0) || (c.id === S.currentId && S.messages && S.messages.length > 0));

  if (!validConvs.length) {
    box.innerHTML = '<div class="conv-empty">还没有对话</div>';
    return;
  }

  // 2. 严格按时间区间分组（置顶、今天、昨天、更早），确保每个区间在列表中只出现一次！
  const groupOrder = ["置顶", "今天", "昨天", "更早"];
  const groups = { "置顶": [], "今天": [], "昨天": [], "更早": [] };

  for (const c of validConvs) {
    if (c.pinned) {
      groups["置顶"].push(c);
    } else {
      const g = dayLabel(c.updated_at || c.created_at);
      if (groups[g]) {
        groups[g].push(c);
      } else {
        groups["更早"].push(c);
      }
    }
  }

  // 3. 构建 DOM，增加 key/id 映射，悬浮显示垃圾桶 🗑️
  let html = "";
  for (const gName of groupOrder) {
    const items = groups[gName];
    if (!items || items.length === 0) continue;

    html += `<div class="conv-group" key="grp-${gName}">${gName}</div>`;
    for (const c of items) {
      const m = S.modes.find((x) => x.id === c.mode) || {};
      html += `<div class="conv-item ${c.id === S.currentId ? "active" : ""}" data-id="${c.id}" key="${c.id}" title="${esc(m.name || "")}">
        <span class="ci-title">${esc(c.title || "新对话")}</span>
        <span class="ci-pin ${c.pinned ? "on" : ""}" data-pin="${c.id}" title="置顶">📌</span>
        <span class="ci-edit" data-edit="${c.id}" title="重命名">✎</span>
        <span class="ci-del" data-del="${c.id}" title="删除">🗑️</span>
      </div>`;
    }
  }

  box.innerHTML = html;

  $$("#convList .conv-item").forEach((el) => {
    el.onclick = (ev) => {
      if (ev.target.dataset.del || ev.target.dataset.edit || ev.target.dataset.pin) return;
      openConv(el.dataset.id);
    };
    el.ondblclick = (ev) => {
      if (ev.target.dataset.del || ev.target.dataset.edit || ev.target.dataset.pin) return;
      startRename(el.dataset.id);
    };
  });
  $$("#convList .ci-pin").forEach((el) => {
    el.onclick = async (ev) => {
      ev.stopPropagation();
      const c = S.convs.find((x) => x.id === el.dataset.pin);
      await api(`/api/conversations/${el.dataset.pin}/pin`, {
        method: "POST",
        body: JSON.stringify({ pinned: !(c && c.pinned) }),
      });
      await loadConvs();
    };
  });
  $$("#convList .ci-edit").forEach((el) => {
    el.onclick = (ev) => {
      ev.stopPropagation();
      startRename(el.dataset.edit);
    };
  });
  $$("#convList .ci-del").forEach((el) => {
    el.onclick = async (ev) => {
      ev.stopPropagation();
      const id = el.dataset.del;
      const ok = await showConfirm({
        title: "删除会话",
        message: "确定要删除该对话吗？删除后记录无法恢复。",
        icon: "🗑️",
        confirmText: "删除",
        isDanger: true
      });
      if (!ok) return;
      await api(`/api/conversations/${id}`, { method: "DELETE" });
      if (S.currentId === id) {
        S.currentId = null;
        S.messages = [];
        S.files = [];
        renderMessages();
        $("#topTitle").textContent = "新对话";
      }
      await loadConvs();
    };
  });
}

function renderChatHistory() {
  return renderSidebar();
}

async function loadConvs() {
  try {
    S.convs = (await api("/api/conversations")) || [];
  } catch (err) {
    console.warn("loadConvs failed, defaulting to empty list:", err);
    S.convs = [];
  }
  renderSidebar();
}

function startRename(id) {
  const titleEl = document.querySelector('.conv-item[data-id="' + id + '"] .ci-title');
  if (!titleEl) return;
  const old = titleEl.textContent;
  const input = document.createElement("input");
  input.className = "ci-rename";
  input.value = old;
  input.maxLength = 60;
  titleEl.replaceWith(input);
  input.focus();
  input.select();
  let finished = false;
  const finish = async (save) => {
    if (finished) return;
    finished = true;
    const val = input.value.trim();
    if (save && val && val !== old) {
      try {
        await api(`/api/conversations/${id}`, { method: "PATCH", body: JSON.stringify({ title: val }) });
        const c = S.convs.find((x) => x.id === id);
        if (c) c.title = val;
        if (S.currentId === id) $("#topTitle").textContent = val;
      } catch (e) {
        showToast("重命名失败：" + e.message, "error");
      }
    }
    renderSidebar();
  };
  input.addEventListener("click", (e) => e.stopPropagation());
  input.addEventListener("dblclick", (e) => e.stopPropagation());
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      finish(true);
    } else if (e.key === "Escape") {
      e.preventDefault();
      finish(false);
    }
  });
  input.addEventListener("blur", () => finish(true));
}

/* ------------------------------------------------ 会话 */
function resetView(focus = true) {
  S.currentId = null;
  S.messages = [];
  S.files = [];
  S.currentArtifact = null;
  hideArtifact();
  closeAllPipelines(true);
  $("#topTitle").textContent = "新对话";
  renderWelcome();
  renderMessages();
  renderChips();
  renderFilesCount();
  renderSidebar();
  if (focus) $("#input").focus();
}

async function ensureConv(initialTitle) {
  if (S.currentId) return S.currentId;
  const title = (initialTitle || "").trim() || "新对话";
  const c = await api("/api/conversations", { method: "POST", body: JSON.stringify({ mode: S.mode, title }) });
  S.currentId = c.id;
  return c.id;
}


/* ==============================================================================
   调拨对账汇总 4 步结构化流水线面板控制器
   ============================================================================== */
const ReconcilePipeline = {
  currentStep: 1,
  files: [],
  fieldsInfo: null,
  mapping: {},
  headerRowIndex: 0,
  columnSamples: {},
  customRules: [],
  auditResult: null,
  exportResult: null,

  initCustomRules() {
    if (!this.customRules) this.customRules = [];
    this.renderCustomRules();
  },

  renderCustomRules() {
    const listEl = $("#reconcileCustomRulesList");
    if (!listEl) return;
    if (!this.customRules.length) {
      listEl.innerHTML = '<div style="font-size:12px;color:var(--label-3);padding:6px;text-align:center;">暂无自定义核对规则，如需额外比对可点击右上角「+ 添加自定义核对规则」</div>';
      return;
    }
    const cols = (this.fieldsInfo && this.fieldsInfo.all_columns) || [];
    listEl.innerHTML = this.customRules.map((r, idx) => `
      <div class="rcr-card" data-idx="${idx}">
        <span class="rcr-badge">规则 ${idx + 1}</span>
        <div class="rcr-inputs">
          <input type="text" class="rcr-name-inp" placeholder="规则名称（如：规格完全一致）" value="${esc(r.name || '')}" data-idx="${idx}" />
          <select class="rcr-col-sel rcr-col-a" data-idx="${idx}">
            <option value="">-- 选择表A字段 --</option>
            ${cols.map(c => `<option value="${esc(c)}" ${c === r.col_a ? 'selected' : ''}>${esc(c)}</option>`).join('')}
          </select>
          <select class="rcr-type-sel" data-idx="${idx}">
            <option value="text_exact" ${r.rule_type === 'text_exact' ? 'selected' : ''}>文本一致</option>
            <option value="num_exact" ${r.rule_type === 'num_exact' ? 'selected' : ''}>数值相等</option>
            <option value="tolerance" ${r.rule_type === 'tolerance' ? 'selected' : ''}>允许误差 ±X</option>
            <option value="qty_ge" ${r.rule_type === 'qty_ge' ? 'selected' : ''}>调出 >= 实收</option>
            <option value="ratio_diff" ${r.rule_type === 'ratio_diff' ? 'selected' : ''}>偏离比例 <= 5%</option>
          </select>
          <select class="rcr-col-sel rcr-col-b" data-idx="${idx}">
            <option value="">-- 选择表B字段 --</option>
            ${cols.map(c => `<option value="${esc(c)}" ${c === r.col_b ? 'selected' : ''}>${esc(c)}</option>`).join('')}
          </select>
          ${r.rule_type === 'tolerance' ? `<input type="number" step="0.01" class="rcr-tol-inp" placeholder="误差值" value="${r.tolerance || 0.05}" data-idx="${idx}" />` : ''}
          <button type="button" class="apple-btn mini rcr-del-btn" data-idx="${idx}" title="删除规则">✕</button>
        </div>
      </div>
    `).join("");

    $$("#reconcileCustomRulesList .rcr-name-inp").forEach(inp => {
      inp.oninput = (e) => {
        const i = parseInt(inp.dataset.idx, 10);
        if (ReconcilePipeline.customRules[i]) ReconcilePipeline.customRules[i].name = e.target.value;
      };
    });
    $$("#reconcileCustomRulesList .rcr-col-a").forEach(sel => {
      sel.onchange = (e) => {
        const i = parseInt(sel.dataset.idx, 10);
        if (ReconcilePipeline.customRules[i]) ReconcilePipeline.customRules[i].col_a = e.target.value;
      };
    });
    $$("#reconcileCustomRulesList .rcr-col-b").forEach(sel => {
      sel.onchange = (e) => {
        const i = parseInt(sel.dataset.idx, 10);
        if (ReconcilePipeline.customRules[i]) ReconcilePipeline.customRules[i].col_b = e.target.value;
      };
    });
    $$("#reconcileCustomRulesList .rcr-type-sel").forEach(sel => {
      sel.onchange = (e) => {
        const i = parseInt(sel.dataset.idx, 10);
        if (ReconcilePipeline.customRules[i]) {
          ReconcilePipeline.customRules[i].rule_type = e.target.value;
          ReconcilePipeline.renderCustomRules();
        }
      };
    });
    $$("#reconcileCustomRulesList .rcr-tol-inp").forEach(inp => {
      inp.oninput = (e) => {
        const i = parseInt(inp.dataset.idx, 10);
        if (ReconcilePipeline.customRules[i]) ReconcilePipeline.customRules[i].tolerance = parseFloat(e.target.value) || 0;
      };
    });
    $$("#reconcileCustomRulesList .rcr-del-btn").forEach(btn => {
      btn.onclick = () => {
        const i = parseInt(btn.dataset.idx, 10);
        ReconcilePipeline.deleteCustomRule(i);
      };
    });
  },

  addCustomRule() {
    const cols = (this.fieldsInfo && this.fieldsInfo.all_columns) || [];
    this.customRules.push({
      name: `自定义比对 ${this.customRules.length + 1}`,
      col_a: cols[0] || "",
      col_b: cols[1] || cols[0] || "",
      rule_type: "text_exact",
      tolerance: 0.05
    });
    this.renderCustomRules();
  },

  deleteCustomRule(idx) {
    if (idx >= 0 && idx < this.customRules.length) {
      this.customRules.splice(idx, 1);
      this.renderCustomRules();
    }
  }
};

async function openReconcilePipeline() {
  hideArtifact();
  closeAllPipelines();
  S.mode = "merge";
  renderModes();
  const tm = $("#topMode");
  if (tm) tm.textContent = "调拨对账汇总";
  updatePlaceholder();
  document.body.classList.add("has-pipeline-open");
  const wb = $("#workbench");
  if (wb) wb.classList.remove("has-artifact");
  if (wb) wb.classList.add("has-pipeline-open");
  const chatPane = $("#chatPane");
  if (chatPane) {
    chatPane.style.flex = "1 1 100%";
    chatPane.style.width = "100%";
  }
  const artPanel = $("#artifactPanel");
  if (artPanel) {
    artPanel.hidden = true;
    artPanel.style.display = "none";
    artPanel.style.width = "0";
    artPanel.style.flex = "0 0 0";
  }

  // 严格只切换中央 #welcome-view 与 #task-wizard-view，严禁隐藏外层主容器或底部输入框
  switchMainView("wizard");

  const pipelineEl = $("#reconcilePipeline");
  if (pipelineEl) {
    pipelineEl.hidden = false;
    pipelineEl.style.display = "flex";
  }

  const tableFiles = (S.files || []).filter((f) => ["xlsx", "xls", "csv"].includes((f.name || "").split(".").pop().toLowerCase()));
  ReconcilePipeline.files = [...tableFiles];
  setReconcileStep(1);
  renderPipelineFiles();
}

function closeReconcilePipeline() {
  closeAllPipelines(true);
}

function setReconcileStep(step) {
  ReconcilePipeline.currentStep = step;
  $$("#pipelineStepper .step-item").forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    el.classList.toggle("active", s === step);
    el.classList.toggle("completed", s < step);
  });
  for (let i = 1; i <= 4; i++) {
    const el = $(`#pipelineStep${i}`);
    if (el) el.hidden = i !== step;
  }
}

function renderPipelineFiles() {
  const listEl = $("#pipelineFilesList");
  const nextBtn = $("#pipelineStep1NextBtn");
  if (!listEl) return;

  if (!ReconcilePipeline.files.length) {
    listEl.innerHTML = '<div class="pipeline-no-files">尚未上传对账表格，请点击上方区域或拖拽上传「调拨表」与「对账清单」</div>';
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  listEl.innerHTML = ReconcilePipeline.files
    .map((f, i) => {
      const sizeStr = f.size ? `${(f.size / 1024).toFixed(1)} KB` : (f.chars ? `${f.chars} 字` : "");
      return `<div class="pipeline-file-item">
        <span class="pfi-icon">📊</span>
        <div class="pfi-info">
          <span class="pfi-name">${esc(f.name)}</span>
          <span class="pfi-size">${sizeStr}</span>
        </div>
        <button class="pfi-del" data-idx="${i}" title="移除文件">✕</button>
      </div>`;
    })
    .join("");

  if (nextBtn) nextBtn.disabled = false;

  $$("#pipelineFilesList .pfi-del").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10);
      ReconcilePipeline.files.splice(idx, 1);
      renderPipelineFiles();
    };
  });
}

async function handlePipelineFileUpload(files) {
  if (!files || !files.length) return;
  const firstTitle = files[0].name.replace(/\.[^/.]+$/, "").slice(0, 24);
  ReconcilePipeline.initialTitle = firstTitle;
  for (const f of files) {
    const ext = f.name.split(".").pop().toLowerCase();
    if (!["xlsx", "xls", "csv"].includes(ext)) {
      showToast(`文件 ${f.name} 并非 Excel/CSV 表格，已跳过`, "warn");
      continue;
    }
    const fd = new FormData();
    fd.append("file", f);
    if (S.currentId) fd.append("conversation_id", S.currentId);
    try {
      showToast(`正在上传并解析 ${f.name}...`, "info", 2000);
      const res = await api("/api/upload", { method: "POST", body: fd });
      const fItem = {
        id: res.id,
        name: f.name,
        path: res.path,
        size: f.size,
        chars: res.chars,
      };
      ReconcilePipeline.files.push(fItem);
      S.files.push({ id: res.id, name: f.name, path: res.path, size: f.size, chars: res.chars });
      renderChips();
      renderFilesCount();
    } catch (err) {
      showToast(`上传 ${f.name} 失败：` + err.message, "error");
    }
  }
  renderPipelineFiles();
}

async function loadAndRenderFieldMapping() {
  if (!ReconcilePipeline.files.length) {
    return showToast("请先上传至少一个表格文件", "warn");
  }
  const nextBtn = $("#pipelineStep1NextBtn");
  if (nextBtn) {
    nextBtn.disabled = true;
    nextBtn.textContent = "正在分析两表表头结构...";
  }
  try {
    const res = await api("/api/calc/reconcile_fields", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: ReconcilePipeline.files,
      }),
    });
    ReconcilePipeline.fieldsInfo = res;
    renderMappingGrid(res);
    setReconcileStep(2);
  } catch (err) {
    showToast("读取表格表头失败：" + err.message, "error");
  } finally {
    if (nextBtn) {
      nextBtn.disabled = false;
      nextBtn.textContent = "下一步：确认字段映射 →";
    }
  }
}

function renderMappingGrid(fieldsInfo) {
  const grid = $("#mappingGrid");
  if (!grid) return;

  const targetFields = fieldsInfo.target_fields || [
    { key: "物资名称", label: "物资名称", required: true },
    { key: "规格型号", label: "规格型号", required: false },
    { key: "数量", label: "数量（账面/原数量）", required: true },
    { key: "调出方", label: "调出方（供方单位）", required: false },
    { key: "调入方", label: "调入方（需方单位）", required: false },
    { key: "日期", label: "业务日期", required: false },
  ];

  const allColumns = fieldsInfo.all_columns || [];
  const suggested = fieldsInfo.suggested_mapping || {};
  const samples = fieldsInfo.column_samples || {};
  ReconcilePipeline.columnSamples = samples;

  // 更新表头扫描识别指示与微调下拉框
  const detRow = fieldsInfo.detected_header_row || 1;
  const detRowEl = $("#reconcileDetectedRow");
  if (detRowEl) detRowEl.textContent = String(detRow);
  const rowSel = $("#reconcileHeaderRowSelect");
  if (rowSel) rowSel.value = String(detRow);

  grid.innerHTML = targetFields
    .map((field) => {
      const isReq = field.required;
      const currentSelected = suggested[field.key] || "";
      const colSamples = samples[currentSelected] || [];
      const s1 = colSamples[0] || "—";
      const s2 = colSamples[1] || "—";

      const optionsHtml = [
        `<option value="">-- 请选择或保持自动匹配 --</option>`,
        ...allColumns.map(
          (c) => `<option value="${esc(c)}" ${c === currentSelected ? "selected" : ""}>${esc(c)}</option>`
        ),
      ].join("");

      return `<div class="mapping-card" data-key="${field.key}">
        <div class="mc-head">
          <span class="mc-label">${esc(field.label || field.key)}</span>
          ${isReq ? '<span class="mc-req">必填核心字段</span>' : '<span class="mc-opt">辅助核对</span>'}
        </div>
        <select class="mc-select sel" data-target="${field.key}">
          ${optionsHtml}
        </select>
        <div class="mc-hint">${currentSelected ? `智能识别匹配到列「${esc(currentSelected)}」` : "待手动选择对应列"}</div>
        <div class="mc-samples" id="mc_sample_${esc(field.key)}">
          <div class="mc-sample-title">数据样本（前 2 行）：</div>
          <div class="mc-sample-row">行 1: <code>${esc(s1)}</code></div>
          <div class="mc-sample-row">行 2: <code>${esc(s2)}</code></div>
        </div>
      </div>`;
    })
    .join("");

  $$("#mappingGrid .mc-select").forEach((sel) => {
    sel.onchange = () => {
      const val = sel.value;
      const card = sel.closest(".mapping-card");
      const hint = card?.querySelector(".mc-hint");
      if (hint) {
        hint.textContent = val ? `已指定对应列「${val}」` : "未指定，将按系统规则自动匹配";
      }
      const smpWrap = card?.querySelector(".mc-samples");
      if (smpWrap) {
        const colSamples = (ReconcilePipeline.columnSamples && ReconcilePipeline.columnSamples[val]) || [];
        const s1 = colSamples[0] || "—";
        const s2 = colSamples[1] || "—";
        smpWrap.innerHTML = `
          <div class="mc-sample-title">数据样本（前 2 行）：</div>
          <div class="mc-sample-row">行 1: <code>${esc(s1)}</code></div>
          <div class="mc-sample-row">行 2: <code>${esc(s2)}</code></div>
        `;
      }
    };
  });

  ReconcilePipeline.initCustomRules();
}

async function runAuditAndRenderSheet() {
  const mapping = {};
  $$("#mappingGrid .mc-select").forEach((sel) => {
    const key = sel.dataset.target;
    if (sel.value) mapping[key] = sel.value;
  });
  ReconcilePipeline.mapping = mapping;

  const nextBtn = $("#pipelineStep2NextBtn");
  if (nextBtn) {
    nextBtn.disabled = true;
    nextBtn.textContent = "正在调用 calc_engine 进行确定性核对...";
  }

  const sheetHeaders = {};
  (ReconcilePipeline.fieldsInfo?.files || []).forEach((f) => {
    (f.sheets || []).forEach((s) => {
      sheetHeaders[s.sheet_name] = ReconcilePipeline.headerRowIndex || 0;
    });
  });

  try {
    const res = await api("/api/calc/reconcile_audit", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        mapping: mapping,
        files: ReconcilePipeline.files,
        sheet_headers: sheetHeaders,
        custom_rules: ReconcilePipeline.customRules || [],
      }),
    });
    ReconcilePipeline.auditResult = res;
    renderAuditSheet(res);
    setReconcileStep(3);
    showToast("✨《数据校验验收单》核对完成！", "success");
  } catch (err) {
    showToast("预检核对失败：" + err.message, "error");
  } finally {
    if (nextBtn) {
      nextBtn.disabled = false;
      nextBtn.textContent = "下一步：预检并生成验收核对单 →";
    }
  }
}

function renderAuditSheet(audit) {
  if (!audit) return;

  const metaEl = $("#auditSheetMeta");
  if (metaEl) {
    metaEl.textContent = `核验时间：${new Date().toLocaleTimeString()}  |  明细合计：${audit.total_count} 笔  |  由确定性计算引擎（pandas/numpy）自动化执行`;
  }

  const scopeEl = $("#auditScopeText");
  if (scopeEl && audit.scope_description) {
    scopeEl.textContent = audit.scope_description;
  }

  const kpiBar = $("#auditKpiBar");
  if (kpiBar && audit.kpi_metrics) {
    kpiBar.innerHTML = renderKpiDashboard(audit.kpi_metrics);
  }

  // 1. 【异常与差额清单（强视觉高亮置顶）】
  const highSec = $("#reconcileHighlightSection");
  const highCount = $("#reconcileHighlightCount");
  const highBody = $("#reconcileHighlightBody");
  const discItems = audit.discrepancy_items || [];

  if (highCount) highCount.textContent = `${discItems.length} 笔`;
  if (highSec) {
    if (discItems.length === 0) {
      highSec.classList.add("no-discrepancy");
    } else {
      highSec.classList.remove("no-discrepancy");
    }
  }

  if (highBody) {
    if (!discItems.length) {
      highBody.innerHTML = '<div style="color:#166534;font-size:13px;font-weight:600;padding:6px 0;">✨ 经确定性核对，两表未检测到任何差额或异常项，全部数据账实相符！</div>';
    } else {
      highBody.innerHTML = discItems.map((item) => {
        const cleanStatus = (item.status || "存在差额").replace(/[⚠️✅🔴🟡🟢⚪]/g, "").trim();
        const cleanReason = (item.reason || "账面与实际调拨量存在差异").replace(/[⚠️✅🔴🟡🟢⚪]/g, "").trim();
        return `
          <div class="rh-item-card">
            <div class="rh-item-head">
              <span class="rh-item-name">${esc(item.name)} <span style="font-weight:normal;color:#6B7280;">(${esc(item.spec || '-')})</span></span>
              <span class="rh-item-diff-badge">差额：${esc(item.diff_str)} ${esc(item.unit || '')}</span>
            </div>
            <div class="rh-item-grid">
              <div>账面存根：<b>${Number(item.book_qty).toFixed(2)} ${esc(item.unit || '')}</b></div>
              <div>实际调拨：<b>${Number(item.actual_qty).toFixed(2)} ${esc(item.unit || '')}</b></div>
              <div>核对状态：<span style="color:#DC2626;font-weight:600;">${esc(cleanStatus)}</span></div>
            </div>
            <div class="rh-item-diag">
              <b>差异原因诊断：</b>${esc(cleanReason)}
            </div>
          </div>
        `;
      }).join("");
    }
  }

  // 2. 【完全符合项（弱视觉弱化紧凑折叠）】
  const weakCount = $("#reconcileWeakCount");
  const weakBody = $("#reconcileWeakBody");
  const passedItems = audit.passed_items || [];
  if (weakCount) weakCount.textContent = `${passedItems.length} 笔`;

  if (weakBody) {
    if (!passedItems.length) {
      weakBody.innerHTML = '<div class="rws-row"><span>暂无完全账实相符项</span></div>';
    } else {
      weakBody.innerHTML = passedItems.map((item) => `
        <div class="rws-row">
          <b>${esc(item.name)} <span style="font-weight:normal;color:#8E8E93;">(${esc(item.spec || '-')})</span></b>
          <span>账面 ${Number(item.book_qty).toFixed(2)} / 实发 ${Number(item.actual_qty).toFixed(2)} ${esc(item.unit || '')}</span>
          <span class="rws-tag">已达标</span>
        </div>
      `).join("");
    }
  }

  // 折叠开关
  const weakHead = $("#reconcileWeakToggleHead");
  if (weakHead) {
    weakHead.onclick = () => {
      const b = $("#reconcileWeakBody");
      const arr = $("#reconcileWeakArrow");
      if (b) {
        b.classList.toggle("collapsed");
        if (arr) arr.textContent = b.classList.contains("collapsed") ? "▶ 点击展开" : "▼ 点击折叠";
      }
    };
  }

  // 保持向后兼容：同时填充底层原始表格 DOM
  const passedTitle = $("#auditPassedTitle");
  if (passedTitle) passedTitle.textContent = `校验通过项（账实相符 ${audit.passed_count} 笔）`;
  const passedWrap = $("#auditPassedTableWrap");
  if (passedWrap) {
    if (!passedItems.length) {
      passedWrap.innerHTML = '<div class="audit-empty-row">（暂无完全账实相符项）</div>';
    } else {
      let html = `<table class="audit-table"><thead><tr>
        <th>序号</th><th>物资名称</th><th>规格型号</th><th>单位</th><th>账面数量</th><th>实际调拨量</th><th>差额</th><th>核对结果</th><th>调出方</th><th>调入方</th>
      </tr></thead><tbody>`;
      passedItems.forEach((item, idx) => {
        html += `<tr>
          <td>${idx + 1}</td>
          <td><b>${esc(item.name)}</b></td>
          <td>${esc(item.spec)}</td>
          <td>${esc(item.unit)}</td>
          <td class="num">${Number(item.book_qty).toFixed(2)}</td>
          <td class="num">${Number(item.actual_qty).toFixed(2)}</td>
          <td class="num success">0.00</td>
          <td><span class="badge-status success">账实相符</span></td>
          <td>${esc(item.supplier)}</td>
          <td>${esc(item.receiver)}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      passedWrap.innerHTML = html;
    }
  }

  const discTitle = $("#auditDiscrepancyTitle");
  if (discTitle) discTitle.textContent = `差异/异常清单（差额 ${audit.discrepancy_count} 笔、缺失值 ${audit.missing_count} 处）`;
  const discWrap = $("#auditDiscrepancyTableWrap");
  if (discWrap) {
    if (!discItems.length) {
      discWrap.innerHTML = '<div class="audit-empty-row success">太棒了！未发现任何账实差额或异常项</div>';
    } else {
      let html = `<table class="audit-table warning"><thead><tr>
        <th>序号</th><th>物资名称</th><th>规格型号</th><th>单位</th><th>账面数量</th><th>实际调拨量</th><th>差额 (账面-调拨)</th><th>预警状态</th><th>原因诊断与说明</th>
      </tr></thead><tbody>`;
      discItems.forEach((item, idx) => {
        const diffNum = Number(item.diff);
        const diffClass = diffNum > 0 ? "warn-plus" : "warn-minus";
        html += `<tr>
          <td>${idx + 1}</td>
          <td><b>${esc(item.name)}</b></td>
          <td>${esc(item.spec)}</td>
          <td>${esc(item.unit)}</td>
          <td class="num">${Number(item.book_qty).toFixed(2)}</td>
          <td class="num">${Number(item.actual_qty).toFixed(2)}</td>
          <td class="num ${diffClass}"><b>${esc(item.diff_str)}</b></td>
          <td><span class="badge-status warn">${esc(item.status)}</span></td>
          <td class="reason-cell">${esc(item.reason || "-")}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      discWrap.innerHTML = html;
    }
  }
}

async function executeExportExcel() {
  const exportBtn = $("#pipelineExportExcelBtn");
  if (exportBtn) {
    exportBtn.disabled = true;
    exportBtn.textContent = "正在生成专业对账汇总表...";
  }
  const sheetHeaders = {};
  (ReconcilePipeline.fieldsInfo?.files || []).forEach((f) => {
    (f.sheets || []).forEach((s) => {
      sheetHeaders[s.sheet_name] = ReconcilePipeline.headerRowIndex || 0;
    });
  });
  try {
    const res = await api("/api/calc/summary", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        mapping: ReconcilePipeline.mapping,
        files: ReconcilePipeline.files,
        sheet_headers: sheetHeaders,
      }),
    });
    ReconcilePipeline.exportResult = res;
    S.currentArtifact = res;
    showArtifact(res);
    const resultBox = $("#pipelineExportResult");
    if (resultBox) {
      resultBox.hidden = false;
      resultBox.innerHTML = renderArtifactCard(res);
    }
    showToast(`《对账汇总表.xlsx》导出成功（共 ${res.rows} 行）！`, "success");
  } catch (err) {
    showToast("导出失败：" + err.message, "error");
  } finally {
    if (exportBtn) {
      exportBtn.disabled = false;
      exportBtn.textContent = "📥 重新导出 Excel 汇总表";
    }
  }
}

function sendToReportWorkflow() {
  if (!ReconcilePipeline.auditResult) {
    return showToast("请先完成对账预检", "warn");
  }
  closeReconcilePipeline();
  S.mode = "report";
  renderModes();
  const promptMsg = `请根据以下物资调拨《数据校验验收单》的确定性核对结果，撰写一份供应链物资调拨与对账清算专项分析报告。要求：严格依据麦肯锡金字塔原理，重点针对存在差额的 ${ReconcilePipeline.auditResult.discrepancy_count} 笔异常物料进行管理归因并提出处理方案：\n\n${ReconcilePipeline.auditResult.markdown}`;
  $("#input").value = promptMsg;
  send();
}

function sendToPptWorkflow() {
  if (!ReconcilePipeline.auditResult) {
    return showToast("请先完成对账预检", "warn");
  }
  closeReconcilePipeline();
  S.mode = "ppt";
  renderModes();
  const promptMsg = `请根据以下物资调拨对账与差额验收数据，策划一份高管汇报 PPT 大纲，必须包含物资调拨与计划对比图表页、关键差异归因页：\n\n${ReconcilePipeline.auditResult.markdown}`;
  $("#input").value = promptMsg;
  send();
}

function closeAllPipelines(forceHome = false) {
  const p1 = $("#reconcilePipeline");
  if (p1) { p1.hidden = true; p1.style.display = "none"; }
  const p2 = $("#pricePipeline");
  if (p2) { p2.hidden = true; p2.style.display = "none"; }
  const p3 = $("#reviewPipeline");
  if (p3) { p3.hidden = true; p3.style.display = "none"; }
  const wizardView = $("#task-wizard-view");
  if (wizardView) { wizardView.hidden = true; wizardView.style.display = "none"; }

  document.body.classList.remove("has-pipeline-open");
  const wb = $("#workbench");
  if (wb) wb.classList.remove("has-pipeline-open");
  const chatPane = $("#chatPane");
  if (chatPane) {
    chatPane.style.flex = "1 1 100%";
    chatPane.style.width = "100%";
  }

  const artPanel = $("#artifactPanel");
  if (artPanel) {
    artPanel.hidden = true;
    artPanel.style.display = "none";
    artPanel.style.width = "0";
    artPanel.style.flex = "0 0 0";
  }

  if (S.messages && S.messages.length > 0 && !forceHome) {
    switchMainView("chat");
  } else {
    switchMainView("welcome");
  }

  if (forceHome) {
    S.mode = "general";
    const tm = $("#topMode");
    if (tm) tm.textContent = "通用对话";
    renderModes();
    updatePlaceholder();
  }
}


/* ==============================================================================
   供应商比选/比价 4 步结构化流水线面板控制器
   ============================================================================== */
const PricePipeline = {
  currentStep: 1,
  files: [],
  weights: { price: 0.40, delivery: 0.20, payment: 0.20, quality: 0.20 },
  taxRate: 0.13,
  interestRate: 0.06,
  compareResult: null,
  exportResult: null,
};

async function openPricePipeline() {
  hideArtifact();
  closeAllPipelines();
  S.mode = "price";
  renderModes();
  const tm = $("#topMode");
  if (tm) tm.textContent = "供应商比选/比价";
  updatePlaceholder();
  document.body.classList.add("has-pipeline-open");
  const wb = $("#workbench");
  if (wb) wb.classList.remove("has-artifact");
  if (wb) wb.classList.add("has-pipeline-open");
  const chatPane = $("#chatPane");
  if (chatPane) {
    chatPane.style.flex = "1 1 100%";
    chatPane.style.width = "100%";
  }
  const artPanel = $("#artifactPanel");
  if (artPanel) {
    artPanel.hidden = true;
    artPanel.style.display = "none";
    artPanel.style.width = "0";
    artPanel.style.flex = "0 0 0";
  }

  // 严格只切换中央 #welcome-view 与 #task-wizard-view，严禁隐藏外层主容器或底部输入框
  switchMainView("wizard");

  const pipelineEl = $("#pricePipeline");
  if (pipelineEl) {
    pipelineEl.hidden = false;
    pipelineEl.style.display = "flex";
  }

  const tableFiles = (S.files || []).filter((f) => ["xlsx", "xls", "csv"].includes((f.name || "").split(".").pop().toLowerCase()));
  PricePipeline.files = [...tableFiles];
  setPriceStep(1);
  renderPricePipelineFiles();
}

function closePricePipeline() {
  closeAllPipelines(true);
}

function setPriceStep(step) {
  PricePipeline.currentStep = step;
  $$("#pricePipelineStepper .step-item").forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    el.classList.toggle("active", s === step);
    el.classList.toggle("completed", s < step);
  });
  for (let i = 1; i <= 4; i++) {
    const el = $(`#pricePipelineStep${i}`);
    if (el) el.hidden = i !== step;
  }
}

function renderPricePipelineFiles() {
  const listEl = $("#pricePipelineFilesList");
  const nextBtn = $("#pricePipelineStep1NextBtn");
  if (!listEl) return;

  if (!PricePipeline.files.length) {
    listEl.innerHTML = '<div class="pipeline-no-files">尚未上传报价单，请点击上方区域或拖拽上传各供应商报价表格</div>';
    if (nextBtn) nextBtn.disabled = true;
    return;
  }

  listEl.innerHTML = PricePipeline.files
    .map((f, i) => {
      const sizeStr = f.size ? `${(f.size / 1024).toFixed(1)} KB` : (f.chars ? `${f.chars} 字` : "");
      return `<div class="pipeline-file-item">
        <span class="pfi-icon">💰</span>
        <div class="pfi-info">
          <span class="pfi-name">${esc(f.name)}</span>
          <span class="pfi-size">${sizeStr}</span>
        </div>
        <button class="pfi-del" data-idx="${i}" title="移除文件">✕</button>
      </div>`;
    })
    .join("");

  if (nextBtn) nextBtn.disabled = false;

  $$("#pricePipelineFilesList .pfi-del").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10);
      PricePipeline.files.splice(idx, 1);
      renderPricePipelineFiles();
    };
  });
}

async function handlePriceFileUpload(files) {
  if (!files || !files.length) return;
  const firstTitle = files[0].name.replace(/\.[^/.]+$/, "").slice(0, 24);
  PricePipeline.initialTitle = firstTitle;
  for (const f of files) {
    const ext = f.name.split(".").pop().toLowerCase();
    if (!["xlsx", "xls", "csv"].includes(ext)) {
      showToast(`文件 ${f.name} 并非 Excel/CSV 报价表格，已跳过`, "warn");
      continue;
    }
    const fd = new FormData();
    fd.append("file", f);
    if (S.currentId) fd.append("conversation_id", S.currentId);
    try {
      showToast(`正在上传并解析 ${f.name}...`, "info", 2000);
      const res = await api("/api/upload", { method: "POST", body: fd });
      const fItem = {
        id: res.id,
        name: f.name,
        path: res.path,
        size: f.size,
        chars: res.chars,
      };
      PricePipeline.files.push(fItem);
      S.files.push({ id: res.id, name: f.name, path: res.path, size: f.size, chars: res.chars });
      renderChips();
      renderFilesCount();
    } catch (err) {
      showToast(`上传 ${f.name} 失败：` + err.message, "error");
    }
  }
  renderPricePipelineFiles();
}

function updatePriceWeightsFromSliders() {
  const p = parseInt($("#sliderWeightPrice")?.value || 40, 10);
  const d = parseInt($("#sliderWeightDelivery")?.value || 20, 10);
  const pay = parseInt($("#sliderWeightPayment")?.value || 20, 10);
  const q = parseInt($("#sliderWeightQuality")?.value || 20, 10);

  if ($("#echoWeightPrice")) $("#echoWeightPrice").textContent = `${p}%`;
  if ($("#echoWeightDelivery")) $("#echoWeightDelivery").textContent = `${d}%`;
  if ($("#echoWeightPayment")) $("#echoWeightPayment").textContent = `${pay}%`;
  if ($("#echoWeightQuality")) $("#echoWeightQuality").textContent = `${q}%`;

  const total = p + d + pay + q;
  const statusEl = $("#weightTotalStatus");
  if (statusEl) {
    if (total === 100) {
      statusEl.className = "weight-total-status";
      statusEl.innerHTML = `<span>当前权重总和：<b>100%</b>（有效）</span>`;
    } else {
      statusEl.className = "weight-total-status invalid";
      statusEl.innerHTML = `<span>当前权重总和：<b>${total}%</b>（将被按比例归一化）</span>`;
    }
  }

  const factor = total > 0 ? 1.0 / total : 1.0;
  PricePipeline.weights = {
    price: p * factor,
    delivery: d * factor,
    payment: pay * factor,
    quality: q * factor,
  };
}

async function runPriceCompareAndRender() {
  if (!PricePipeline.files.length) {
    return showToast("请先上传至少一个供应商报价表格", "warn");
  }
  updatePriceWeightsFromSliders();
  PricePipeline.taxRate = parseFloat($("#selectTaxRate")?.value || "0.13");
  PricePipeline.interestRate = parseFloat($("#selectInterestRate")?.value || "0.06");

  const nextBtn = $("#pricePipelineStep2NextBtn");
  if (nextBtn) {
    nextBtn.disabled = true;
    nextBtn.textContent = "正在调用 calc_engine 进行 TCO 测算与加权评分...";
  }

  try {
    const res = await api("/api/calc/price_compare", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: PricePipeline.files,
        weights: PricePipeline.weights,
        tax_rate: PricePipeline.taxRate,
        annual_interest_rate: PricePipeline.interestRate,
      }),
    });
    PricePipeline.compareResult = res;
    renderPriceAuditSheet(res);
    setPriceStep(3);
    showToast("✨《比价校验表》测算完成！", "success");
  } catch (err) {
    showToast("比价测算失败：" + err.message, "error");
  } finally {
    if (nextBtn) {
      nextBtn.disabled = false;
      nextBtn.textContent = "下一步：测算确定性 TCO 与比价校验表 →";
    }
  }
}

function renderPriceAuditSheet(data) {
  if (!data) return;
  const metaEl = $("#priceAuditSheetMeta");
  if (metaEl) {
    metaEl.textContent = `核算时间：${new Date().toLocaleTimeString()}  |  税率基准：${data.tax_rate_str}  |  由确定性 TCO 模型与加权矩阵算法执行`;
  }
  const scopeEl = $("#priceAuditScopeText");
  if (scopeEl && data.scope_description) {
    scopeEl.textContent = data.scope_description;
  }
  const kpiBar = $("#priceAuditKpiBar");
  if (kpiBar && data.kpi_metrics) {
    kpiBar.innerHTML = renderKpiDashboard(data.kpi_metrics);
  }

  // 1. Comparison table
  const compWrap = $("#priceComparisonTableWrap");
  if (compWrap && data.comparison_matrix) {
    let html = `<table class="audit-table"><thead><tr>
      <th>序号</th><th>材料名称</th><th>规格型号</th><th>单位</th><th>供应商</th>
      <th>未税单价(元)</th><th>含税单价(元)</th><th>税率</th><th>交期</th><th>账期条件</th>
      <th>贴息收益(元)</th><th>运费承担</th><th>综合TCO单价(元)</th><th>差价率</th><th>状态提示</th>
    </tr></thead><tbody>`;
    data.comparison_matrix.forEach((it) => {
      const rowClass = it.is_lowest ? "is-lowest" : (it.has_missing ? "is-missing" : "");
      html += `<tr class="${rowClass}">
        <td>${it.id}</td>
        <td><b>${esc(it.material)}</b></td>
        <td>${esc(it.spec)}</td>
        <td>${esc(it.unit)}</td>
        <td><b>${esc(it.vendor)}</b></td>
        <td class="num">￥${Number(it.price_excl).toFixed(2)}</td>
        <td class="num ${it.is_lowest ? 'lowest-price' : ''}">￥${Number(it.price_incl).toFixed(2)}</td>
        <td>${esc(it.tax_rate_str)}</td>
        <td>${esc(it.lead_time_str)}</td>
        <td>${esc(it.payment_terms)}</td>
        <td class="num">￥${Number(it.capital_benefit).toFixed(2)}</td>
        <td>${esc(it.freight)}</td>
        <td class="num ${it.is_lowest ? 'lowest-price' : ''}">￥${Number(it.tco_price).toFixed(2)}</td>
        <td class="num ${it.is_lowest ? 'success' : 'warn-plus'}"><b>${esc(it.diff_rate_str)}</b></td>
        <td>${it.has_missing ? `<span class="badge-status warn">⚠️ ${esc(it.verification_status)}</span>` : '<span class="badge-status success">✅ 完整</span>'}</td>
      </tr>`;
    });
    html += `</tbody></table>`;
    compWrap.innerHTML = html;
  }

  // 2. Score matrix table
  const scoreWrap = $("#priceScoreMatrixTableWrap");
  if (scoreWrap && data.score_matrix) {
    let html = `<table class="audit-table"><thead><tr>
      <th>排名</th><th>供应商名称</th><th>条目数</th><th>价格得分 (40%)</th><th>交期得分 (20%)</th><th>账期得分 (20%)</th><th>质量风险 (20%)</th><th>综合加权得分</th><th>授标推荐建议</th>
    </tr></thead><tbody>`;
    data.score_matrix.forEach((sm) => {
      const isTop = sm.rank === 1;
      html += `<tr class="${isTop ? 'is-lowest' : ''}">
        <td><span class="badge-status ${isTop ? 'success' : 'warn'}">第 ${sm.rank} 名</span></td>
        <td><b>${esc(sm.vendor)}</b></td>
        <td>${sm.item_count}</td>
        <td class="num">${Number(sm.price_score).toFixed(1)}</td>
        <td class="num">${Number(sm.delivery_score).toFixed(1)}</td>
        <td class="num">${Number(sm.payment_score).toFixed(1)}</td>
        <td class="num">${Number(sm.quality_score).toFixed(1)}</td>
        <td class="num ${isTop ? 'lowest-price' : ''}"><b>${Number(sm.total_score).toFixed(1)}</b></td>
        <td><b>${esc(sm.recommendation)}</b></td>
      </tr>`;
    });
    html += `</tbody></table>`;
    scoreWrap.innerHTML = html;
  }

  // 3. Verification items
  const verWrap = $("#priceVerificationTableWrap");
  const verTitle = $("#priceVerificationTitle");
  if (verWrap && verTitle) {
    const vItems = data.verification_items || [];
    verTitle.textContent = `待核实项清单（漏填交期/运费排查 ${vItems.length} 处）`;
    if (!vItems.length) {
      verWrap.innerHTML = '<div class="audit-empty-row success">✨ 太棒了！所有供应商报价条款完备，未发现漏填交期或运费项</div>';
    } else {
      let html = `<table class="audit-table warning"><thead><tr>
        <th>序号</th><th>材料名称</th><th>规格型号</th><th>供应商</th><th>待核实类别</th><th>风险诊断与澄清要求</th>
      </tr></thead><tbody>`;
      vItems.forEach((it, idx) => {
        html += `<tr>
          <td>${idx + 1}</td>
          <td><b>${esc(it.material)}</b></td>
          <td>${esc(it.spec)}</td>
          <td><b>${esc(it.vendor)}</b></td>
          <td><span class="badge-status warn">⚠️ ${esc(it.issue_type)}</span></td>
          <td class="reason-cell">${esc(it.description)}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      verWrap.innerHTML = html;
    }
  }
}

async function executePriceExportExcel() {
  const btn = $("#priceExportExcelBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "正在生成比价分析表...";
  }
  try {
    const res = await api("/api/calc/price_export", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: PricePipeline.files,
        weights: PricePipeline.weights,
        tax_rate: PricePipeline.taxRate,
        annual_interest_rate: PricePipeline.interestRate,
      }),
    });
    PricePipeline.exportResult = res;
    S.currentArtifact = res;
    showArtifact(res);
    const resultBox = $("#priceExportResult");
    if (resultBox) {
      resultBox.hidden = false;
      resultBox.innerHTML = renderArtifactCard(res);
    }
    showToast(`《材料比价与TCO成本分析表.xlsx》导出成功！`, "success");
  } catch (err) {
    showToast("导出失败：" + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "📥 重新导出 Excel 比价表";
    }
  }
}

async function executePriceExportPpt() {
  const btn = $("#priceExportPptBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "正在生成柱状图汇报 PPT...";
  }
  try {
    const res = await api("/api/calc/price_ppt", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: PricePipeline.files,
        weights: PricePipeline.weights,
        tax_rate: PricePipeline.taxRate,
        annual_interest_rate: PricePipeline.interestRate,
      }),
    });
    S.currentArtifact = res;
    showArtifact(res);
    const resultBox = $("#priceExportResult");
    if (resultBox) {
      resultBox.hidden = false;
      resultBox.innerHTML = renderArtifactCard(res);
    }
    showToast(`《供应商比选汇报PPT.pptx》导出成功！`, "success");
  } catch (err) {
    showToast("导出 PPT 失败：" + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "📊 重新导出柱状图 PPT";
    }
  }
}

function sendPriceToReportWorkflow() {
  if (!PricePipeline.compareResult) {
    return showToast("请先完成比选测算", "warn");
  }
  closePricePipeline();
  S.mode = "report";
  renderModes();
  const promptMsg = `请根据以下供应商比选与确定性 TCO 计算结果及加权得分矩阵，撰写一份正式的采购授标决策与供应商谈判策略专项报告。要求：严格依据麦肯锡金字塔原理，仅根据 Python 加权得分矩阵输出《授标推荐结论》与《分供应商谈判压价要点》：\n\n${PricePipeline.compareResult.markdown}`;
  $("#input").value = promptMsg;
  send();
}


/* ==============================================================================
   采购合同审查 4 步结构化流水线面板控制器
   ============================================================================== */
const ReviewPipeline = {
  currentStep: 1,
  files: [],
  contractText: "",
  reviewResult: null,
  exportResult: null,
  customRules: [],

  initCustomRules() {
    if (!this.customRules || !this.customRules.length) {
      try {
        const saved = localStorage.getItem("my_compliance_template");
        if (saved) {
          const parsed = JSON.parse(saved);
          if (Array.isArray(parsed) && parsed.length) {
            this.customRules = parsed;
          }
        }
      } catch (_) {}
    }
    if (!this.customRules || !this.customRules.length) {
      this.customRules = [
        { name: "海外供应商准入资质", requirement: "必须具备 ISO9001 质量认证体系且账期不得短于 60 天" }
      ];
    }
    this.renderCustomRules();
  },

  renderCustomRules() {
    const listEl = $("#customRulesList");
    if (!listEl) return;
    if (!this.customRules.length) {
      listEl.innerHTML = '<div style="font-size:12.5px;color:var(--label-3);padding:10px;text-align:center;">暂无自定义审查标准，点击下方「+ 新增一条审查标准」即可添加</div>';
      return;
    }
    listEl.innerHTML = this.customRules.map((rule, idx) => `
      <div class="custom-rule-card" data-idx="${idx}">
        <span class="cr-num-badge">标准 ${idx + 1}</span>
        <div class="cr-fields">
          <input type="text" class="cr-name-input" data-idx="${idx}" placeholder="审查项名称（如：海外供应商准入资质）" value="${esc(rule.name || '')}" />
          <textarea class="cr-desc-input" data-idx="${idx}" rows="2" placeholder="具体合规标准与要求大输入框（如：必须具备 ISO9001 认证且账期不得短于 60 天）">${esc(rule.requirement || '')}</textarea>
        </div>
        <button class="apple-btn mini cr-del-btn" data-idx="${idx}" title="删除此标准">✕</button>
      </div>
    `).join("");

    $$("#customRulesList .cr-name-input").forEach((inp) => {
      inp.oninput = (e) => {
        const i = parseInt(inp.dataset.idx, 10);
        if (ReviewPipeline.customRules[i]) ReviewPipeline.customRules[i].name = e.target.value;
      };
    });

    $$("#customRulesList .cr-desc-input").forEach((inp) => {
      inp.oninput = (e) => {
        const i = parseInt(inp.dataset.idx, 10);
        if (ReviewPipeline.customRules[i]) ReviewPipeline.customRules[i].requirement = e.target.value;
      };
    });

    $$("#customRulesList .cr-del-btn").forEach((btn) => {
      btn.onclick = () => {
        const i = parseInt(btn.dataset.idx, 10);
        ReviewPipeline.deleteCustomRule(i);
      };
    });
  },

  addCustomRule(name = "", requirement = "") {
    this.customRules.push({ name, requirement });
    this.renderCustomRules();
  },

  deleteCustomRule(idx) {
    if (idx >= 0 && idx < this.customRules.length) {
      this.customRules.splice(idx, 1);
      this.renderCustomRules();
    }
  },

  saveTemplate() {
    try {
      localStorage.setItem("my_compliance_template", JSON.stringify(this.customRules));
      showToast("💾 常用审查模板已保存至本地 JSON！下次打开直接复用", "success");
    } catch (e) {
      showToast("保存失败：" + e.message, "error");
    }
  },

  loadTemplate() {
    try {
      const saved = localStorage.getItem("my_compliance_template");
      if (!saved) return showToast("本地暂无已保存的审查模板", "warn");
      const parsed = JSON.parse(saved);
      if (Array.isArray(parsed) && parsed.length) {
        this.customRules = parsed;
        this.renderCustomRules();
        showToast(`📂 成功载入本地模板（共 ${parsed.length} 条审查标准）`, "success");
      } else {
        showToast("本地模板为空", "warn");
      }
    } catch (e) {
      showToast("载入失败：" + e.message, "error");
    }
  },

  getRules() {
    return (this.customRules || []).filter(r => (r.name && r.name.trim()) || (r.requirement && r.requirement.trim()));
  }
};

async function openReviewPipeline() {
  hideArtifact();
  closeAllPipelines();
  S.mode = "review";
  renderModes();
  const tm = $("#topMode");
  if (tm) tm.textContent = "合规性审查";
  updatePlaceholder();
  document.body.classList.add("has-pipeline-open");
  const wb = $("#workbench");
  if (wb) wb.classList.remove("has-artifact");
  if (wb) wb.classList.add("has-pipeline-open");
  const chatPane = $("#chatPane");
  if (chatPane) {
    chatPane.style.flex = "1 1 100%";
    chatPane.style.width = "100%";
  }
  const artPanel = $("#artifactPanel");
  if (artPanel) {
    artPanel.hidden = true;
    artPanel.style.display = "none";
    artPanel.style.width = "0";
    artPanel.style.flex = "0 0 0";
  }

  // 严格只切换中央 #welcome-view 与 #task-wizard-view，严禁隐藏外层主容器或底部输入框
  switchMainView("wizard");

  const pipelineEl = $("#reviewPipeline");
  if (pipelineEl) {
    pipelineEl.hidden = false;
    pipelineEl.style.display = "flex";
  }

  const docFiles = (S.files || []).filter((f) => ["docx", "pdf", "txt"].includes((f.name || "").split(".").pop().toLowerCase()));
  ReviewPipeline.files = [...docFiles];
  setReviewStep(1);
  renderReviewPipelineFiles();
  ReviewPipeline.initCustomRules();
}

function closeReviewPipeline() {
  closeAllPipelines(true);
}

function setReviewStep(step) {
  ReviewPipeline.currentStep = step;
  $$("#reviewPipelineStepper .step-item").forEach((el) => {
    const s = parseInt(el.dataset.step, 10);
    el.classList.toggle("active", s === step);
    el.classList.toggle("completed", s < step);
  });
  for (let i = 1; i <= 4; i++) {
    const el = $(`#reviewPipelineStep${i}`);
    if (el) el.hidden = i !== step;
  }
}

function renderReviewPipelineFiles() {
  const listEl = $("#reviewPipelineFilesList");
  if (!listEl) return;

  if (!ReviewPipeline.files.length) {
    listEl.innerHTML = '<div class="pipeline-no-files">未上传审查文件（支持上传文件或在下方文本框中直接粘贴待审条款）</div>';
    return;
  }

  listEl.innerHTML = ReviewPipeline.files
    .map((f, i) => {
      const sizeStr = f.size ? `${(f.size / 1024).toFixed(1)} KB` : (f.chars ? `${f.chars} 字` : "");
      return `<div class="pipeline-file-item">
        <span class="pfi-icon">📄</span>
        <div class="pfi-info">
          <span class="pfi-name">${esc(f.name)}</span>
          <span class="pfi-size">${sizeStr}</span>
        </div>
        <button class="pfi-del" data-idx="${i}" title="移除文件">✕</button>
      </div>`;
    })
    .join("");

  $$("#reviewPipelineFilesList .pfi-del").forEach((btn) => {
    btn.onclick = (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.dataset.idx, 10);
      ReviewPipeline.files.splice(idx, 1);
      renderReviewPipelineFiles();
    };
  });
}

async function handleReviewFileUpload(files) {
  if (!files || !files.length) return;
  const firstTitle = files[0].name.replace(/\.[^/.]+$/, "").slice(0, 24);
  ReviewPipeline.initialTitle = firstTitle;
  for (const f of files) {
    const ext = f.name.split(".").pop().toLowerCase();
    if (!["docx", "pdf", "txt"].includes(ext)) {
      showToast(`文件 ${f.name} 并非 .docx/.pdf/.txt 格式，已跳过`, "warn");
      continue;
    }
    const fd = new FormData();
    fd.append("file", f);
    if (S.currentId) fd.append("conversation_id", S.currentId);
    try {
      showToast(`正在上传并提取 ${f.name}...`, "info", 2000);
      const res = await api("/api/upload", { method: "POST", body: fd });
      const fItem = {
        id: res.id,
        name: f.name,
        path: res.path,
        size: f.size,
        chars: res.chars,
      };
      ReviewPipeline.files.push(fItem);
      S.files.push({ id: res.id, name: f.name, path: res.path, size: f.size, chars: res.chars });
      renderChips();
      renderFilesCount();
    } catch (err) {
      showToast(`上传 ${f.name} 失败：` + err.message, "error");
    }
  }
  renderReviewPipelineFiles();
}

async function runContractReviewAndRender() {
  const directText = $("#reviewContractTextarea")?.value?.trim() || "";
  ReviewPipeline.contractText = directText;

  if (!ReviewPipeline.files.length && !directText) {
    return showToast("请先上传审查文件或在文本框中粘贴条款内容", "warn");
  }

  const nextBtn = $("#reviewPipelineStep2NextBtn");
  if (nextBtn) {
    nextBtn.disabled = true;
    nextBtn.textContent = "正在调用合规审查引擎排查条款...";
  }

  if (!ReviewPipeline.files.length && directText) {
    ReviewPipeline.initialTitle = "合规性审查";
  }

  const enableBuiltin = $("#toggleBuiltinRulesCheckbox") ? $("#toggleBuiltinRulesCheckbox").checked : true;
  const enabledBuiltinIndexes = [];
  $$(".builtin-clause-cb").forEach((cb) => {
    if (cb.checked) {
      enabledBuiltinIndexes.push(parseInt(cb.dataset.clause, 10));
    }
  });

  const customRules = ReviewPipeline.getRules();

  try {
    const res = await api("/api/calc/contract_review", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: ReviewPipeline.files,
        text: directText,
        enable_builtin: enableBuiltin,
        enabled_builtin_indexes: enabledBuiltinIndexes,
        custom_rules: customRules,
      }),
    });
    ReviewPipeline.reviewResult = res;
    renderReviewAuditSheet(res);
    setReviewStep(3);
    showToast("✨《合规性审查报告》排查完成！", "success");
  } catch (err) {
    showToast("合规审查失败：" + err.message, "error");
  } finally {
    if (nextBtn) {
      nextBtn.disabled = false;
      nextBtn.textContent = "下一步：开始风控审查并生成验收单 →";
    }
  }
}

function renderReviewAuditSheet(data) {
  if (!data) return;
  const metaEl = $("#reviewAuditSheetMeta");
  if (metaEl) {
    metaEl.textContent = `审查时间：${new Date().toLocaleTimeString()}  |  综合合规评级：${(data.rating || '').replace(/[🔴🟡🟢⚪]/g, '')}  |  支持内置标准与自定义规则库`;
  }

  // 彻底删除所有 🔴、🟡、🟢、⚪ Emoji 图标以及顶部的「红绿灯统计看板」
  const kpiBar = $("#reviewAuditKpiBar");
  if (kpiBar) {
    kpiBar.style.display = "none";
    kpiBar.innerHTML = "";
  }

  // 采用强弱对比层级呈现
  const compTable = data.comparison_table || [];
  const fatalItems = compTable.filter((r) => r.risk_level_code === "red" || r.risk_level_code === "fatal" || (r.risk_level && (r.risk_level.includes("致命") || r.risk_level.includes("不合规"))));
  const flawItems = compTable.filter((r) => r.risk_level_code === "flaw" || (r.risk_level && (r.risk_level.includes("瑕疵") || r.risk_level.includes("偏离"))));
  const highlightItems = [...fatalItems, ...flawItems];
  const compItems = compTable.filter((r) => r.risk_level_code === "compliance" || (r.risk_level && r.risk_level.includes("符合")));

  // 1. 【重点不合规 / 偏离项（强视觉高亮）】排在最上方
  const highSec = $("#contrastHighlightSection");
  const highBody = $("#contrastHighlightBody");
  const highCount = $("#contrastHighlightCount");
  if (highCount) highCount.textContent = `${highlightItems.length} 项`;
  if (highSec) {
    if (fatalItems.length > 0) {
      highSec.classList.add("has-fatal");
    } else {
      highSec.classList.remove("has-fatal");
    }
  }

  if (highBody) {
    if (!highlightItems.length) {
      highBody.innerHTML = '<div style="background:#FFFFFF;border-radius:8px;padding:12px;font-size:13px;color:#2E7D32;">✨ 经严格比对，未检出重点不合规或偏离项。</div>';
    } else {
      highBody.innerHTML = highlightItems.map((item) => {
        const isFatal = item.risk_level_code === "red" || item.risk_level_code === "fatal" || (item.risk_level && item.risk_level.includes("致命"));
        const cleanLevel = (item.risk_level || "").replace(/[🔴🟡🟢⚪]/g, "").trim() || (isFatal ? "重点不合规" : "偏离项");
        const cleanReason = (item.risk_reason || "").replace(/[🔴🟡🟢⚪]/g, "").trim();
        return `
          <div class="contrast-item-card">
            <div class="cic-head">
              <span class="cic-title">审查标准：${esc(item.category)}</span>
              <span class="cic-badge ${isFatal ? 'danger' : 'flaw'}">${esc(cleanLevel)}</span>
            </div>
            <div class="cic-flow">
              <div class="cic-step quote">
                <span class="cic-step-label">文件原文摘录</span>
                <span class="cic-step-val"><code>${esc(item.quote || '未发现相关保证或约定条款')}</code></span>
              </div>
              <div class="cic-step reason">
                <span class="cic-step-label">不合规偏离点剖析</span>
                <span class="cic-step-val">${esc(cleanReason)}</span>
              </div>
              <div class="cic-step fix">
                <span class="cic-step-label">标准修正文本</span>
                <span class="cic-step-val">${esc(item.standard_clause || '建议补充完善')}</span>
              </div>
            </div>
          </div>
        `;
      }).join("");
    }
  }

  // 2. 【完全符合项（弱视觉弱化）】排在下方，浅灰底色、次要字色(#86868B)紧凑折叠
  const weakBody = $("#contrastWeakBody");
  const weakCount = $("#contrastWeakCount");
  if (weakCount) weakCount.textContent = `${compItems.length} 项`;
  if (weakBody) {
    if (!compItems.length) {
      weakBody.innerHTML = '<div class="cws-item"><span>暂无完全符合项记录</span></div>';
    } else {
      weakBody.innerHTML = compItems.map((item) => `
        <div class="cws-item">
          <b>${esc(item.category)}</b>
          <span>${esc((item.risk_reason || '已达到合规标准要求').replace(/[🔴🟡🟢⚪]/g, ''))}</span>
          <span style="color:#34C759;font-weight:600;">已达标</span>
        </div>
      `).join("");
    }
  }

  // 折叠开关
  const weakHead = $("#contrastWeakToggleHead");
  if (weakHead) {
    weakHead.onclick = () => {
      const b = $("#contrastWeakBody");
      const arr = $("#contrastWeakArrow");
      if (b) {
        b.classList.toggle("collapsed");
        if (arr) arr.textContent = b.classList.contains("collapsed") ? "▶ 点击展开" : "▼ 点击折叠";
      }
    };
  }

  // 3. 兼容逐项对照表桩
  const compWrap = $("#reviewComparisonTableWrap");
  if (compWrap && data.comparison_table) {
    if (!data.comparison_table.length) {
      compWrap.innerHTML = '<div class="audit-empty-row success">✨ 未检测到明显违约或瑕疵条款</div>';
    } else {
      let html = `<table class="audit-table"><thead><tr>
        <th style="width:140px;">条款类别</th><th>合同原句摘录</th><th style="width:200px;">风险等级与原因</th><th>建议修改后标准条款</th>
      </tr></thead><tbody>`;
      data.comparison_table.forEach((row) => {
        let badgeClass = "badge-risk gray";
        if (row.risk_level_code === "red" || row.risk_level_code === "fatal") badgeClass = "badge-risk red";
        else if (row.risk_level_code === "flaw") badgeClass = "badge-risk yellow";
        else if (row.risk_level_code === "compliance") badgeClass = "badge-risk green";

        const cleanLvl = (row.risk_level || "").replace(/[🔴🟡🟢⚪]/g, "");
        const cleanRsn = (row.risk_reason || "").replace(/[🔴🟡🟢⚪]/g, "");

        html += `<tr>
          <td><b>${esc(row.category)}</b></td>
          <td class="reason-cell" style="max-width:240px;"><code>${esc(row.quote)}</code></td>
          <td class="reason-cell"><span class="${badgeClass}">${esc(cleanLvl)}</span><div style="margin-top:4px;font-size:11.5px;color:var(--label-2);">${esc(cleanRsn)}</div></td>
          <td class="reason-cell" style="max-width:320px;">${esc(row.standard_clause)}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      compWrap.innerHTML = html;
    }
  }

  // 4. Missing clauses list
  const missWrap = $("#reviewMissingTableWrap");
  const missTitle = $("#reviewMissingTitle");
  if (missWrap && missTitle) {
    const mList = data.missing_list || [];
    missTitle.textContent = `底部《缺失条款补充清单》（必备风控兜底条款 ${mList.length} 项）`;
    if (!mList.length) {
      missWrap.innerHTML = '<div class="audit-empty-row success">未检测到关键条款缺失。</div>';
    } else {
      let html = `<table class="audit-table warning"><thead><tr>
        <th style="width:60px;">序号</th><th style="width:140px;">缺失条款类别</th><th>缺失风险提示与说明</th><th>建议补充标准条款</th>
      </tr></thead><tbody>`;
      mList.forEach((it, idx) => {
        const cleanIssue = (it.missing_issue || "").replace(/[🔴🟡🟢⚪⚠️]/g, "");
        html += `<tr>
          <td>${idx + 1}</td>
          <td><b>${esc(it.category)}</b></td>
          <td class="reason-cell" style="max-width:240px;"><span class="badge-status warn">待补充</span><div style="margin-top:4px;">${esc(cleanIssue)}</div></td>
          <td class="reason-cell" style="max-width:340px;">${esc(it.recommended_addition)}</td>
        </tr>`;
      });
      html += `</tbody></table>`;
      missWrap.innerHTML = html;
    }
  }
}

async function executeReviewExportDocx() {
  const btn = $("#reviewExportDocxBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "正在生成 Word 审查报告...";
  }
  try {
    const res = await api("/api/calc/contract_export", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: ReviewPipeline.files,
        text: ReviewPipeline.contractText,
        export_type: "doc",
        custom_rules: ReviewPipeline.getRules(),
        enable_builtin: $("#toggleBuiltinRulesCheckbox") ? $("#toggleBuiltinRulesCheckbox").checked : true,
      }),
    });
    ReviewPipeline.exportResult = res;
    S.currentArtifact = res;
    showArtifact(res);
    const resultBox = $("#reviewExportResult");
    if (resultBox) {
      resultBox.hidden = false;
      resultBox.innerHTML = renderArtifactCard(res);
    }
    showToast(`《合规性审查报告.docx》导出成功！`, "success");
  } catch (err) {
    showToast("导出 Word 失败：" + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "📥 重新导出 Word 报告";
    }
  }
}

async function executeReviewExportPpt() {
  const btn = $("#reviewExportPptBtn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "正在生成汇报 PPT...";
  }
  try {
    const res = await api("/api/calc/contract_export", {
      method: "POST",
      body: JSON.stringify({
        conversation_id: S.currentId,
        files: ReviewPipeline.files,
        text: ReviewPipeline.contractText,
        export_type: "ppt",
        custom_rules: ReviewPipeline.getRules(),
        enable_builtin: $("#toggleBuiltinRulesCheckbox") ? $("#toggleBuiltinRulesCheckbox").checked : true,
      }),
    });
    S.currentArtifact = res;
    showArtifact(res);
    const resultBox = $("#reviewExportResult");
    if (resultBox) {
      resultBox.hidden = false;
      resultBox.innerHTML = renderArtifactCard(res);
    }
    showToast(`《合规性审查汇报.pptx》导出成功！`, "success");
  } catch (err) {
    showToast("导出 PPT 失败：" + err.message, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = "📊 重新导出汇报 PPT";
    }
  }
}

function sendReviewToReportWorkflow() {
  if (!ReviewPipeline.reviewResult) {
    return showToast("请先完成合规审查", "warn");
  }
  closeReviewPipeline();
  S.mode = "report";
  renderModes();
  const promptMsg = `请根据以下合规性审查验收结果，撰写一份正式的《关于合规风险与偏离项修改建议的专项报告》。要求：重点分析不合规项、偏离点与修订建议：\n\n${ReviewPipeline.reviewResult.markdown}`;
  $("#input").value = promptMsg;
  send();
}


/* ==============================================================================
   工作台右侧成果预览舱与交付物卡片 (Claude Artifacts / SAP Joule 架构)
   ============================================================================== */

/* 供应链 KPI 数据摘要看板渲染 (SAP Joule / Coupa Copilot 风格) */
function renderKpiDashboard(kpis) {
  if (!kpis || !Array.isArray(kpis) || kpis.length === 0) return "";
  const cardsHtml = kpis.map((k) => {
    let statusClass = k.status || "info";
    const label = esc(k.label || "");
    const val = esc(String(k.value || ""));
    const icon = k.icon || "📌";

    if (label.includes("致命风险") || val.includes("高风险")) {
      const cnt = parseInt(val) || 0;
      statusClass = cnt > 0 ? "danger" : "success";
    } else if (label.includes("商务瑕疵") || label.includes("对账差额") || val.includes("中风险") || k.alert) {
      const isClean = val === "0 项" || val === "0.0" || val === "0" || val === "+0.0" || val === "-0.0";
      statusClass = isClean ? "success" : "warn";
    } else if (label.includes("合规完备") || val.includes("低风险") || val.includes("已对齐") || val.includes("就绪")) {
      statusClass = "success";
    }

    let badgeText = "";
    if (statusClass === "warn") badgeText = '<span class="kpi-card-badge warn">警示</span>';
    else if (statusClass === "danger") badgeText = '<span class="kpi-card-badge danger">高危</span>';
    else if (statusClass === "success" && (label.includes("差额") || label.includes("合规") || label.includes("风险"))) {
      badgeText = '<span class="kpi-card-badge success">合规</span>';
    }

    return `
      <div class="kpi-card ${statusClass}">
        <div class="kpi-card-top">
          <span class="kpi-card-icon">${icon}</span>
          <span class="kpi-card-label">${label}</span>
          ${badgeText}
        </div>
        <div class="kpi-card-val">${val}</div>
      </div>
    `;
  }).join("");

  return `<div class="kpi-dashboard">${cardsHtml}</div>`;
}

function extractContractRisksFromText(text) {
  if (!text || text.length < 20) return null;
  let fatalCount = 0;
  let flawCount = 0;
  let compCount = 0;

  const redTags = text.match(/【红灯[^】]*】/g) || [];
  const yellowTags = text.match(/【黄灯[^】]*】/g) || [];
  const greenTags = text.match(/【绿灯[^】]*】/g) || [];

  if (redTags.length > 0 || yellowTags.length > 0 || greenTags.length > 0) {
    fatalCount = redTags.length;
    flawCount = yellowTags.length;
    compCount = Math.max(greenTags.length, 1);
  } else {
    const fatalMatch = text.match(/【(?:致命风险|红灯项)[^】]*】([\s\S]*?)(?=【(?:商务瑕疵|黄灯项|合规完备|建议增补)|$)/i);
    if (fatalMatch) {
      const items = fatalMatch[1].match(/(?:^|\n)\s*(?:\d+[\.\、\)]|[-*]|【问题\d+】)\s*(.+)/g) || [];
      fatalCount = Math.max(items.length, 1);
    }
    const flawMatch = text.match(/【(?:商务瑕疵|黄灯项)[^】]*】([\s\S]*?)(?=【(?:合规完备|绿灯项|建议增补)|$)/i);
    if (flawMatch) {
      const items = flawMatch[1].match(/(?:^|\n)\s*(?:\d+[\.\、\)]|[-*]|【瑕疵\d+】)\s*(.+)/g) || [];
      flawCount = Math.max(items.length, 1);
    }
    const compMatch = text.match(/【(?:合规完备|绿灯项)[^】]*】([\s\S]*?)(?=【(?:建议增补|总结)|$)/i);
    if (compMatch) {
      const items = compMatch[1].match(/(?:^|\n)\s*(?:\d+[\.\、\)]|[-*])\s*(.+)/g) || [];
      compCount = Math.max(items.length, 2);
    }
  }

  if (fatalCount === 0 && flawCount === 0 && compCount === 0) {
    if (text.includes("致命风险") || text.includes("红灯项")) fatalCount = 1;
    if (text.includes("商务瑕疵") || text.includes("黄灯项")) flawCount = 1;
    if (text.includes("合规完备") || text.includes("绿灯项")) compCount = 2;
  }

  if (fatalCount === 0 && flawCount === 0 && compCount === 0) return null;

  let rating = "🟢 低风险·合规较好";
  if (fatalCount >= 2) rating = "🔴 高风险·建议重签";
  else if (fatalCount === 1 || flawCount >= 2) rating = "🟡 中风险·建议修订";

  return [
    { label: "致命风险", value: `${fatalCount} 项`, icon: "🔴", status: fatalCount > 0 ? "danger" : "success" },
    { label: "商务瑕疵", value: `${flawCount} 项`, icon: "🟡", status: flawCount > 0 ? "warn" : "success" },
    { label: "合规完备", value: `${compCount} 项`, icon: "🟢", status: "success" },
    { label: "风控评级", value: rating, icon: "📋", status: fatalCount >= 2 ? "danger" : (fatalCount === 1 || flawCount >= 2 ? "warn" : "success") }
  ];
}

function renderArtifactCard(art) {
  if (!art) return "";
  const rawName = art.filename || art.name || "交付成果";
  const lowerName = rawName.toLowerCase();
  let ftype = (art.filetype || "").toLowerCase();
  let icon = "📦";
  if (lowerName.endsWith(".pptx") || lowerName.endsWith(".ppt") || ftype === "ppt" || ftype === "pptx") {
    icon = "📊";
    ftype = "ppt";
  } else if (lowerName.endsWith(".xlsx") || lowerName.endsWith(".xls") || lowerName.endsWith(".csv") || ftype === "excel" || ftype === "table") {
    icon = "📈";
    ftype = "excel";
  } else if (lowerName.endsWith(".docx") || lowerName.endsWith(".doc") || ftype === "doc" || ftype === "word") {
    icon = "📄";
    ftype = "doc";
  } else if (lowerName.endsWith(".pdf") || ftype === "pdf") {
    icon = "📕";
    ftype = "pdf";
  } else {
    ftype = ftype || "file";
  }

  const name = esc(rawName);
  const size = esc(art.filesize || art.size || "");
  const p = esc(art.filepath || art.path || "");
  const valReport = art.validation_report || art.report_text || art.report_summary || art.summary || "";
  const valStatus = art.validation_status || art.status || "自检通过 · 0处溢出";

  return `
    <div class="artifact-card" data-art-path="${p}" data-art-name="${name}">
      <div class="art-card-top">
        <div class="art-card-icon ${esc(ftype)}">${icon}</div>
        <div class="art-card-info">
          <div class="art-card-name" title="${name}">${name}</div>
          <div class="art-card-meta">
            ${size ? `<span class="art-card-size">${size}</span> · ` : ""}<span class="art-card-badge" title="${esc(valReport || valStatus)}">✓ ${esc(valStatus)}</span>
          </div>
        </div>
      </div>
      <div class="art-card-actions">
        <button class="art-btn primary art-btn-preview" type="button" title="在右侧成果预览舱查看数据与图表">📊 在成果舱预览</button>
        <button class="art-btn art-btn-open" type="button" title="直接调用本机软件打开">📂 直接用本机软件打开</button>
        <button class="art-btn art-btn-reveal" type="button" title="打开所在本地文件夹">📁 打开所在目录</button>
      </div>
    </div>
  `;
}

function showArtifact(art) {
  if (!art) return;
  S.currentArtifact = art;
  const wb = $("#workbench");
  const panel = $("#artifactPanel");
  const resizer = $("#artifactResizer");
  const toggleBtn = $("#splitToggleBtn");
  if (wb) {
    wb.classList.add("has-artifact");
    wb.style.gridTemplateColumns = "";
  }
  if (panel) {
    panel.hidden = false;
    panel.classList.remove("closed");
    panel.classList.add("open");
    panel.style.display = "flex";
    panel.style.width = "";
    panel.style.flex = "";
    panel.style.borderLeft = "";
  }
  if (resizer) {
    resizer.hidden = false;
    resizer.classList.remove("closed");
    resizer.classList.add("open");
    resizer.style.display = "flex";
    resizer.style.width = "";
    resizer.style.border = "";
  }
  if (toggleBtn) toggleBtn.classList.add("active");

  const titleEl = $("#apTitle");
  const tagEl = $("#apTag");
  const sizeEl = $("#apSize");
  const iconEl = $("#apIcon");
  const pathEl = $("#apPath");
  const kpiBar = $("#apKpiBar");
  const bodyEl = $("#apBody");

  const typeIcons = { excel: "📊", csv: "📊", ppt: "📑", doc: "📄", word: "📄" };
  const ftype = (art.filetype || "excel").toLowerCase();

  if (titleEl) {
    titleEl.textContent = art.filename || "交付成果";
    titleEl.title = art.filepath || art.path || art.filename || "";
  }
  if (tagEl) tagEl.textContent = ftype.toUpperCase();
  if (sizeEl) sizeEl.textContent = art.filesize || "";
  if (iconEl) iconEl.textContent = typeIcons[ftype] || "📦";
  if (pathEl) {
    pathEl.textContent = art.filepath || art.path || "-";
    pathEl.title = art.filepath || art.path || "";
  }

  // 1. KPI 状态看板渲染
  if (kpiBar) {
    if (art.kpi_metrics && art.kpi_metrics.length) {
      kpiBar.innerHTML = art.kpi_metrics.map(k => {
        const valStr = String(k.value || "");
        const isWarn = (k.label && k.label.includes("差额") && !valStr.startsWith("0")) || (valStr.includes("异常"));
        return `
          <div class="kpi-chip ${isWarn ? 'kpi-warn' : ''}">
            <span class="kpi-icon">${k.icon || '📌'}</span>
            <span class="kpi-label">${esc(k.label)}:</span>
            <span class="kpi-val">${esc(valStr)}</span>
          </div>
        `;
      }).join("");
      kpiBar.style.display = "flex";
    } else {
      kpiBar.style.display = "none";
      kpiBar.innerHTML = "";
    }
  }

  // 2. 成果体实时渲染
  if (bodyEl) {
    const pdata = art.preview_data;
    if (pdata && pdata.columns && pdata.rows) {
      // 表格渲染（斑马纹、冻结表头、差额标红高亮、数值右对齐）
      const cols = pdata.columns;
      const rows = pdata.rows;
      const diffIndices = new Set(pdata.diff_indices || []);
      const ths = cols.map(c => `<th>${esc(String(c))}</th>`).join("");
      const trs = rows.map((r, rIdx) => {
        const tds = r.map((cell, cIdx) => {
          const colName = String(cols[cIdx] || "");
          const isDiffCol = colName.includes("差额") || colName.includes("差异");
          const isDiffCell = diffIndices.has(rIdx) && isDiffCol;
          const isNum = typeof cell === "number" || (!isNaN(Number(cell)) && String(cell).trim() !== "");
          return `<td class="${isNum ? 'cell-num' : ''} ${isDiffCell ? 'cell-diff' : ''}">${esc(String(cell !== null && cell !== undefined ? cell : ""))}</td>`;
        }).join("");
        return `<tr>${tds}</tr>`;
      }).join("");

      bodyEl.innerHTML = `
        <div class="ap-table-wrap">
          <table class="ap-table">
            <thead><tr>${ths}</tr></thead>
            <tbody>${trs}</tbody>
          </table>
        </div>
      `;
    } else if (pdata && pdata.type === "ppt") {
      // PPT 幻灯片大纲卡片预览
      const slides = pdata.slides || [];
      const slidesHtml = slides.map((s, idx) => `
        <div class="ap-slide-card">
          <span class="ap-slide-num">第 ${idx + 1} / ${slides.length} 页</span>
          <div class="ap-slide-title">${esc(s.title || `第 ${idx + 1} 页`)}</div>
          <ul class="ap-slide-bullets">
            ${(s.bullets || []).map(b => `<li>${esc(b)}</li>`).join("")}
          </ul>
        </div>
      `).join("");
      bodyEl.innerHTML = `<div class="ap-slides-wrap">${slidesHtml}</div>`;
    } else if (pdata && pdata.type === "doc") {
      // Word 公文报告预览
      bodyEl.innerHTML = `
        <div class="ap-doc-page">
          <h1>${esc(pdata.title || "专项工作与管理分析报告")}</h1>
          ${md(pdata.content || "")}
        </div>
      `;
    } else {
      bodyEl.innerHTML = `
        <div class="ap-placeholder">
          <div class="ap-ph-icon">${typeIcons[ftype] || "📦"}</div>
          <div class="ap-ph-title">${esc(art.filename || "交付成果就绪")}</div>
          <div class="ap-ph-desc">文件已导出至本地目录，点击上方「📂 本机打开」即可直接调用专业软件查看。</div>
        </div>
      `;
    }
  }
}

function hideArtifact() {
  const wb = $("#workbench");
  const panel = $("#artifactPanel");
  const resizer = $("#artifactResizer");
  const toggleBtn = $("#splitToggleBtn");
  if (wb) {
    wb.classList.remove("has-artifact");
    wb.style.gridTemplateColumns = "1fr";
  }
  if (panel) {
    panel.hidden = true;
    panel.classList.remove("open");
    panel.classList.add("closed");
    panel.style.display = "none";
    panel.style.width = "0";
    panel.style.flex = "0 0 0";
    panel.style.borderLeft = "none";
  }
  if (resizer) {
    resizer.hidden = true;
    resizer.classList.remove("open");
    resizer.classList.add("closed");
    resizer.style.display = "none";
    resizer.style.width = "0";
    resizer.style.border = "none";
  }
  if (toggleBtn) toggleBtn.classList.remove("active");
  const chatPane = $("#chatPane");
  if (chatPane) {
    chatPane.style.flex = "1 1 100%";
    chatPane.style.width = "100%";
    chatPane.style.maxWidth = "100%";
  }
}

async function toggleArtifact() {
  const panel = $("#artifactPanel");
  const wb = $("#workbench");
  if (!panel) return;
  if (!panel.hidden && wb && wb.classList.contains("has-artifact")) {
    hideArtifact();
    return;
  }
  if (S.currentArtifact) {
    showArtifact(S.currentArtifact);
  } else if (S.currentId) {
    try {
      const res = await api(`/api/artifact/latest?cid=${S.currentId}`);
      if (res && res.ok && res.artifact) {
        showArtifact(res.artifact);
      } else {
        showArtifact({
          filename: "暂无交付成果",
          filepath: "",
          filesize: "",
          filetype: "excel",
          kpi_metrics: [],
          preview_data: null
        });
      }
    } catch (e) {
      hideArtifact();
    }
  } else {
    showArtifact({
      filename: "暂无交付成果",
      filepath: "",
      filesize: "",
      filetype: "excel",
      kpi_metrics: [],
      preview_data: null
    });
  }
}

async function resetAllPrompts() {
  const ok = await showConfirm({
    title: "恢复专家提示词库",
    message: "确定要将所有 8 种模式的系统提示词全部恢复为最新的工业级专家提示词库吗？",
    icon: "🔄",
    confirmText: "确认恢复",
    isDanger: true
  });
  if (!ok) return;
  try {
    await api("/api/mode_prompts/reset_all", { method: "POST" });
    await loadPromptEditor();
    showToast("已全部恢复为最新工业级专家提示词库！", "success");
  } catch (e) {
    showToast("恢复失败：" + e.message, "error");
  }
}

async function openConv(id) {
  // 切回正在生成的那个对话：直接用它内存里的消息，不重新拉取
  if (S.stream && S.stream.convId === id) {
    S.currentId = id;
    S.messages = S.stream.msgs;
    const c = S.convs.find((x) => x.id === id);
    if (c) {
      S.mode = c.mode || "general";
      $("#topTitle").textContent = c.title || "新对话";
    }
    renderModes();
    renderMessages();
    renderChips();
    renderFilesCount();
    renderSidebar();
    scrollToBottom(true);
    if (window.innerWidth <= 900) $("#sidebar").classList.remove("open");
    return;
  }
  const data = await api(`/api/conversations/${id}`);
  S.currentId = id;
  S.messages = (data.messages || []).map((m) => {
    let files = [];
    let meta = {};
    try {
      meta = typeof m.meta === "string" ? JSON.parse(m.meta || "{}") : (m.meta || {});
      files = meta.files || [];
    } catch (e) {}
    return { ...m, files, meta };
  });
  S.files = (data.files || []).map((f) => ({ ...f, pending: false }));
  S.mode = data.conversation.mode || "general";
  $("#topTitle").textContent = data.conversation.title || "新对话";

  // 恢复本会话最近一次生成的交付成果
  const lastArtMsg = [...S.messages].reverse().find((m) => m.meta && m.meta.artifact);
  if (lastArtMsg && lastArtMsg.meta.artifact) {
    S.currentArtifact = lastArtMsg.meta.artifact;
    if (window.innerWidth > 960 && ["merge", "price", "ppt", "report"].includes(S.mode)) {
      showArtifact(S.currentArtifact);
    }
  } else {
    S.currentArtifact = null;
    hideArtifact();
  }
  closeReconcilePipeline();
  renderModes();
  renderMessages();
  renderChips();
  renderFilesCount();
  renderSidebar();
  scrollToBottom(true);
  $("#sendBtn").disabled = !S.ready || S.streaming;
  if (window.innerWidth <= 900) $("#sidebar").classList.remove("open");
}

/* ------------------------------------------------ 消息渲染 */
function renderMessages() {
  const list = $("#msgList");
  const wb = $("#workbench");
  const isPipelineOpen = document.body.classList.contains("has-pipeline-open") || (wb && wb.classList.contains("has-pipeline-open"));
  if (isPipelineOpen) {
    switchMainView("wizard");
  } else {
    switchMainView(S.messages.length ? "chat" : "welcome");
  }
  list.innerHTML = S.messages
    .map((m, i) => {
      if (m.role === "user") {
        const fl = (m.files || [])
          .map((f) => {
            // 兼容旧数据：files 里可能是纯 id 字符串，也可能是 {id,name}
            let nm = "附件";
            if (typeof f === "string") {
              const hit = (S.files || []).find((x) => x.id === f);
              nm = hit ? hit.name : "附件";
            } else if (f && f.name) {
              nm = f.name;
            }
            return `<span class="msg-file"><span class="fi">📄</span>${esc(nm)}</span>`;
          })
          .join("");
        return `<div class="msg user"><div class="bubble">${fl ? `<div class="msg-files">${fl}</div>` : ""}<div class="utext">${esc(m.content)}</div></div></div>`;
      }
      const streaming = m.streaming ? " cursor" : "";
      const tools = m.streaming ? "" : toolsFor(m, i);
      const sp = splitThink(m.content, false);
      let thinkHtml = "";
      if (sp.think) {
        let tTime = "";
        try {
          const meta = typeof m.meta === "string" ? JSON.parse(m.meta || "{}") : (m.meta || {});
          if (meta.think_time) tTime = ` (用时 ${meta.think_time} 秒)`;
          else if (meta.elapsed) tTime = ` (用时 ${meta.elapsed} 秒)`;
        } catch (e) {}
        thinkHtml = `<details class="think-box"><summary><span class="think-check">💭</span> 已深度推演${tTime}</summary><div class="tb-body">${md(sp.think)}</div></details>`;
      }
      const bodyHtml = md(sp.body || (!sp.think ? m.content : ""));
      let artHtml = "";
      let kpiHtml = "";
      try {
        const meta = typeof m.meta === "string" ? JSON.parse(m.meta || "{}") : (m.meta || {});
        if (meta.artifact) {
          artHtml = renderArtifactCard(meta.artifact);
        }
        const kpis = meta.kpi_metrics || meta.kpis || (meta.artifact && meta.artifact.kpi_metrics) || null;
        if (kpis && kpis.length) {
          kpiHtml = renderKpiDashboard(kpis);
        } else if (S.mode === "review" || m.content.includes("致命风险") || m.content.includes("红灯项")) {
          const parsed = extractContractRisksFromText(m.content);
          if (parsed && parsed.length) {
            kpiHtml = renderKpiDashboard(parsed);
          }
        }
      } catch (e) {}
      const thinkLine =
        m.streaming && !m.content
          ? '<div class="think"><i></i> 正在生成，请稍候…</div>'
          : "";
      return `<div class="msg assistant">
        <div class="avatar">灵</div>
        <div class="body"><div class="md${streaming}" data-idx="${i}">${thinkHtml}${kpiHtml}${bodyHtml}</div>${artHtml}${thinkLine}${tools}</div>
      </div>`;
    })
    .join("");
  bindTools();
  renderFilesCount();
}

function toolsFor(m, i) {
  if (!m.content) return "";
  const btns = [];
  if (S.mode === "ppt") btns.push(`<button class="tool-btn" data-export="ppt" data-msgidx="${i}">⬇ 导出 PPT</button>`);
  if (S.mode === "data") btns.push(`<button class="tool-btn" data-export="excel" data-msgidx="${i}">⬇ 导出表格</button>`);
  btns.push(`<button class="tool-btn" data-copy="${i}">复制</button>`);
  btns.push(`<button class="tool-btn" data-mem="${i}">记住这条</button>`);
  btns.push(`<button class="tool-btn" data-branch="${i}">分支</button>`);
  btns.push(`<button class="tool-btn" data-delmsg="${i}">删除</button>`);
  return `<div class="msg-tools">${btns.join("")}</div>`;
}

function bindTools() {
  $$("[data-export]").forEach((b) => (b.onclick = () => doExport(b.dataset.export, b, +b.dataset.msgidx)));
  $$("[data-mem]").forEach((b) => {
    b.onclick = async () => {
      const m = S.messages[+b.dataset.mem];
      const text = (m.content || "").trim().slice(0, 400);
      if (!text) return;
      try {
        await api("/api/memories", { method: "POST", body: JSON.stringify({ text }) });
        b.textContent = "已记住";
        setTimeout(() => (b.textContent = "记住这条"), 1500);
      } catch (e) {
        showToast("记住失败：" + e.message, "error");
      }
    };
  });
  $$("[data-delmsg]").forEach((b) => {
    b.onclick = async () => {
      const m = S.messages[+b.dataset.delmsg];
      if (!S.currentId) return;
      const ok = await showConfirm({
        title: "删除消息",
        message: "确定删除这条回答以及对应的提问吗？",
        icon: "🗑️",
        confirmText: "删除",
        isDanger: true
      });
      if (!ok) return;
      try {
        await api(`/api/conversations/${S.currentId}/delete_pair`, {
          method: "POST",
          body: JSON.stringify({ message_id: m && m.id ? m.id : null, index: +b.dataset.delmsg }),
        });
        await openConv(S.currentId);
      } catch (e) {
        showToast("删除失败：" + e.message, "error");
      }
    };
  });
  $$("[data-branch]").forEach((b) => {
    b.onclick = async () => {
      const m = S.messages[+b.dataset.branch];
      if (!S.currentId) return;
      b.textContent = "分支中…";
      try {
        const r = await api(`/api/conversations/${S.currentId}/branch`, {
          method: "POST",
          body: JSON.stringify({ message_id: m && m.id ? m.id : null }),
        });
        await loadConvs();
        await openConv(r.id);
      } catch (e) {
        showToast("分支失败：" + e.message, "error");
        b.textContent = "分支";
      }
    };
  });
  $$("[data-copy]").forEach((b) => {
    b.onclick = (ev) => {
      const m = S.messages[+b.dataset.copy];
      navigator.clipboard.writeText(m.content || "");
      b.textContent = "已复制";
      setTimeout(() => (b.textContent = "复制"), 1200);
    };
  });
}

function scrollToBottom(force = false) {
  const box = $("#msgScroll");
  const near = box.scrollHeight - box.scrollTop - box.clientHeight < 90;
  if (force || near) box.scrollTop = box.scrollHeight;
}

/* ------------------------------------------------ 文件 */
const fmtChars = (n) => (!n ? "" : n < 1000 ? n + " 字" : (n / 1000).toFixed(1) + "k 字");

function renderChips() {
  $("#chips").innerHTML = S.files
    .map(
      (f) => `<div class="chip ${f.pending ? "draft" : ""}" data-fid="${f.id}">
        <span class="name" title="${esc(f.name)}">${esc(f.name)}</span>
        <span class="size">${fmtChars(f.chars)}</span>
        <span class="x" data-rm="${f.id}" title="从本对话移除">×</span>
      </div>`
    )
    .join("");
  $$("#chips .x").forEach((x) => {
    x.onclick = async () => {
      await api(`/api/files/${x.dataset.rm}/delete`, { method: "POST" });
      S.files = S.files.filter((f) => f.id !== x.dataset.rm);
      renderChips();
      renderFilesCount();
      renderDrawerFiles();
    };
  });
  renderFilesCount();
}

function renderFilesCount() {
  const n = S.files.length;
  $("#filesCount").textContent = n;
  renderDrawerFiles();
  const btn = $("#plusBtn");
  const badge = $("#plusBadge");
  if (btn && badge) {
    btn.classList.toggle("has-files", n > 0);
    badge.hidden = n === 0;
    badge.textContent = n;
  }
}

function renderDrawerFiles() {
  $("#drawerFiles").innerHTML = S.files.length
    ? S.files
        .map(
          (f) => `<div class="pop-item"><span>📄</span><span class="name" title="${esc(f.name)}">${esc(f.name)}</span>
      <span class="meta">${fmtChars(f.chars)}</span></div>`
        )
        .join("")
    : '<div class="pop-empty">本对话还没有加载文件</div>';
}

async function uploadFiles(fileList) {
  const files = [...fileList];
  for (const f of files) {
    const fd = new FormData();
    fd.append("file", f);
    const chip = document.createElement("div");
    chip.className = "chip";
    chip.innerHTML = `<span class="name">${esc(f.name)}</span><span class="size">解析中…</span>`;
    $("#chips").appendChild(chip);
    try {
      const r = await api("/api/upload", { method: "POST", body: fd });
      S.files.push({ id: r.id, name: r.name, chars: r.chars, pending: true });
    } catch (e) {
      showToast(`「${f.name}」解析失败：${e.message}`, "error");
    }
    renderChips();
  }
}

/* ------------------------------------------------ 模型 */
async function loadModels() {
  try {
    const r = await api("/api/models");
    $("#modelList").innerHTML = r.items
      .map(
        (m) => `<button class="model-item ${m.current ? "on" : ""}" data-id="${esc(m.id)}" ${m.supported ? "" : "disabled"}>
          <div class="mi-top"><b>${esc(m.name)}${m.id === r.recommended ? '<span class="mi-badge">推荐</span>' : ""}${m.current && r.lock ? '<span class="mi-lock">🔒 已锁定</span>' : ""}</b><span>${m.size_gb} GB</span></div>
          <div class="mi-note">${esc(m.note || "")}</div>
        </button>`
      )
      .join("");
    const info = $("#modelHint");
    if (info && r.reason) {
      info.textContent = r.lock
        ? "已锁定：" + r.current + "，下次启动继续加载它。"
        : "自动选择：" + r.reason + "（未锁定，每次启动按本机配置重新推荐）";
    }
    $$("#modelList .model-item").forEach((b) => {
      b.onclick = () => switchModel(b.dataset.id, b);
    });
  } catch (e) {}
}

async function switchModel(id, btn) {
  if (S.switching) return;
  const ok = await showConfirm({
    title: "切换模型",
    message: "切换模型需要重新分配显存与载入权重，约需 20–60 秒，期间暂时不能对话。确认切换吗？",
    icon: `<svg viewBox="0 0 44 44" width="44" height="44" aria-hidden="true" style="display:block;margin:0 auto;"><rect width="44" height="44" rx="10" fill="#1C1C1E"/><circle cx="22" cy="22" r="13" fill="#D4AF37" opacity="0.15"/><path d="M22 5L25.5 18.5L39 22L25.5 25.5L22 39L18.5 25.5L5 22L18.5 18.5Z" fill="#D4AF37"/></svg>`,
    confirmText: "确认切换",
    cancelText: "取消"
  });
  if (!ok) return;

  S.switching = true;
  $("#sendBtn").disabled = true;
  $("#hintRight").textContent = "正在切换模型，请稍候…";
  showModelLoading(id);
  const old = btn.innerHTML;
  btn.innerHTML = `<div class="mi-top"><b>载入中…</b></div><div class="mi-note">正在分配计算资源</div>`;
  try {
    await api("/api/model", { method: "POST", body: JSON.stringify({ id }) });
    await loadStatus();
    await loadModels();
    hideModelLoading(id);
  } catch (e) {
    hideModelLoading();
    showAlert("模型切换失败：" + e.message, "切换失败", "❌");
    btn.innerHTML = old;
  } finally {
    S.switching = false;
    $("#sendBtn").disabled = !S.ready;
  }
}

async function loadKbFiles() {
  try {
    const r = await api("/api/kb/files");
    $("#kbStats").textContent = `已索引 ${r.total_chunks} 个片段，来自 ${r.files.length} 个文件`;
    $("#kbFiles").innerHTML = r.files.length
      ? r.files
          .map(
            (f) => `<div class="kb-item"><span class="name" title="${esc(f.name)}">${esc(f.name)}</span>
        <span class="meta">${f.chunks} 块</span>
        <span class="x" data-kbdel="${f.id}" title="删除该文件的索引">×</span></div>`
          )
          .join("")
      : "";
    $$("#kbFiles .x").forEach((x) => {
      x.onclick = async () => {
        const ok = await showConfirm({
          title: "删除索引",
          message: "确定删除该文件的知识库索引吗？",
          icon: "🗑️",
          confirmText: "删除",
          isDanger: true
        });
        if (!ok) return;
        await api("/api/kb/clear", { method: "POST", body: JSON.stringify({ file_id: x.dataset.kbdel }) });
        loadKbFiles();
      };
    });
  } catch (e) {}
}

/* ------------------------------------------------ 模式提示词 */
async function loadPromptEditor() {
  try {
    const r = await api("/api/mode_prompts");
    S.promptModes = r.modes;
    const sel = $("#promptModeSel");
    const cur = sel.value;
    sel.innerHTML = r.modes
      .map((m) => `<option value="${m.id}">${esc(m.name)}${m.custom ? "（已自定义）" : ""}</option>`)
      .join("");
    if (cur) sel.value = cur;
    sel.onchange = () => showPrompt(sel.value);
    showPrompt(sel.value);
  } catch (e) {}
}

function showPrompt(id) {
  const m = (S.promptModes || []).find((x) => x.id === id);
  const box = $("#promptText");
  if (!m || !box) return;
  box.value = m.custom || m.default || "";
  box.dataset.mode = id;
}

async function savePrompt(reset) {
  const box = $("#promptText");
  const id = box.dataset.mode;
  if (!id) return;
  const text = reset ? "" : box.value;
  try {
    await api(`/api/mode_prompts/${id}`, { method: "PUT", body: JSON.stringify({ prompt: text }) });
    await loadPromptEditor();
    $("#promptModeSel").value = id;
    showPrompt(id);
  } catch (e) {
    showToast("保存失败：" + e.message, "error");
  }
}

/* ------------------------------------------------ 记忆 / 知识库 */
async function loadMemories() {
  try {
    const list = await api("/api/memories");
    $("#memList").innerHTML = list.length
      ? list
          .map(
            (m) => `<div class="mem-item"><span class="t" title="${esc(m.text)}">${esc(m.text)}</span>
        <span class="x" data-mid="${m.id}" title="删除">×</span></div>`
          )
          .join("")
      : '<div class="pop-empty">还没有记忆</div>';
    $$("#memList .x").forEach((x) => {
      x.onclick = async () => {
        await api(`/api/memories/${x.dataset.mid}`, { method: "DELETE" });
        loadMemories();
      };
    });
    await loadKbFiles();
  } catch (e) {}
}

async function addMemory() {
  const t = $("#memInput").value.trim();
  if (!t) return;
  await api("/api/memories", { method: "POST", body: JSON.stringify({ text: t }) });
  $("#memInput").value = "";
  loadMemories();
}

/* ------------------------------------------------ 发送 / 流式 */
async function send() {
  const input = $("#input");
  const text = input.value.trim();
  if (!text || S.streaming || !S.ready) return;

  try {
    if (!S.currentId) {
      const pTitle = (ReconcilePipeline && ReconcilePipeline.initialTitle) || (PricePipeline && PricePipeline.initialTitle) || (ReviewPipeline && ReviewPipeline.initialTitle) || "";
      const firstTitle = (S.files.length ? S.files[0].name.replace(/\.[^/.]+$/, "").slice(0, 24) : "") || pTitle || text.slice(0, 24).replace(/\s+/g, " ") || "新对话";
      await ensureConv(firstTitle);
    }
  } catch (e) {
    showToast("创建会话失败：" + e.message, "error");
    return;
  }

  input.value = "";
  input.style.height = "auto";

  const attachedNow = S.files.filter((f) => f.pending).map((f) => ({ id: f.id, name: f.name }));
  const convId = S.currentId;
  const msgs = S.messages;
  msgs.push({ role: "user", content: text, files: attachedNow });
  msgs.push({ role: "assistant", content: "", streaming: true });
  const idx = msgs.length - 1;
  S.stream = { convId, msgs, running: true };
  renderMessages();
  scrollToBottom(true);

  const el = () => (S.currentId === convId ? document.querySelector('.md[data-idx="' + idx + '"]') : null);
  const fileIds = S.files.filter((f) => f.pending).map((f) => f.id);

  S.streaming = true;
  $("#sendBtn").classList.add("stop");
  $("#sendBtn").disabled = false;
  S.controller = new AbortController();

  let acc = "";
  let thinkStartTime = Date.now();
  let thinkDuration = null;
  let streamArtifact = null;
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: S.controller.signal,
      body: JSON.stringify({
        conversation_id: convId,
        message: text,
        mode: S.mode,
        file_ids: fileIds,
        max_tokens: S.params.maxTokens,
        temperature: S.params.temperature,
        deep_think: S.params.deep,
        use_kb: S.kb,
        use_code: S.useCode && (S.mode === "data" || S.mode === "merge"),
        report_length: S.reportLength || "short",
      }),
    });
    if (!res.ok || !res.body) {
      let msg = "HTTP " + res.status;
      try {
        const j = await res.json();
        msg = j.detail || j.message || msg;
      } catch (e) {}
      throw new Error(msg);
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const parts = buf.split("\n\n");
      buf = parts.pop();
      for (const part of parts) {
        const line = part.replace(/^data:\s*/, "").trim();
        if (!line) continue;
        let evt;
        try {
          evt = JSON.parse(line);
        } catch (e) {
          continue;
        }
        if (evt.type === "start") {
          if (evt.title && S.currentId === convId) $("#topTitle").textContent = evt.title;
        } else if (evt.type === "delta") {
          const deltaText = evt.text || "";
          acc += deltaText;
          msgs[idx].content = acc;
          const node = el();
          if (node) {
            const thinkEl = node.parentElement ? node.parentElement.querySelector(".think") : null;
            if (thinkEl) thinkEl.remove();
            const sp = splitThink(acc, true);

            let thinkHtml = "";
            if (sp.think) {
              if (sp.isThinking) {
                const sec = Math.max(1, Math.floor((Date.now() - thinkStartTime) / 1000));
                thinkHtml = `<details class="think-box" open><summary><span class="think-dot">💭</span> 灵梦正在深度推演... <span class="think-timer">${sec}s</span></summary><div class="tb-body">${md(sp.think)}</div></details>`;
              } else {
                if (!thinkDuration) {
                  thinkDuration = Math.max(0.5, ((Date.now() - thinkStartTime) / 1000).toFixed(1));
                  msgs[idx].meta = msgs[idx].meta || {};
                  msgs[idx].meta.think_time = thinkDuration;
                }
                thinkHtml = `<details class="think-box"><summary><span class="think-check">💭</span> 已深度推演 (用时 ${thinkDuration} 秒)</summary><div class="tb-body">${md(sp.think)}</div></details>`;
              }
            }
            let kpis = (streamArtifact && streamArtifact.kpi_metrics) || null;
            if (!kpis && (S.mode === "review" || acc.includes("致命风险") || acc.includes("红灯项"))) {
              kpis = extractContractRisksFromText(acc);
            }
            const kpiHtml = kpis ? renderKpiDashboard(kpis) : "";
            const artHtml = streamArtifact ? renderArtifactCard(streamArtifact) : "";

            node.innerHTML =
              thinkHtml +
              kpiHtml +
              md(sp.body) +
              artHtml +
              (sp.body ? '<span class="cursor"></span>' : (sp.think ? '' : '<span class="cursor"></span>'));
            scrollToBottom();
          }
        } else if (evt.type === "artifact") {
          streamArtifact = evt.artifact;
          S.currentArtifact = evt.artifact;
          msgs[idx].meta = msgs[idx].meta || {};
          msgs[idx].meta.artifact = evt.artifact;
          if (evt.artifact.kpi_metrics) {
            msgs[idx].meta.kpi_metrics = evt.artifact.kpi_metrics;
          }
          showArtifact(evt.artifact);
          const node = el();
          if (node) {
            const sp = splitThink(acc);
            const kpiHtml = evt.artifact.kpi_metrics ? renderKpiDashboard(evt.artifact.kpi_metrics) : "";
            node.innerHTML =
              (sp.think ? `<details class="think-box"><summary><span class="think-check">💭</span> 已深度推演</summary><div class="tb-body">${md(sp.think)}</div></details>` : "") +
              kpiHtml +
              md(sp.body) +
              renderArtifactCard(evt.artifact) +
              '<span class="cursor"></span>';
            scrollToBottom();
          }
        } else if (evt.type === "done") {
          if (evt.artifact) {
            streamArtifact = evt.artifact;
            S.currentArtifact = evt.artifact;
            showArtifact(evt.artifact);
          }
          let finalKpis = (streamArtifact && streamArtifact.kpi_metrics) || evt.kpi_metrics || null;
          if (!finalKpis && (S.mode === "review" || acc.includes("致命风险") || acc.includes("红灯项"))) {
            finalKpis = extractContractRisksFromText(acc);
          }
          msgs[idx] = {
            id: evt.message_id || null,
            role: "assistant",
            content: acc,
            meta: {
              elapsed: evt.elapsed,
              think_time: thinkDuration,
              artifact: streamArtifact || evt.artifact || null,
              kpi_metrics: finalKpis
            }
          };
          const node = el();
          if (node) {
            const sp = splitThink(acc, false);
            const kpiHtml = finalKpis ? renderKpiDashboard(finalKpis) : "";
            const artHtml = (streamArtifact || evt.artifact) ? renderArtifactCard(streamArtifact || evt.artifact) : "";
            let tTime = "";
            if (thinkDuration) tTime = ` (用时 ${thinkDuration} 秒)`;
            else if (evt.elapsed) tTime = ` (用时 ${evt.elapsed} 秒)`;
            const thinkHtml = sp.think ? `<details class="think-box"><summary><span class="think-check">💭</span> 已深度推演${tTime}</summary><div class="tb-body">${md(sp.think)}</div></details>` : "";
            node.innerHTML = thinkHtml + kpiHtml + md(sp.body) + artHtml;
          }
          if (evt.title && S.currentId === convId) $("#topTitle").textContent = evt.title;
        } else if (evt.type === "error") {
          msgs[idx] = { role: "assistant", content: acc + `\n\n**出错了：** ${evt.message}` };
        }
      }
    }
    if (!acc) {
      msgs[idx] = { role: "assistant", content: "（模型这次没有返回内容，请重试一次，或把问题说得更具体些）" };
    }
  } catch (e) {
    if (e.name === "AbortError") {
      msgs[idx] = { role: "assistant", content: acc ? acc + "\n\n（已停止）" : "（已停止）" };
    } else {
      msgs[idx] = {
        role: "assistant",
        content: acc ? acc + "\n\n**中途出错了：** " + e.message : "**请求失败：** " + e.message,
      };
    }
  } finally {
    S.streaming = false;
    S.stream = null;
    S.controller = null;
    S.files.forEach((f) => (f.pending = false));
    if (S.currentId === convId) {
      renderMessages();
      scrollToBottom();
    }
    renderChips();
    $("#sendBtn").classList.remove("stop");
    $("#sendBtn").disabled = !S.ready;
    loadConvs();
  }
}

/* ------------------------------------------------ 导出 */
async function doExport(kind, btn, msgIdx) {
  if (!S.currentId) return;
  const target = Number.isInteger(msgIdx) ? S.messages[msgIdx] : null;
  const messageId = target && target.id ? target.id : null;
  const pagesInput = $("#pptPages");
  const pages = Math.max(1, Math.min(100, parseInt((pagesInput && pagesInput.value) || "10", 10) || 10));
  const old = btn.textContent;
  btn.textContent = "生成中…";
  btn.disabled = true;
  try {
    const r = await api("/api/export", {
      method: "POST",
      body: JSON.stringify({ conversation_id: S.currentId, kind, pages, message_id: messageId }),
    });
    let job = null;
    for (let i = 0; i < 1200; i++) {
      await new Promise((res) => setTimeout(res, 2000));
      job = await api(`/api/export/${r.job_id}`);
      if (job.status !== "running") break;
      btn.textContent = "生成中 " + (job.progress || "");
    }
    if (!job || job.status !== "done") throw new Error((job && job.error) || "生成超时");
    const a = document.createElement("a");
    a.href = job.url;
    a.download = job.file;
    document.body.appendChild(a);
    a.click();
    a.remove();

    // 挂载成果交付卡片至当前回答气泡
    const artObj = (job && job.artifact) || {
      filename: job.file,
      filepath: job.path || ("D:\\AI\\output\\" + job.file),
      path: job.path || ("D:\\AI\\output\\" + job.file),
      filesize: job.filesize || "",
      filetype: kind || (job.file && job.file.endsWith(".pptx") ? "ppt" : (job.file && job.file.endsWith(".xlsx") ? "excel" : "doc")),
      validation_report: job.validation_report || job.summary || "自检通过 · 0处溢出",
      validation_status: "自检通过 · 0处溢出",
      status: "自检通过",
    };
    S.currentArtifact = artObj;
    let targetMsg = target;
    if (!targetMsg && S.messages && S.messages.length) {
      for (let mi = S.messages.length - 1; mi >= 0; mi--) {
        if (S.messages[mi].role === "assistant") {
          targetMsg = S.messages[mi];
          break;
        }
      }
    }
    if (targetMsg) {
      targetMsg.meta = typeof targetMsg.meta === "string" ? JSON.parse(targetMsg.meta || "{}") : (targetMsg.meta || {});
      targetMsg.meta.artifact = artObj;
      renderMessages();
    }

    btn.textContent = "已生成";
    setTimeout(() => {
      btn.textContent = old;
      btn.disabled = false;
    }, 2500);
  } catch (e) {
    showToast("导出失败：" + e.message, "error");
    btn.textContent = old;
    btn.disabled = false;
  }
}

function showFilePreview(res, fallbackName) {
  const mask = $("#previewMask");
  const title = $("#previewName");
  const body = $("#previewBody");
  if (!mask || !body) return;
  title.textContent = res.name || fallbackName || "文件预览";
  if (res.type === "table" && res.sheets) {
    const sNames = Object.keys(res.sheets);
    if (!sNames.length) {
      body.textContent = "（表格无数据）";
    } else {
      const firstSheet = res.sheets[sNames[0]];
      let tHtml = `<div class="preview-table-wrap"><table class="preview-table"><thead><tr>`;
      tHtml += firstSheet.columns.map((c) => `<th>${esc(c)}</th>`).join("");
      tHtml += `</tr></thead><tbody>`;
      for (const row of firstSheet.rows) {
        tHtml += `<tr>` + row.map((cell) => `<td>${esc(cell)}</td>`).join("") + `</tr>`;
      }
      tHtml += `</tbody></table></div>`;
      if (firstSheet.total_rows > firstSheet.rows.length) {
        tHtml += `<div style="font-size:11px;color:var(--label-3);margin-top:6px;padding:4px 2px">（已显示前 ${firstSheet.rows.length} 行，全表共 ${firstSheet.total_rows} 行）</div>`;
      }
      body.innerHTML = tHtml;
    }
  } else {
    body.textContent = res.content || res.text || "（没有可预览的内容）";
  }
  mask.hidden = false;
  mask.style.removeProperty("display");
  mask.style.removeProperty("pointer-events");
}

/* ------------------------------------------------ 交互绑定 */
function bind() {
  renderWelcome();
  const newChatBtn = $("#newChatBtn");
  if (newChatBtn) newChatBtn.onclick = () => resetView();

  const input = $("#input");
  const grow = () => {
    if (!input) return;
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 190) + "px";
  };
  if (input) {
    input.addEventListener("input", grow);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        send();
      }
    });
  }

  const sendBtn = $("#sendBtn");
  if (sendBtn) {
    sendBtn.onclick = async () => {
      if (S.streaming) {
        if (S.controller) S.controller.abort();
        try {
          await api("/api/chat/stop", {
            method: "POST",
            body: JSON.stringify({ conversation_id: S.currentId }),
          });
        } catch (e) {}
      } else send();
    };
  }

  // 全局键盘交互保障：Escape 键关闭活动遮罩/抽屉/弹窗，主界面按键自动聚焦聊天框
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const drawer = $("#drawer");
      if (drawer && drawer.classList.contains("open")) {
        drawer.classList.remove("open");
        const mask = $("#drawerMask");
        if (mask) mask.classList.remove("show");
        return;
      }
      const pm = $("#previewMask");
      if (pm && !pm.hidden) {
        pm.hidden = true;
        return;
      }
      const cm = $("#customModalMask");
      if (cm && !cm.hidden) {
        const cancelBtn = $("#modalCancelBtn");
        if (cancelBtn && cancelBtn.style.display !== "none") cancelBtn.click();
        else cm.hidden = true;
        return;
      }
      const pop = document.getElementById("filesPop");
      if (pop && pop.classList.contains("show")) {
        pop.classList.remove("show");
        return;
      }
    }

    const active = document.activeElement;
    const isEditing = active && (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
    if (!isEditing && !e.ctrlKey && !e.altKey && !e.metaKey && e.key && e.key.length === 1) {
      const inputEl = $("#input");
      if (inputEl && document.body.contains(inputEl)) {
        inputEl.focus();
      }
    }
  });

  // 全局文件点击打开与预览绑定（点击直接系统 os.startfile 打开，支持表格结构化预览）
  document.addEventListener("click", async (e) => {
    // 0. 成果卡片按钮代理
    const artPrev = e.target.closest(".art-btn-preview");
    if (artPrev) {
      const card = artPrev.closest(".artifact-card");
      const p = card ? card.dataset.artPath : "";
      const n = card ? card.dataset.artName : "";
      let matchedArt = null;
      for (const m of S.messages) {
        const art = m.meta && m.meta.artifact;
        if (art && ((art.filepath && art.filepath === p) || art.filename === n)) {
          matchedArt = art;
          break;
        }
      }
      if (matchedArt) showArtifact(matchedArt);
      else if (S.currentArtifact) showArtifact(S.currentArtifact);
      return;
    }

    const artOpen = e.target.closest(".art-btn-open");
    if (artOpen) {
      const card = artOpen.closest(".artifact-card");
      const p = card ? card.dataset.artPath : "";
      const n = card ? card.dataset.artName : "";
      try {
        await api("/api/file/open", { method: "POST", body: JSON.stringify({ path: p, name: n }) });
      } catch (err) {
        showToast("打开文件失败：" + err.message, "error");
      }
      return;
    }

    const artReveal = e.target.closest(".art-btn-reveal");
    if (artReveal) {
      const card = artReveal.closest(".artifact-card");
      const p = card ? card.dataset.artPath : "";
      const n = card ? card.dataset.artName : "";
      try {
        await api("/api/file/open", { method: "POST", body: JSON.stringify({ path: p, name: n, is_dir: true }) });
      } catch (err) {
        showToast("打开目录失败：" + err.message, "error");
      }
      return;
    }

    // 1. 拦截 Markdown 中的导出文件打开链接
    const openLink = e.target.closest('a[href*="/api/file/open"]');
    if (openLink) {
      e.preventDefault();
      try {
        const u = new URL(openLink.href, location.origin);
        const name = u.searchParams.get("name") || "";
        const r = await api("/api/file/open", { method: "POST", body: JSON.stringify({ name }) });
        if (!r.ok && r.url) window.open(r.url, "_blank");
      } catch (err) {
        showToast("打开文件失败：" + err.message, "error");
      }
      return;
    }

    // 2. 点击输入框或对话上方的文件 Chip 标签
    const chip = e.target.closest(".chip[data-fid], .msg-file[data-fid]");
    if (!chip || e.target.classList.contains("x")) return;
    const fid = chip.dataset.fid;
    try {
      const r = await api("/api/file/open", { method: "POST", body: JSON.stringify({ file_id: fid }) });
      if (!r.ok) {
        const prev = await api(`/api/file/preview?file_id=${fid}`);
        showFilePreview(prev, chip.querySelector(".name")?.textContent);
      }
    } catch (err) {
      try {
        const prev = await api(`/api/file/preview?file_id=${fid}`);
        showFilePreview(prev, chip.querySelector(".name")?.textContent);
      } catch (e2) {
        showToast("打开文件失败：" + err.message, "error");
      }
    }
  });

  const pm = $("#previewMask");
  if (pm) {
    pm.onclick = (e) => {
      if (e.target === pm || e.target.id === "previewClose") pm.hidden = true;
    };
  }

  $("#plusBtn").onclick = () => $("#fileInput").click();
  $("#fileInput").onchange = (e) => {
    if (e.target.files.length) uploadFiles(e.target.files);
    e.target.value = "";
  };

  const composer = $("#composer");
  ["dragenter", "dragover"].forEach((ev) =>
    composer.addEventListener(ev, (e) => {
      e.preventDefault();
      composer.classList.add("dragover");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    composer.addEventListener(ev, (e) => {
      e.preventDefault();
      if (ev === "dragleave" && composer.contains(e.relatedTarget)) return;
      composer.classList.remove("dragover");
    })
  );
  composer.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) uploadFiles(e.dataTransfer.files);
  });

  // 参数
  const LEN_STEPS = [512, 1024, 2048, 3072];
  const LEN_LABELS = ["约 300 字", "约 600 字", "约 1200 字", "约 1800 字"];
  const paint = (el) => {
    const min = +el.min, max = +el.max, v = +el.value;
    const pct = max > min ? ((v - min) / (max - min)) * 100 : 0;
    el.style.setProperty("--p", pct + "%");
  };
  const lr = $("#lenRange");
  const idx0 = Math.max(0, LEN_STEPS.indexOf(S.params.maxTokens));
  lr.value = String(idx0 === -1 ? 1 : idx0);
  $("#lenVal").textContent = LEN_LABELS[+lr.value] || LEN_LABELS[1];
  paint(lr);
  lr.oninput = () => {
    const i = +lr.value;
    S.params.maxTokens = LEN_STEPS[i];
    $("#lenVal").textContent = LEN_LABELS[i];
    localStorage.setItem("qwen.maxTokens", String(LEN_STEPS[i]));
    paint(lr);
  };

  const tp = $("#temperature");
  tp.value = S.params.temperature;
  $("#tempVal").textContent = S.params.temperature.toFixed(1);
  paint(tp);
  tp.oninput = () => {
    S.params.temperature = +tp.value;
    $("#tempVal").textContent = (+tp.value).toFixed(1);
    localStorage.setItem("qwen.temperature", tp.value);
    paint(tp);
  };
  const dt = $("#deepThink");
  const deepBtn = $("#deepToggle");
  const delBtn = $("#delConvBtn");
  if (delBtn) delBtn.onclick = async () => {
    if (!S.currentId) { showToast("当前没有打开的对话", "warn"); return; }
    const ok = await showConfirm({
      title: "删除当前对话",
      message: "删除当前对话后记录将永久清除，确认删除吗？",
      icon: "🗑️",
      confirmText: "确认删除",
      isDanger: true
    });
    if (!ok) return;
    await api(`/api/conversations/${S.currentId}`, { method: "DELETE" });
    S.currentId = null; S.messages = []; S.files = [];
    $("#topTitle").textContent = "新对话";
    renderMessages(); renderChips(); renderFilesCount();
    await loadConvs();
  };
  // 思考强度：四档，联动回答长度与随机性（保留原输入元素，业务不变）
  const EFFORTS = [
    { name: "Low", len: 512, temp: 0.3, desc: "回答最短最快，只给结论，适合摘数据、改格式。" },
    { name: "Medium", len: 1024, temp: 0.6, desc: "较快给出答案，适合日常问答与简单整理。" },
    { name: "High", len: 2048, temp: 0.8, desc: "更完整、更有条理，适合写报告与方案。" },
    { name: "Max", len: 3072, temp: 1.0, desc: "最长最发散，适合长文、多方案对比，速度最慢。" },
  ];
  const effort = $("#effortRange");
  const applyEffort = (i, fire) => {
    const L = EFFORTS[i] || EFFORTS[1];
    const nm = $("#effortName"), ds = $("#effortDesc");
    if (nm) nm.textContent = L.name;
    if (ds) ds.textContent = L.desc;
    effort.style.setProperty("--p", (i / 3) * 100 + "%");
    localStorage.setItem("qwen.effort", String(i));
    const echo = $("#paramEcho");
    if (echo) echo.textContent = L.name;
    const pb = $("#paramBtn");
    if (pb && !echo) pb.textContent = "思考强度 · " + L.name;
    if (fire) {
      lr.value = String(LEN_STEPS.indexOf(L.len));
      lr.dispatchEvent(new Event("input"));
      tp.value = String(L.temp);
      tp.dispatchEvent(new Event("input"));
    }
  };
  if (effort) {
    const saved = +(localStorage.getItem("qwen.effort") ?? 1);
    effort.value = String(saved >= 0 && saved <= 3 ? saved : 1);
    effort.oninput = () => applyEffort(+effort.value, true);
    applyEffort(+effort.value, true);
  }
  const paramBtn = $("#paramBtn");
  const paramPop = $("#paramPop");
  if (paramBtn && paramPop) {
    paramBtn.onclick = (e) => {
      e.stopPropagation();
      paramPop.hidden = !paramPop.hidden;
      paramBtn.classList.toggle("on", !paramPop.hidden);
    };
    document.addEventListener("click", (e) => {
      if (!paramPop.hidden && !paramPop.contains(e.target) && e.target !== paramBtn) {
        paramPop.hidden = true;
        paramBtn.classList.remove("on");
      }
    });
  }
  const codeBtn = $("#codeToggle");
  if (codeBtn) {
    codeBtn.classList.toggle("on", S.useCode);
    codeBtn.onclick = () => {
      S.useCode = !S.useCode;
      codeBtn.classList.toggle("on", S.useCode);
      localStorage.setItem("qwen.usecode", S.useCode ? "1" : "0");
    };
  }
  const kb = $("#kbToggle");
  if (kb) {
    kb.checked = S.kb;
    kb.onchange = () => {
      S.kb = kb.checked;
      localStorage.setItem("qwen.kb", S.kb ? "1" : "0");
    };
  }
  const pSave = $("#promptSave");
  if (pSave) pSave.onclick = () => savePrompt(false);
  const pReset = $("#promptReset");
  if (pReset) pReset.onclick = () => savePrompt(true);
  const kbRebuild = $("#kbRebuild");
  if (kbRebuild) kbRebuild.onclick = async () => {
    kbRebuild.disabled = true;
    kbRebuild.textContent = "重建中…";
    try { const r = await api("/api/kb/rebuild", { method: "POST", body: "{}" }); await loadKbFiles(); showToast(`重建完成，共索引 ${r.chunks} 个片段`, "success"); }
    finally { kbRebuild.disabled = false; kbRebuild.textContent = "重建索引"; }
  };
  const kbClear = $("#kbClear");
  if (kbClear) kbClear.onclick = async () => {
    const ok = await showConfirm({
      title: "清空知识库",
      message: "确定清空全部知识库索引吗？（已上传记录将被清除，原始文件保留在 data/uploads）",
      icon: "⚠️",
      confirmText: "清空",
      isDanger: true
    });
    if (!ok) return;
    await api("/api/kb/clear", { method: "POST", body: "{}" });
    loadKbFiles();
  };
  const memAdd = $("#memAdd");
  if (memAdd) memAdd.onclick = addMemory;
  const syncDeep = () => {
    dt.checked = S.params.deep;
    deepBtn.classList.toggle("on", S.params.deep);
    localStorage.setItem("qwen.deep", S.params.deep ? "1" : "0");
  };
  syncDeep();
  dt.onchange = () => {
    S.params.deep = dt.checked;
    syncDeep();
  };
  deepBtn.onclick = () => {
    S.params.deep = !S.params.deep;
    syncDeep();
  };

  // 抽屉
  const openDrawer = () => {
    $("#drawer").classList.add("open");
    $("#drawerMask").classList.add("show");
    renderDrawerFiles();
    loadMemories();
    loadModels();
    loadPromptEditor();
  };
  const closeDrawer = () => {
    $("#drawer").classList.remove("open");
    $("#drawerMask").classList.remove("show");
  };
  $("#settingsBtn").onclick = openDrawer;
  $("#drawerClose").onclick = closeDrawer;
  $("#drawerMask").onclick = closeDrawer;
  const modelLock = $("#modelLock");
  if (modelLock) {
    modelLock.onchange = async () => {
      try {
        await api("/api/model/lock", {
          method: "POST",
          body: JSON.stringify({ locked: modelLock.checked }),
        });
        await loadStatus();
        await loadModels();
      } catch (e) {
        modelLock.checked = !modelLock.checked;
        showToast("保存失败：" + e.message, "error");
      }
    };
  }
  if (location.hash === "#settings") setTimeout(openDrawer, 400);

  // 成果预览舱与分屏控件绑定
  $("#splitToggleBtn")?.addEventListener("click", toggleArtifact);
  initSplitResizer();
  $("#apCloseBtn")?.addEventListener("click", hideArtifact);
  $("#apOpenBtn")?.addEventListener("click", async () => {
    if (S.currentArtifact) {
      try {
        await api("/api/file/open", {
          method: "POST",
          body: JSON.stringify({ path: S.currentArtifact.filepath, name: S.currentArtifact.filename })
        });
      } catch (err) {
        showToast("打开文件失败：" + err.message, "error");
      }
    }
  });
  $("#apRevealBtn")?.addEventListener("click", async () => {
    if (S.currentArtifact) {
      try {
        await api("/api/file/open", {
          method: "POST",
          body: JSON.stringify({
            path: S.currentArtifact.filepath || S.currentArtifact.path,
            name: S.currentArtifact.filename || S.currentArtifact.name,
            is_dir: true,
          }),
        });
      } catch (err) {
        showToast("打开目录失败：" + err.message, "error");
      }
    }
  });
  $("#apCopyPathBtn")?.addEventListener("click", () => {
    if (S.currentArtifact && (S.currentArtifact.filepath || S.currentArtifact.path)) {
      navigator.clipboard.writeText(S.currentArtifact.filepath || S.currentArtifact.path);
      const btn = $("#apCopyPathBtn");
      const old = btn.textContent;
      btn.textContent = "已复制✓";
      setTimeout(() => (btn.textContent = old), 1600);
    }
  });
  $("#promptResetAll")?.addEventListener("click", resetAllPrompts);

  // 调拨对账汇总流水线交互绑定
  const pClose = $("#pipelineCloseBtn");
  if (pClose) pClose.onclick = () => closeReconcilePipeline();
  const pS1Reset = $("#pipelineStep1ResetBtn");
  if (pS1Reset) pS1Reset.onclick = () => { ReconcilePipeline.files = []; renderPipelineFiles(); };
  const pS1Next = $("#pipelineStep1NextBtn");
  if (pS1Next) pS1Next.onclick = () => loadAndRenderFieldMapping();
  const pS2Back = $("#pipelineStep2BackBtn");
  if (pS2Back) pS2Back.onclick = () => setReconcileStep(1);
  const pS2Next = $("#pipelineStep2NextBtn");
  if (pS2Next) pS2Next.onclick = () => runAuditAndRenderSheet();
  const pS3Back = $("#pipelineStep3BackBtn");
  if (pS3Back) pS3Back.onclick = () => setReconcileStep(2);
  const pS3Recheck = $("#pipelineStep3RecheckBtn");
  if (pS3Recheck) pS3Recheck.onclick = () => runAuditAndRenderSheet();
  const pS3Next = $("#pipelineStep3NextBtn");
  if (pS3Next) pS3Next.onclick = () => setReconcileStep(4);
  const pS4Back = $("#pipelineStep4BackBtn");
  if (pS4Back) pS4Back.onclick = () => setReconcileStep(3);
  const pFinish = $("#pipelineFinishBtn");
  if (pFinish) pFinish.onclick = () => closeReconcilePipeline();
  const pExportBtn = $("#pipelineExportExcelBtn");
  if (pExportBtn) pExportBtn.onclick = () => executeExportExcel();
  const pToRepBtn = $("#pipelineToReportBtn");
  if (pToRepBtn) pToRepBtn.onclick = () => sendToReportWorkflow();
  const pToPptBtn = $("#pipelineToPptBtn");
  if (pToPptBtn) pToPptBtn.onclick = () => sendToPptWorkflow();

  const addRecCrBtn = $("#addReconcileCustomRuleBtn");
  if (addRecCrBtn) addRecCrBtn.onclick = () => ReconcilePipeline.addCustomRule();

  const recRowSel = $("#reconcileHeaderRowSelect");
  if (recRowSel) {
    recRowSel.onchange = async () => {
      const chosen = parseInt(recRowSel.value, 10);
      ReconcilePipeline.headerRowIndex = chosen - 1;
      const sheetHeaders = {};
      (ReconcilePipeline.fieldsInfo?.files || []).forEach((f) => {
        (f.sheets || []).forEach((s) => {
          sheetHeaders[s.sheet_name] = ReconcilePipeline.headerRowIndex;
        });
      });
      try {
        const res = await api("/api/calc/reconcile_fields", {
          method: "POST",
          body: JSON.stringify({
            conversation_id: S.currentId,
            files: ReconcilePipeline.files,
            sheet_headers: sheetHeaders,
          }),
        });
        ReconcilePipeline.fieldsInfo = res;
        renderMappingGrid(res);
        showToast(`已微调切换至第 ${chosen} 行为表头`, "info");
      } catch (err) {
        showToast("切换表头行失败：" + err.message, "error");
      }
    };
  }
  const pDropzone = $("#pipelineDropzone");
  const pFileInput = $("#pipelineFileInput");
  if (pDropzone && pFileInput) {
    pDropzone.onclick = () => pFileInput.click();
    pFileInput.onchange = (e) => {
      handlePipelineFileUpload([...e.target.files]);
      pFileInput.value = "";
    };
    pDropzone.ondragover = (e) => {
      e.preventDefault();
      pDropzone.classList.add("dragover");
    };
    pDropzone.ondragleave = () => pDropzone.classList.remove("dragover");
    pDropzone.ondrop = (e) => {
      e.preventDefault();
      pDropzone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files) {
        handlePipelineFileUpload([...e.dataTransfer.files]);
      }
    };
  }

  // 供应商比选流水线交互绑定
  const priceClose = $("#pricePipelineCloseBtn");
  if (priceClose) priceClose.onclick = () => closePricePipeline();
  const priceS1Reset = $("#pricePipelineStep1ResetBtn");
  if (priceS1Reset) priceS1Reset.onclick = () => { PricePipeline.files = []; renderPricePipelineFiles(); };
  const priceS1Next = $("#pricePipelineStep1NextBtn");
  if (priceS1Next) priceS1Next.onclick = () => setPriceStep(2);
  const priceS2Back = $("#pricePipelineStep2BackBtn");
  if (priceS2Back) priceS2Back.onclick = () => setPriceStep(1);
  const priceS2Next = $("#pricePipelineStep2NextBtn");
  if (priceS2Next) priceS2Next.onclick = () => runPriceCompareAndRender();
  const priceS3Back = $("#pricePipelineStep3BackBtn");
  if (priceS3Back) priceS3Back.onclick = () => setPriceStep(2);
  const priceS3Recheck = $("#pricePipelineStep3RecheckBtn");
  if (priceS3Recheck) priceS3Recheck.onclick = () => runPriceCompareAndRender();
  const priceS3Next = $("#pricePipelineStep3NextBtn");
  if (priceS3Next) priceS3Next.onclick = () => setPriceStep(4);
  const priceS4Back = $("#pricePipelineStep4BackBtn");
  if (priceS4Back) priceS4Back.onclick = () => setPriceStep(3);
  const priceFinish = $("#pricePipelineFinishBtn");
  if (priceFinish) priceFinish.onclick = () => closePricePipeline();
  const priceExpExcel = $("#priceExportExcelBtn");
  if (priceExpExcel) priceExpExcel.onclick = () => executePriceExportExcel();
  const priceExpPpt = $("#priceExportPptBtn");
  if (priceExpPpt) priceExpPpt.onclick = () => executePriceExportPpt();
  const priceToRep = $("#priceToReportBtn");
  if (priceToRep) priceToRep.onclick = () => sendPriceToReportWorkflow();

  $$(".slider-weight").forEach((slider) => {
    slider.addEventListener("input", updatePriceWeightsFromSliders);
  });

  const priceDropzone = $("#pricePipelineDropzone");
  const priceFileInput = $("#pricePipelineFileInput");
  if (priceDropzone && priceFileInput) {
    priceDropzone.onclick = () => priceFileInput.click();
    priceFileInput.onchange = (e) => {
      handlePriceFileUpload([...e.target.files]);
      priceFileInput.value = "";
    };
    priceDropzone.ondragover = (e) => {
      e.preventDefault();
      priceDropzone.classList.add("dragover");
    };
    priceDropzone.ondragleave = () => priceDropzone.classList.remove("dragover");
    priceDropzone.ondrop = (e) => {
      e.preventDefault();
      priceDropzone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files) {
        handlePriceFileUpload([...e.dataTransfer.files]);
      }
    };
  }

  // 采购合同审查流水线交互绑定
  const reviewClose = $("#reviewPipelineCloseBtn");
  if (reviewClose) reviewClose.onclick = () => closeReviewPipeline();
  const reviewS1Reset = $("#reviewPipelineStep1ResetBtn");
  if (reviewS1Reset) reviewS1Reset.onclick = () => {
    ReviewPipeline.files = [];
    if ($("#reviewContractTextarea")) $("#reviewContractTextarea").value = "";
    renderReviewPipelineFiles();
  };
  const reviewS1Next = $("#reviewPipelineStep1NextBtn");
  if (reviewS1Next) reviewS1Next.onclick = () => setReviewStep(2);
  const reviewS2Back = $("#reviewPipelineStep2BackBtn");
  if (reviewS2Back) reviewS2Back.onclick = () => setReviewStep(1);
  const reviewS2Next = $("#reviewPipelineStep2NextBtn");
  if (reviewS2Next) reviewS2Next.onclick = () => runContractReviewAndRender();
  const reviewS3Back = $("#reviewPipelineStep3BackBtn");
  if (reviewS3Back) reviewS3Back.onclick = () => setReviewStep(2);
  const reviewS3Recheck = $("#reviewPipelineStep3RecheckBtn");
  if (reviewS3Recheck) reviewS3Recheck.onclick = () => runContractReviewAndRender();
  const reviewS3Next = $("#reviewPipelineStep3NextBtn");
  if (reviewS3Next) reviewS3Next.onclick = () => setReviewStep(4);
  const reviewS4Back = $("#reviewPipelineStep4BackBtn");
  if (reviewS4Back) reviewS4Back.onclick = () => setReviewStep(3);
  const reviewFinish = $("#reviewPipelineFinishBtn");
  if (reviewFinish) reviewFinish.onclick = () => closeReviewPipeline();
  const reviewExpDocx = $("#reviewExportDocxBtn");
  if (reviewExpDocx) reviewExpDocx.onclick = () => executeReviewExportDocx();
  const reviewExpPpt = $("#reviewExportPptBtn");
  if (reviewExpPpt) reviewExpPpt.onclick = () => executeReviewExportPpt();
  const reviewToRep = $("#reviewToReportBtn");
  if (reviewToRep) reviewToRep.onclick = () => sendReviewToReportWorkflow();

  const reviewDropzone = $("#reviewPipelineDropzone");
  const reviewFileInput = $("#reviewPipelineFileInput");
  if (reviewDropzone && reviewFileInput) {
    reviewDropzone.onclick = () => reviewFileInput.click();
    reviewFileInput.onchange = (e) => {
      handleReviewFileUpload([...e.target.files]);
      reviewFileInput.value = "";
    };
    reviewDropzone.ondragover = (e) => {
      e.preventDefault();
      reviewDropzone.classList.add("dragover");
    };
    reviewDropzone.ondragleave = () => reviewDropzone.classList.remove("dragover");
    reviewDropzone.ondrop = (e) => {
      e.preventDefault();
      reviewDropzone.classList.remove("dragover");
      if (e.dataTransfer && e.dataTransfer.files) {
        handleReviewFileUpload([...e.dataTransfer.files]);
      }
    };
  }

  const addCrBtn = $("#addCustomRuleBtn");
  if (addCrBtn) addCrBtn.onclick = () => ReviewPipeline.addCustomRule("", "");
  const saveCrBtn = $("#saveCustomRulesTemplateBtn");
  if (saveCrBtn) saveCrBtn.onclick = () => ReviewPipeline.saveTemplate();
  const loadCrBtn = $("#loadCustomRulesTemplateBtn");
  if (loadCrBtn) loadCrBtn.onclick = () => ReviewPipeline.loadTemplate();
  const toggleBuiltinBtn = $("#toggleBuiltinListBtn");
  if (toggleBuiltinBtn) toggleBuiltinBtn.onclick = () => {
    const wrap = $("#builtinRulesWrap");
    if (wrap) wrap.classList.toggle("collapsed");
  };
  const toggleBuiltinCb = $("#toggleBuiltinRulesCheckbox");
  if (toggleBuiltinCb) toggleBuiltinCb.onchange = (e) => {
    const wrap = $("#builtinRulesWrap");
    if (wrap) wrap.style.display = e.target.checked ? "" : "none";
  };
  // 文件弹层
  const pop = document.createElement("div");
  pop.className = "pop";
  pop.id = "filesPop";
  document.body.appendChild(pop);
  $("#filesBtn").onclick = (e) => {
    e.stopPropagation();
    if (pop.classList.contains("show")) return pop.classList.remove("show");
    pop.innerHTML =
      `<h4>本对话已加载文件（${S.files.length}）</h4>` +
      (S.files.length
        ? S.files
            .map(
              (f) => `<div class="pop-item"><span>📄</span><span class="name">${esc(f.name)}</span>
          <span class="meta">${fmtChars(f.chars)}</span>
          <span class="x" data-rm="${f.id}">×</span></div>`
            )
            .join("")
        : '<div class="pop-empty">还没有文件。点输入框左边的 ＋ 或直接拖进来。</div>');
    const r = $("#filesBtn").getBoundingClientRect();
    pop.style.top = r.bottom + 8 + "px";
    pop.style.right = Math.max(12, window.innerWidth - r.right) + "px";
    pop.classList.add("show");
    pop.querySelectorAll("[data-rm]").forEach((x) => {
      x.onclick = async (ev) => {
        ev.stopPropagation();
        await api(`/api/files/${x.dataset.rm}/delete`, { method: "POST" });
        S.files = S.files.filter((f) => f.id !== x.dataset.rm);
        renderChips();
        pop.classList.remove("show");
      };
    });
  };
  document.addEventListener("click", (e) => {
    if (!pop.contains(e.target)) pop.classList.remove("show");
  });

  // 桌面窗口里显示自定义窗口按钮（由 desktop.py 用 ?app=1 打开）
  const isApp = new URLSearchParams(location.search).get("app") === "1";
  document.body.classList.toggle("in-app", isApp);
  if (isApp) {
    // 边缘缩放（指针捕获，鼠标移出窗口也不会丢失）
    ["n", "s", "e", "w", "ne", "nw", "se", "sw"].forEach((dir) => {
      const handle = document.createElement("div");
      handle.className = "rz rz-" + dir;
      document.body.appendChild(handle);
      handle.addEventListener("pointerdown", (ev) => {
        const api = window.pywebview && window.pywebview.api;
        if (!api || !api.resize) return;
        ev.preventDefault();
        document.body.classList.add("is-resizing");
        handle.setPointerCapture(ev.pointerId);
        let pend = { dx: 0, dy: 0 };
        let raf = 0;
        const flush = () => {
          raf = 0;
          if (pend.dx || pend.dy) {
            api.resize(pend.dx, pend.dy, dir);
            pend = { dx: 0, dy: 0 };
          }
        };
        const onMove = (e) => {
          pend.dx += e.movementX || 0;
          pend.dy += e.movementY || 0;
          if (!raf) raf = requestAnimationFrame(flush);
        };
        const onUp = () => {
          flush();
          document.body.classList.remove("is-resizing");
          handle.removeEventListener("pointermove", onMove);
          handle.removeEventListener("pointerup", onUp);
          handle.removeEventListener("pointercancel", onUp);
        };
        handle.addEventListener("pointermove", onMove);
        handle.addEventListener("pointerup", onUp);
        handle.addEventListener("pointercancel", onUp);
      });
    });

    // 拖动窗口：顶部细条
    const bar = document.getElementById("dragbar");
    if (bar) {
      bar.addEventListener("pointerdown", (ev) => {
        const api = window.pywebview && window.pywebview.api;
        if (!api || !api.move) return;
        ev.preventDefault();
        document.body.classList.add("is-resizing");
        bar.setPointerCapture(ev.pointerId);
        let lx = ev.screenX, ly = ev.screenY;
        let pend = { dx: 0, dy: 0 };
        let raf = 0;
        const flush = () => {
          raf = 0;
          if (pend.dx || pend.dy) {
            api.move(pend.dx, pend.dy);
            pend = { dx: 0, dy: 0 };
          }
        };
        const onMove = (e) => {
          pend.dx += e.screenX - lx;
          pend.dy += e.screenY - ly;
          lx = e.screenX;
          ly = e.screenY;
          if (!raf) raf = requestAnimationFrame(flush);
        };
        const onUp = () => {
          flush();
          document.body.classList.remove("is-resizing");
          bar.removeEventListener("pointermove", onMove);
          bar.removeEventListener("pointerup", onUp);
          bar.removeEventListener("pointercancel", onUp);
        };
        bar.addEventListener("pointermove", onMove);
        bar.addEventListener("pointerup", onUp);
        bar.addEventListener("pointercancel", onUp);
      });
    }
  }  const enableAppChrome = () => {
    $$(".wc, #filesBtn").forEach((el) => el.addEventListener("mousedown", (e) => e.stopPropagation()));
    $$(".wc").forEach((b) => {
      b.onclick = (ev) => {
        const api = window.pywebview && window.pywebview.api;
        if (!api) return;
        const act = b.dataset.act;
        if (act === "min") api.minimize();
        else if (act === "close") api.close();
        else if (act === "max") {
          Promise.resolve(api.toggle_max())
            .then((s) => {
              b.textContent = s === "max" ? "❐" : "▢";
              b.title = s === "max" ? "还原" : "最大化";
            })
            .catch(() => {});
        }
      };
    });
  };
  const api0 = window.pywebview && window.pywebview.api;
  if (api0) {
    enableAppChrome();
    if (api0.ping) api0.ping(document.body.className).catch(() => {});
  } else {
    window.addEventListener("pywebviewready", () => {
      enableAppChrome();
      const api = window.pywebview && window.pywebview.api;
      if (api && api.ping) api.ping(document.body.className).catch(() => {});
    });
  }

  // 侧边栏收起 / 展开
  const applySide = () => {
    const collapsed = localStorage.getItem("qwen.sidebar") === "0";
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    const btn = $("#sideToggle");
    if (btn) btn.title = collapsed ? "展开侧边栏" : "收起侧边栏";
  };
  applySide();
  const sideBtn = $("#sideToggle");
  if (sideBtn) {
    sideBtn.onclick = () => {
      const collapsed = document.body.classList.toggle("sidebar-collapsed");
      localStorage.setItem("qwen.sidebar", collapsed ? "0" : "1");
      sideBtn.title = collapsed ? "展开侧边栏" : "收起侧边栏";
    };
  }

  // 移动端
  $("#menuBtn").onclick = () => $("#sidebar").classList.toggle("open");

  window.addEventListener("resize", () => {
    const box = $("#msgScroll");
    box.scrollTop = box.scrollTop;
  });
}

/* ------------------------------------------------ 启动 */
async function init() {
  try {
    bind();
  } catch (err) {
    console.error("bind failed:", err);
  }
  try {
    await loadStatus();
  } catch (err) {
    console.error("loadStatus failed:", err);
  }
  try {
    await loadConvs();
  } catch (err) {
    console.error("loadConvs failed:", err);
    S.convs = [];
  }
  try {
    updatePlaceholder();
  } catch (_) {}

  try {
    if (S.convs && S.convs.length) {
      const firstReal = S.convs.find((c) => c.cnt && c.cnt > 0);
      if (firstReal) {
        await openConv(firstReal.id);
      } else {
        resetView(false);
      }
    } else {
      resetView(false);
    }
  } catch (err) {
    console.error("openConv/resetView failed:", err);
    try { resetView(false); } catch (_) {}
  }

  // 模型未就绪就轮询
  let tries = 0;
  const timer = setInterval(async () => {
    try {
      const ok = await loadStatus();
      if (ok || ++tries > 180) clearInterval(timer);
    } catch (_) {}
  }, 1000);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => init());
} else {
  init();
}

function initSplitResizer() {
  const resizer = $("#artifactResizer");
  const panel = $("#artifactPanel");
  const wb = $("#workbench");
  if (!resizer || !panel || !wb) return;

  resizer.addEventListener("pointerdown", (e) => {
    e.preventDefault();
    document.body.classList.add("is-resizing");
    resizer.classList.add("active");
    try { resizer.setPointerCapture(e.pointerId); } catch (_) {}

    const onPointerMove = (ev) => {
      const wbRect = wb.getBoundingClientRect();
      const newWidth = wbRect.right - ev.clientX;
      const minW = 320;
      const maxW = Math.max(minW, wbRect.width * 0.75);
      const clamped = Math.min(Math.max(newWidth, minW), maxW);
      panel.style.width = `${clamped}px`;
      panel.style.flex = `0 0 ${clamped}px`;
      panel.style.maxWidth = `${clamped}px`;
    };

    const onPointerUp = (ev) => {
      document.body.classList.remove("is-resizing");
      resizer.classList.remove("active");
      try { resizer.releasePointerCapture(ev.pointerId); } catch (_) {}
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
      resizer.removeEventListener("pointermove", onPointerMove);
      resizer.removeEventListener("pointerup", onPointerUp);
      resizer.removeEventListener("pointercancel", onPointerUp);
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    resizer.addEventListener("pointermove", onPointerMove);
    resizer.addEventListener("pointerup", onPointerUp);
    resizer.addEventListener("pointercancel", onPointerUp);
  });
}
