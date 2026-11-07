# -*- coding: utf-8 -*-
"""Verification tests for:
1. Async model loading in background thread (0.5s response).
2. core.status() reporting loading/ready states correctly.
3. Purging all webbrowser.open() calls across the codebase.
4. Single-instance named mutex and port checks in launch.ps1 and desktop.py.
5. Frontend status indicator text for warming up vs ready states.
"""
import unittest
import os
import sys
import threading
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
sys.path.insert(0, APP_DIR)

import core
import webapp
import desktop


class TestAsyncModelLoadingAndStatus(unittest.TestCase):
    def test_core_has_load_model_and_warmup(self):
        """core module must have load_model and warmup callable attributes."""
        self.assertTrue(callable(getattr(core, "load_model", None)))
        self.assertTrue(callable(getattr(core, "warmup", None)))

    def test_core_initial_status_loading_flag(self):
        """core.status() reports loading: True, ready: False while warming."""
        with core._lock:
            core._state.update(loading=True, ready=False)
        st = core.status()
        self.assertTrue(st["loading"])
        self.assertFalse(st["ready"])

    def test_core_status_after_ready(self):
        """core.status() reports loading: False, ready: True once loaded."""
        with core._lock:
            core._state.update(loading=False, ready=True)
        st = core.status()
        self.assertFalse(st["loading"])
        self.assertTrue(st["ready"])

    def test_hardware_detection_is_fast(self):
        """core.hardware() should return in <50ms without blocking on device query."""
        t0 = time.perf_counter()
        hw = core.hardware()
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.05, f"hardware() took too long: {elapsed:.3f}s")
        self.assertIn("cpu", hw)
        self.assertIn("ram_gb", hw)
        self.assertIn("cores", hw)


class TestPurgeWebbrowser(unittest.TestCase):
    def test_no_webbrowser_in_project_files(self):
        """Verify no 'import webbrowser' or 'webbrowser.open' exist in app, launch.ps1, or bat files."""
        checked_extensions = (".py", ".bat", ".ps1", ".vbs")
        forbidden = ["import webbrowser", "webbrowser.open"]

        for root, dirs, files in os.walk(APP_DIR):
            for file in files:
                if file.endswith(checked_extensions):
                    path = os.path.join(root, file)
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                        for term in forbidden:
                            self.assertNotIn(term, content, f"Found forbidden {term} in {path}")

        # Check root launcher files
        for f_name in ["launch.ps1", "灵梦工作台.bat", "启动灵梦工作台.bat", "启动灵梦工作台.vbs"]:
            path = os.path.join(BASE_DIR, f_name)
            if os.path.isfile(path):
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for term in forbidden:
                        self.assertNotIn(term, content, f"Found forbidden {term} in {path}")


class TestSingleInstanceAndHealthCheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE_DIR, "launch.ps1"), "r", encoding="utf-8") as f:
            cls.ps1 = f.read()
        with open(os.path.join(APP_DIR, "desktop.py"), "r", encoding="utf-8") as f:
            cls.desktop_code = f.read()

    def test_launch_ps1_checks_port_at_top_before_mutex(self):
        """launch.ps1 must test HTTP readiness at top level to immediately activate/open window."""
        self.assertIn("Test-HttpReady $port 300", self.ps1)
        self.assertIn("Global\\LingmengWorkbenchLauncherMutex", self.ps1)

    def test_launch_ps1_health_check_loop_interval(self):
        """launch.ps1 health check loop must poll every 0.2s (Start-Sleep -Milliseconds 200)."""
        self.assertIn("Start-Sleep -Milliseconds 200", self.ps1)
        self.assertIn("Test-HttpReady $port 400", self.ps1)

    def test_launch_ps1_no_raw_start_process_url(self):
        """launch.ps1 must not fallback to Start-Process $targetUrl opening user's regular browser tabs."""
        self.assertNotIn("Start-Process $targetUrl", self.ps1)

    def test_launch_ps1_has_utf8_bom(self):
        """launch.ps1 must start with UTF-8 BOM to ensure Windows PowerShell 5.1 parses Chinese chars properly."""
        with open(os.path.join(BASE_DIR, "launch.ps1"), "rb") as f:
            raw = f.read(3)
        self.assertEqual(raw, b"\xef\xbb\xbf", "launch.ps1 is missing UTF-8 BOM!")

    def test_launch_ps1_checks_root_endpoint(self):
        """launch.ps1 Test-HttpReady must query root URL http://127.0.0.1:$port/."""
        self.assertIn('http://127.0.0.1:$port/', self.ps1)

    def test_desktop_py_fuzzy_title_matching(self):
        """desktop.py activate_existing must use substring matching for window title."""
        self.assertIn('if "灵梦工作台" in val:', self.desktop_code)

    def test_desktop_py_has_named_mutex_and_top_check(self):
        """desktop.py must have acquire_desktop_mutex and check http_ready/port_open at start."""
        self.assertTrue(hasattr(desktop, "acquire_desktop_mutex"))
        self.assertTrue(hasattr(desktop, "release_desktop_mutex"))
        self.assertIn("LingmengWorkbenchDesktopMutex", self.desktop_code)
        self.assertIn("http_ready(0.3) or port_open()", self.desktop_code)

    def test_webapp_binds_in_under_half_second(self):
        """Verify webapp FastAPI app can start and respond on test port in < 0.5s."""
        import uvicorn
        import urllib.request
        test_port = 7878
        t_started = threading.Event()

        def _run_server():
            config = uvicorn.Config(webapp.app, host="127.0.0.1", port=test_port, log_level="error")
            server = uvicorn.Server(config)
            t_started.set()
            server.run()

        th = threading.Thread(target=_run_server, daemon=True)
        t0 = time.perf_counter()
        th.start()
        t_started.wait()

        success = False
        elapsed = 0
        for _ in range(25):
            time.sleep(0.04)
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{test_port}/api/status")
                with urllib.request.urlopen(req, timeout=0.1) as resp:
                    if resp.status == 200:
                        elapsed = time.perf_counter() - t0
                        success = True
                        break
            except Exception:
                pass
        self.assertTrue(success, "Webapp failed to respond HTTP 200 within timeout")
        self.assertLess(elapsed, 0.5, f"Webapp startup took too long: {elapsed:.3f}s")


class TestFrontendStatusIndicator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP_DIR, "web", "app.js"), "r", encoding="utf-8") as f:
            cls.js = f.read()
        with open(os.path.join(APP_DIR, "web", "index.html"), "r", encoding="utf-8") as f:
            cls.html = f.read()

    def test_index_html_has_status_elements(self):
        """index.html must have #footStatus, #modelStatus, and #statusIndicator."""
        self.assertIn('id="footStatus"', self.html)
        self.assertIn('id="modelStatus"', self.html)
        self.assertIn('id="statusIndicator"', self.html)

    def test_app_js_warming_and_ready_status_text(self):
        """app.js must display warming text when loading/not ready and ready text when ready."""
        self.assertIn("🟢 服务已就绪（模型后台预热中...）", self.js)
        self.assertIn("🟢 模型已就绪", self.js)
        self.assertIn("modelStatus", self.js)
        self.assertIn("statusIndicator", self.js)


if __name__ == "__main__":
    unittest.main()
