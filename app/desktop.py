# -*- coding: utf-8 -*-
"""灵梦工作台 —— 桌面窗口版（内置服务 + 原生窗口，不经过浏览器）。"""
import ctypes
import os
import socket
import sys
import threading
import time
import traceback

PORT = int(os.environ.get("QWEN_PORT", "7860"))
URL = f"http://127.0.0.1:{PORT}"
_HOME = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON = os.path.join(_HOME, "灵梦-v6.ico")
DATA_DIR = os.path.join(_HOME, "data")
LOG = os.path.join(DATA_DIR, "desktop.log")
LOCK_FILE = os.path.join(DATA_DIR, "app.lock")

# pythonw 没有控制台：把标准输出重定向到文件，避免 print/logging 抛异常
if sys.stdout is None or sys.stderr is None:
    os.makedirs(DATA_DIR, exist_ok=True)
    _stream = open(os.path.join(DATA_DIR, "desktop.out.log"), "a", buffering=1, encoding="utf-8")
    sys.stdout = _stream
    sys.stderr = _stream


def log(msg):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        try:
            if os.path.getsize(LOG) > 2 * 1024 * 1024:  # 2MB 轮转，避免日志无限增长
                os.replace(LOG, LOG + ".1")
        except OSError:
            pass
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except OSError:
        pass


def port_open():
    s = socket.socket()
    s.settimeout(0.4)
    try:
        s.connect(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def http_ready(timeout=0.4):
    import urllib.request
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/", headers={"User-Agent": "LingmengCheck"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 400
    except Exception:
        return False


def serve():
    import uvicorn

    from webapp import app

    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


def set_icon():
    """给窗口和任务栏换上应用图标（Windows）。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        pid = os.getpid()
        hwnds = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if "灵梦工作台" in buf.value.strip():
                    wp = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
                    if wp.value == pid:
                        hwnds.append(hwnd)
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
        tries = 0
        while not hwnds and tries < 10:
            tries += 1
            time.sleep(0.5)
            user32.EnumWindows(EnumProc(_cb), 0)
        if not hwnds:
            log("icon: window not found")
            return
        _HWND[:] = [hwnds[0]]
        try:
            with open(os.path.join(DATA_DIR, "app.hwnd"), "w", encoding="utf-8") as fh:
                fh.write(str(hwnds[0]))
        except OSError:
            pass
        if not os.path.isfile(ICON):
            log("icon file missing")
            return
        LR_LOADFROMFILE, IMAGE_ICON = 0x0010, 1
        hicon_small = user32.LoadImageW(0, ICON, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        hicon_big = user32.LoadImageW(0, ICON, IMAGE_ICON, 32, 32, LR_LOADFROMFILE)
        WM_SETICON = 0x0080
        for hwnd in hwnds:
            if hicon_small:
                user32.SendMessageW(hwnd, WM_SETICON, 0, hicon_small)
            if hicon_big:
                user32.SendMessageW(hwnd, WM_SETICON, 1, hicon_big)
            user32.SetClassLongPtrW(hwnd, -14, hicon_big or hicon_small)  # GCLP_HICON
            user32.SetClassLongPtrW(hwnd, -34, hicon_small or hicon_big)  # GCLP_HICONSM
        log(f"icon applied to {len(hwnds)} window(s)")
        _maximize_on_start(hwnds[0])
    except Exception:  # noqa: BLE001
        log("icon failed: " + traceback.format_exc())


def _maximize_on_start(hwnd):
    """窗口一出现就铺满工作区（不盖任务栏）。"""
    try:
        u = ctypes.windll.user32
        r = window_rect(hwnd)
        _NORMAL_RECT[:] = [(r.left, r.top, r.right - r.left, r.bottom - r.top)]
        wa = work_area()
        u.SetWindowPos(hwnd, 0, wa.left, wa.top, wa.right - wa.left, wa.bottom - wa.top, 0x0004 | 0x0010)
        _fit_children(hwnd)
        log("maximized on start")
    except Exception:  # noqa: BLE001
        log("maximize on start failed: " + traceback.format_exc())


def open_browser():
    """以独立应用窗口模式（--app=...）启动 Edge 或 Chrome，隐藏地址栏与标签页。"""
    import subprocess
    app_url = f"{URL}/?app=1"
    # 严格等待 HTTP 200 就绪后再呼出浏览器，杜绝误报“无法访问此网站”
    for _ in range(50):
        if http_ready(0.3):
            break
        time.sleep(0.2)
    candidates = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ]
    launched = False
    for exe in candidates:
        if os.path.isfile(exe):
            try:
                subprocess.Popen([exe, f"--app={app_url}", "--window-size=1440,920"])
                log(f"launched standalone app window via {exe}")
                launched = True
                break
            except Exception as e:
                log(f"launch app window failed via {exe}: {e}")
    if not launched:
        try:
            import winreg
            for subkey in (
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe",
            ):
                for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        with winreg.OpenKey(root, subkey) as k:
                            exe, _ = winreg.QueryValueEx(k, "")
                            if exe and os.path.isfile(exe):
                                subprocess.Popen([exe, f"--app={app_url}", "--window-size=1440,920"])
                                log(f"launched standalone app window via registry {exe}")
                                launched = True
                                break
                    except OSError:
                        pass
                if launched:
                    break
        except Exception:
            pass
    if launched:
        time.sleep(0.4)
        for _ in range(15):
            if activate_existing():
                break
            time.sleep(0.2)
        return
    log("no standalone browser candidate available to open app window")


def pid_alive(pid):
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True
    except Exception:  # noqa: BLE001
        return False


def already_running():
    try:
        with open(LOCK_FILE, encoding="utf-8") as fh:
            pid = int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return False
    if pid <= 0 or pid == os.getpid() or not pid_alive(pid):
        return False
    # 进程号可能被系统复用；也可能上一实例正在启动（端口尚未就绪）。
    # 最多等 60 秒：端口打开即视为在运行；进程中途退出则视为陈旧锁。
    for _ in range(120):
        if port_open():
            return True
        if not pid_alive(pid):
            break
        time.sleep(0.5)
    log(f"stale lock (pid={pid}), ignore")
    return False


def activate_existing():
    """另一个实例已在运行时：优先把已有窗口切到前台，杜绝重复启动。"""
    try:
        user32 = ctypes.windll.user32
        hwnd = 0
        try:
            hwnd = int((open(os.path.join(DATA_DIR, "app.hwnd"), encoding="utf-8").read() or "0").strip())
        except (OSError, ValueError):
            hwnd = 0
        if hwnd and user32.IsWindow(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
            log(f"activated existing window hwnd={hwnd}")
            return True
        # 枚举查找标题包含“灵梦工作台”的窗口
        hits = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def _cb(h, _):
            n = user32.GetWindowTextLengthW(h)
            if n > 0:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(h, buf, n + 1)
                val = buf.value.strip()
                if "antigravity" in val.lower() or "visual studio" in val.lower() or ".bat" in val or ".py" in val or ".ps1" in val or "cursor" in val.lower():
                    return True
                if "灵梦工作台" in val:
                    hits.append(h)
                    return False
            return True
        user32.EnumWindows(EnumProc(_cb), 0)
        if hits:
            h = hits[0]
            user32.ShowWindow(h, 9)
            user32.BringWindowToTop(h)
            user32.SetForegroundWindow(h)
            try:
                user32.SwitchToThisWindow(h, True)
            except Exception:
                pass
            try:
                with open(os.path.join(DATA_DIR, "app.hwnd"), "w", encoding="utf-8") as fh:
                    fh.write(str(h))
            except OSError:
                pass
            log(f"activated existing window by title hwnd={h}")
            return True
    except Exception:  # noqa: BLE001
        pass
    return False


_MUTEX_HANDLE = None


def acquire_desktop_mutex():
    global _MUTEX_HANDLE
    try:
        ERROR_ALREADY_EXISTS = 183
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, True, "Global\\LingmengWorkbenchDesktopMutex")
        if ctypes.windll.kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            return False
        return bool(_MUTEX_HANDLE)
    except Exception:
        return True


def release_desktop_mutex():
    global _MUTEX_HANDLE
    if _MUTEX_HANDLE:
        try:
            ctypes.windll.kernel32.ReleaseMutex(_MUTEX_HANDLE)
            ctypes.windll.kernel32.CloseHandle(_MUTEX_HANDLE)
        except Exception:
            pass
        _MUTEX_HANDLE = None


def main():
    log("---- start ----")
    # 1. 顶层立即检测：端口已在响应 HTTP 200，直接激活/打开已有窗口并立即退出
    if http_ready(0.3) or port_open():
        log("service already running on port, activating existing window")
        if activate_existing():
            return
        for _ in range(5):
            time.sleep(0.2)
            if activate_existing():
                return
        log("no existing window found after retry, open standalone browser window")
        open_browser()
        return

    # 2. 全局命名互斥锁：防止多开冲突
    if not acquire_desktop_mutex():
        log("another desktop instance is launching, waiting for window...")
        for _ in range(40):
            time.sleep(0.2)
            if activate_existing():
                return
            if http_ready(0.2):
                for _w in range(15):
                    time.sleep(0.2)
                    if activate_existing():
                        return
                open_browser()
                return
        return

    if already_running():
        log("another instance is running, activate it")
        if not activate_existing():
            open_browser()
        release_desktop_mutex()
        return

    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(LOCK_FILE, "w", encoding="utf-8") as fh:
            fh.write(str(os.getpid()))
    except OSError:
        pass
    try:
        _run()
    finally:
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        release_desktop_mutex()


_HWND = []


def find_hwnd():
    """找到本进程的顶层窗口句柄。"""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        if _HWND and user32.IsWindow(_HWND[0]):
            return _HWND[0]
        pid = os.getpid()
        hits = []
        EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(hwnd, _lparam):
            n = user32.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if buf.value.strip() == "灵梦工作台":
                    wp = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wp))
                    if wp.value == pid:
                        hits.append(hwnd)
            return True

        user32.EnumWindows(EnumProc(_cb), 0)
        if hits:
            _HWND[:] = [hits[0]]
            return hits[0]
    except Exception:  # noqa: BLE001
        pass
    return 0


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


_NORMAL_RECT = []


def _fit_children(hwnd):
    """窗口尺寸变了以后，把内嵌浏览器子窗口也拉到客户区大小，强制页面重新布局。"""
    try:
        import ctypes
        from ctypes import wintypes

        u = ctypes.windll.user32
        rc = _RECT()
        u.GetClientRect(hwnd, ctypes.byref(rc))
        cw, ch = rc.right, rc.bottom
        if cw <= 0 or ch <= 0:
            return
        Proc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def _cb(child, _lparam):
            u.SetWindowPos(child, 0, 0, 0, cw, ch, 0x0002 | 0x0004 | 0x0010)
            return True

        u.EnumChildWindows(hwnd, Proc(_cb), 0)
    except Exception:  # noqa: BLE001
        pass


def work_area():
    r = _RECT()
    ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
    return r


def window_rect(hwnd):
    r = _RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


WM_NCHITTEST = 0x0084
HT = {"left": 10, "right": 11, "top": 12, "topleft": 13,
      "topright": 14, "bottom": 15, "bottomleft": 16, "bottomright": 17}
BORDER = 6
_OLD_PROC = []
_PROC_REF = []
_WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_void_p, ctypes.c_uint,
                              ctypes.c_ulonglong, ctypes.c_longlong)


def _wndproc(hwnd, msg, wparam, lparam):
    try:
        if msg == WM_NCHITTEST:
            x = ctypes.c_short(lparam & 0xFFFF).value
            y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
            r = window_rect(hwnd)
            l, t, rr, b = r.left, r.top, r.right, r.bottom
            if rr - l > 100:
                on_l, on_r = x < l + BORDER, x > rr - BORDER
                on_t, on_b = y < t + BORDER, y > b - BORDER
                if on_t and on_l:
                    return HT["topleft"]
                if on_t and on_r:
                    return HT["topright"]
                if on_b and on_l:
                    return HT["bottomleft"]
                if on_b and on_r:
                    return HT["bottomright"]
                if on_l:
                    return HT["left"]
                if on_r:
                    return HT["right"]
                if on_t:
                    return HT["top"]
                if on_b:
                    return HT["bottom"]
    except Exception:  # noqa: BLE001
        pass
    try:
        return ctypes.windll.user32.CallWindowProcW(_OLD_PROC[0], hwnd, msg, wparam, lparam)
    except Exception:  # noqa: BLE001
        return 0


def enable_resize(hwnd):
    """无边框窗口的边缘缩放：只改命中测试，不改窗口样式。"""
    try:
        if _OLD_PROC:
            return
        proc = _WNDPROC(_wndproc)
        old = ctypes.windll.user32.SetWindowLongPtrW(hwnd, -4, proc)
        if not old:
            log("enable_resize: SetWindowLongPtr failed")
            return
        _OLD_PROC[:] = [old]
        _PROC_REF.append(proc)
        log("edge resize installed")
    except Exception:  # noqa: BLE001
        log("enable_resize failed: " + traceback.format_exc())


class Api:
    """给页面上的窗口按钮用（直接走 Win32，稳定）。"""

    def ping(self, info=""):
        log(f"js bridge ok ({info})")
        return "ok"

    def move(self, dx, dy):
        hwnd = find_hwnd()
        if not hwnd:
            return
        u = ctypes.windll.user32
        try:
            dpi = u.GetDpiForWindow(hwnd) or 96
        except Exception:  # noqa: BLE001
            dpi = 96
        scale = dpi / 96.0
        r = window_rect(hwnd)
        x, y = r.left + int(round(dx * scale)), r.top + int(round(dy * scale))
        wa = work_area()
        w, h = r.right - r.left, r.bottom - r.top
        x = max(wa.left - w + 120, min(x, wa.right - 120))
        y = max(wa.top, min(y, wa.bottom - 40))
        u.SetWindowPos(hwnd, 0, x, y, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE

    def resize(self, dx, dy, direction):
        """按增量调整窗口大小；dx/dy 来自页面坐标，需按 DPI 换算成物理像素。"""
        hwnd = find_hwnd()
        if not hwnd:
            return
        u = ctypes.windll.user32
        try:
            dpi = u.GetDpiForWindow(hwnd) or 96
        except Exception:  # noqa: BLE001
            dpi = 96
        scale = dpi / 96.0
        r = window_rect(hwnd)
        x, y = r.left, r.top
        w, h = r.right - r.left, r.bottom - r.top
        ddx, ddy = int(round(dx * scale)), int(round(dy * scale))
        if "e" in direction:
            w += ddx
        if "s" in direction:
            h += ddy
        if "w" in direction:
            w -= ddx
            x += ddx
        if "n" in direction:
            h -= ddy
            y += ddy
        w = max(int(980 * scale), w)
        h = max(int(620 * scale), h)
        # 限制在工作区内，避免底部跑到任务栏后面
        wa = work_area()
        if x < wa.left:
            w -= wa.left - x
            x = wa.left
        if y < wa.top:
            h -= wa.top - y
            y = wa.top
        if x + w > wa.right:
            w = wa.right - x
        if y + h > wa.bottom:
            h = wa.bottom - y
        w = max(int(760 * scale), w)
        h = max(int(520 * scale), h)
        u.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004 | 0x0010)
        _fit_children(hwnd)

    def minimize(self):
        log("api.minimize called")
        h = find_hwnd()
        if h:
            ctypes.windll.user32.ShowWindow(h, 6)  # SW_MINIMIZE

    def toggle_max(self):
        h = find_hwnd()
        if not h:
            return "normal"
        u = ctypes.windll.user32
        SWP_NOZORDER, SWP_NOACTIVATE = 0x0004, 0x0010
        if u.IsIconic(h):
            u.ShowWindow(h, 9)
            time.sleep(0.15)
        if _NORMAL_RECT:
            r = _NORMAL_RECT[0]
            u.SetWindowPos(h, 0, r[0], r[1], r[2], r[3], SWP_NOZORDER | SWP_NOACTIVATE)
            _fit_children(h)
            _NORMAL_RECT.clear()
            return "normal"
        r = window_rect(h)
        _NORMAL_RECT[:] = [(r.left, r.top, r.right - r.left, r.bottom - r.top)]
        wa = work_area()
        u.SetWindowPos(h, 0, wa.left, wa.top, wa.right - wa.left, wa.bottom - wa.top,
                       SWP_NOZORDER | SWP_NOACTIVATE)
        _fit_children(h)
        return "max"

    def close(self):
        h = find_hwnd()
        if h:
            ctypes.windll.user32.PostMessageW(h, 0x0010, 0, 0)  # WM_CLOSE


def _watch():
    u = ctypes.windll.user32
    t0 = time.time()
    for _ in range(40):
        time.sleep(2)
        h = find_hwnd()
        if h:
            r = window_rect(h)
            log(f"watch t={time.time()-t0:.0f}s iconic={bool(u.IsIconic(h))} "
                f"size={r.right-r.left}x{r.bottom-r.top}")


def _selftest():
    time.sleep(14)
    try:
        import webview as wv
        win = wv.windows[0]
        w0 = win.evaluate_js("window.innerWidth")
        log(f"selftest innerWidth before={w0}")
        Api().resize(-200, 0, "e")
        time.sleep(2.5)
        w1 = win.evaluate_js("window.innerWidth")
        log(f"selftest innerWidth after={w1}")
        Api().resize(200, 0, "e")
        time.sleep(2.5)
        w2 = win.evaluate_js("window.innerWidth")
        log(f"selftest innerWidth restored={w2}")
    except Exception:  # noqa: BLE001
        log("selftest failed: " + traceback.format_exc())


def _run():
    started_here = False
    if not port_open():
        threading.Thread(target=serve, daemon=True).start()
        started_here = True

    # 先验活再开窗：每 0.2 秒轮询请求，必须确认返回 200 OK 后再进入窗口创建
    ready = False
    for _ in range(150):
        if http_ready(0.2):
            ready = True
            break
        time.sleep(0.2)
    if not ready:
        log("server failed to start or verify HTTP 200")
        open_browser()
        return

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Lingmeng.Workbench.1")
    except Exception:  # noqa: BLE001
        pass

    try:
        import webview

        webview.settings["DRAG_REGION_SELECTOR"] = "#none-drag-region"
        webview.settings["DRAG_REGION_DIRECT_TARGET_ONLY"] = False
        webview.create_window(
            "灵梦工作台", URL + "?app=1",
            width=1440, height=920, min_size=(980, 620),
            background_color="#F7F8FA",
            frameless=True,
            easy_drag=False,
            js_api=Api(),
        )
        if os.environ.get("QWEN_DEBUG_WATCH") == "1":
            threading.Thread(target=_watch, daemon=True).start()
        if os.environ.get('QWEN_UI_TEST'):
            threading.Thread(target=_selftest, daemon=True).start()
        webview.start(func=set_icon)
        log("window closed")
    except Exception:  # noqa: BLE001
        log("webview failed: " + traceback.format_exc())
        open_browser()
        # 浏览器模式下不要退出，让服务继续跑
        if started_here:
            while True:
                time.sleep(3600)
    finally:
        log("---- exit ----")
        try:
            os.remove(LOCK_FILE)
        except OSError:
            pass
        try:
            os.remove(os.path.join(DATA_DIR, "app.hwnd"))
        except OSError:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
