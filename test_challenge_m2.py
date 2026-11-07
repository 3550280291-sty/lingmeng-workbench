# -*- coding: utf-8 -*-
"""Adversarial Verification Suite for Milestone 2: /api/file/open and Frontend Delivery Card.

Run with:
    D:\\AI\\runtime\\python\\python.exe test_challenge_m2.py
"""
import os
import re
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

# Ensure app is on sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
import webapp
import core


class TestMilestone2Challenge(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.out_dir = os.path.abspath(core.OUT_DIR)
        cls.upload_dir = os.path.abspath(webapp.UPLOAD_DIR)
        cls.data_dir = os.path.abspath(webapp.DATA_DIR)
        os.makedirs(cls.out_dir, exist_ok=True)
        os.makedirs(cls.upload_dir, exist_ok=True)

        # Create temporary real test files
        cls.test_ppt = os.path.join(cls.out_dir, "m2_challenge_test.pptx")
        with open(cls.test_ppt, "wb") as f:
            f.write(b"PK\x03\x04challenge_ppt_content")

        cls.test_excel = os.path.join(cls.out_dir, "m2_challenge_test.xlsx")
        with open(cls.test_excel, "wb") as f:
            f.write(b"PK\x03\x04challenge_excel_content")

        cls.test_doc = os.path.join(cls.out_dir, "m2_challenge_test.docx")
        with open(cls.test_doc, "wb") as f:
            f.write(b"PK\x03\x04challenge_doc_content")

        cls.test_cn = os.path.join(cls.out_dir, "企业级战略汇报_2026.pptx")
        with open(cls.test_cn, "wb") as f:
            f.write(b"PK\x03\x04challenge_cn_content")

        cls.test_space = os.path.join(cls.out_dir, "Quarterly Report 2026.pptx")
        with open(cls.test_space, "wb") as f:
            f.write(b"PK\x03\x04challenge_space_content")

        cls.test_subdir = os.path.join(cls.out_dir, "m2_challenge_subdir")
        os.makedirs(cls.test_subdir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        for path in [
            cls.test_ppt,
            cls.test_excel,
            cls.test_doc,
            cls.test_cn,
            cls.test_space,
        ]:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass
        if os.path.exists(cls.test_subdir):
            try:
                os.rmdir(cls.test_subdir)
            except Exception:
                pass

    # =========================================================================
    # Group 1: Valid File Opening (Expected 200, os.startfile called with file)
    # =========================================================================
    @patch("os.startfile")
    def test_01_valid_pptx_open_post(self, mock_startfile):
        """T1.1: Valid PPTX in output/ returns 200 and calls os.startfile."""
        resp = self.client.post("/api/file/open", json={"path": self.test_ppt, "is_dir": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertFalse(data.get("is_dir"))
        self.assertEqual(data.get("path"), self.test_ppt)
        mock_startfile.assert_called_once_with(self.test_ppt)

    @patch("os.startfile")
    def test_02_valid_xlsx_open_post(self, mock_startfile):
        """T1.2: Valid XLSX in output/ returns 200 and calls os.startfile."""
        resp = self.client.post("/api/file/open", json={"path": self.test_excel, "is_dir": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        mock_startfile.assert_called_once_with(self.test_excel)

    @patch("os.startfile")
    def test_03_valid_name_param_resolution(self, mock_startfile):
        """T1.3: Resolving file via 'name' parameter in output/."""
        resp = self.client.post("/api/file/open", json={"name": "m2_challenge_test.docx"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        mock_startfile.assert_called_once_with(self.test_doc)

    @patch("os.startfile")
    def test_04_chinese_filename_handling(self, mock_startfile):
        """T1.4: Unicode/Chinese characters in filename."""
        resp = self.client.post("/api/file/open", json={"path": self.test_cn})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mock_startfile.assert_called_once_with(self.test_cn)

    @patch("os.startfile")
    def test_05_space_in_filename(self, mock_startfile):
        """T1.5: Filename with spaces handled correctly."""
        resp = self.client.post("/api/file/open", json={"path": self.test_space})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mock_startfile.assert_called_once_with(self.test_space)

    @patch("os.startfile")
    def test_06_get_method_open_file(self, mock_startfile):
        """T1.6: GET request with query parameter to /api/file/open."""
        resp = self.client.get("/api/file/open", params={"path": self.test_ppt})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mock_startfile.assert_called_once_with(self.test_ppt)

    # =========================================================================
    # Group 2: Valid Directory Opening (Expected 200, os.startfile called with dir)
    # =========================================================================
    @patch("os.startfile")
    def test_07_open_output_dir_explicit(self, mock_startfile):
        """T2.1: Open output directory explicitly with is_dir=True."""
        resp = self.client.post("/api/file/open", json={"path": self.out_dir, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_dir"))
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_08_open_directory_with_is_dir_false_auto_detection(self, mock_startfile):
        """T2.2: Passing directory path with is_dir=False auto-detects directory."""
        resp = self.client.post("/api/file/open", json={"path": self.out_dir, "is_dir": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_dir"))
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_09_open_dir_trailing_backslash(self, mock_startfile):
        """T2.3: Directory path with trailing backslash."""
        resp = self.client.post("/api/file/open", json={"path": self.out_dir + "\\", "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_10_open_dir_forward_slashes(self, mock_startfile):
        """T2.4: Directory path with forward slashes."""
        forward_path = self.out_dir.replace("\\", "/")
        resp = self.client.post("/api/file/open", json={"path": forward_path, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_11_open_subdir_in_output(self, mock_startfile):
        """T2.5: Subdirectory inside output/."""
        resp = self.client.post("/api/file/open", json={"path": self.test_subdir, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get("ok"))
        mock_startfile.assert_called_once_with(self.test_subdir)

    @patch("os.startfile")
    def test_12_open_dir_of_file(self, mock_startfile):
        """T2.6: Passing a file path with is_dir=True opens the parent directory."""
        resp = self.client.post("/api/file/open", json={"path": self.test_ppt, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_dir"))
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_13_open_dir_of_nonexistent_file_in_output(self, mock_startfile):
        """T2.7: Passing nonexistent file in output/ with is_dir=True opens output dir."""
        non_file = os.path.join(self.out_dir, "ghost.pptx")
        resp = self.client.post("/api/file/open", json={"path": non_file, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        mock_startfile.assert_called_once_with(self.out_dir)

    @patch("os.startfile")
    def test_14_empty_payload_fallback(self, mock_startfile):
        """T2.8: Completely empty payload defaults to opening output dir."""
        resp = self.client.post("/api/file/open", json={})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_dir"))
        mock_startfile.assert_called_once_with(self.out_dir)

    # =========================================================================
    # Group 3: Directory Traversal and Security Attacks (Expected 403 Forbidden)
    # =========================================================================
    @patch("os.startfile")
    def test_15_traversal_relative_cmd(self, mock_startfile):
        """T3.1: Relative path traversal to System32/cmd.exe -> 403."""
        resp = self.client.post("/api/file/open", json={"path": r"..\..\Windows\System32\cmd.exe"})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_16_traversal_absolute_windows(self, mock_startfile):
        """T3.2: Absolute path to C:\\Windows -> 403."""
        resp = self.client.post("/api/file/open", json={"path": r"C:\Windows"})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_17_traversal_absolute_cmd(self, mock_startfile):
        """T3.3: Absolute path to C:\\Windows\\System32\\cmd.exe -> 403."""
        resp = self.client.post("/api/file/open", json={"path": r"C:\Windows\System32\cmd.exe"})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_18_traversal_deep_from_output(self, mock_startfile):
        """T3.4: Deep dot-dot traversal starting within output directory -> 403."""
        bad_path = os.path.join(self.out_dir, r"..\..\..\..\Windows\System32\cmd.exe")
        resp = self.client.post("/api/file/open", json={"path": bad_path})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_19_unauthorized_internal_code_webapp_py(self, mock_startfile):
        """T3.5: Attempting to open backend source code D:\\AI\\app\\webapp.py -> 403."""
        source_code = os.path.join(APP_DIR, "webapp.py")
        resp = self.client.post("/api/file/open", json={"path": source_code})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_20_unauthorized_root_workspace(self, mock_startfile):
        """T3.6: Attempting to open D:\\AI root workspace -> 403."""
        resp = self.client.post("/api/file/open", json={"path": BASE_DIR})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_21_sibling_directory_bypass_attempt(self, mock_startfile):
        """T3.7: Sibling directory attack (e.g. output_evil) -> 403."""
        evil_dir = self.out_dir + "_evil\\exploit.exe"
        resp = self.client.post("/api/file/open", json={"path": evil_dir})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_22_traversal_via_name_param(self, mock_startfile):
        """T3.8: Directory traversal via 'name' field -> 403."""
        resp = self.client.post("/api/file/open", json={"name": r"..\..\Windows\System32\cmd.exe"})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_23_traversal_with_is_dir_true(self, mock_startfile):
        """T3.9: Directory traversal with is_dir=True -> 403."""
        resp = self.client.post("/api/file/open", json={"path": r"C:\Windows", "is_dir": True})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_24_unc_path_attack(self, mock_startfile):
        """T3.10: UNC network path attempt -> 403."""
        resp = self.client.post("/api/file/open", json={"path": r"\\127.0.0.1\c$\Windows\cmd.exe"})
        self.assertEqual(resp.status_code, 403)
        mock_startfile.assert_not_called()

    # =========================================================================
    # Group 4: Non-Existent Paths (Expected 404 Not Found)
    # =========================================================================
    @patch("os.startfile")
    def test_25_missing_file_in_output_404(self, mock_startfile):
        """T4.1: Non-existent file in output/ with is_dir=False -> 404."""
        missing = os.path.join(self.out_dir, "non_existent_file_xyz_123.pptx")
        resp = self.client.post("/api/file/open", json={"path": missing, "is_dir": False})
        self.assertEqual(resp.status_code, 404)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_26_missing_file_in_uploads_404(self, mock_startfile):
        """T4.2: Non-existent file in uploads/ with is_dir=False -> 404."""
        missing = os.path.join(self.upload_dir, "ghost_excel_999.xlsx")
        resp = self.client.post("/api/file/open", json={"path": missing, "is_dir": False})
        self.assertEqual(resp.status_code, 404)
        mock_startfile.assert_not_called()

    @patch("os.startfile")
    def test_27_missing_file_by_name_404(self, mock_startfile):
        """T4.3: Non-existent file by name -> 404."""
        resp = self.client.post("/api/file/open", json={"name": "definitely_not_here.pptx", "is_dir": False})
        self.assertEqual(resp.status_code, 404)
        mock_startfile.assert_not_called()

    # =========================================================================
    # Group 5: Error Handling and Graceful Fallback
    # =========================================================================
    @patch("os.startfile", side_effect=OSError("System file handler unavailable"))
    def test_28_startfile_exception_returns_graceful_error(self, mock_startfile):
        """T5.1: If os.startfile raises OSError, returns ok: False without crashing."""
        resp = self.client.post("/api/file/open", json={"path": self.test_ppt, "is_dir": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data.get("ok"))
        self.assertIn("error", data)
        self.assertIn("System file handler unavailable", data["error"])

    # =========================================================================
    # Group 6: Frontend Static Analysis (app.js and style.css)
    # =========================================================================
    def test_29_frontend_popup_elimination(self):
        """T6.1: Verify window.alert and window.confirm are overridden and no unintercepted calls exist."""
        app_js_path = os.path.join(APP_DIR, "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check interception
        self.assertIn("window.alert = function", content)
        self.assertIn("window.confirm = function", content)
        self.assertIn("window.prompt = function", content)

        # Ensure no alert exposing 127.0.0.1:7860
        pattern_port = re.compile(r"alert\([^\)]*127\.0\.0\.1:7860")
        self.assertIsNone(pattern_port.search(content), "Found native alert exposing 127.0.0.1:7860!")

        # Ensure no native alert/confirm invocations remain unintercepted
        # (All alerts/confirms should go through showAlert/showConfirm)
        raw_alerts = re.findall(r"(?<![a-zA-Z0-9_\.])alert\s*\(", content)
        raw_confirms = re.findall(r"(?<![a-zA-Z0-9_\.])confirm\s*\(", content)
        self.assertEqual(len(raw_alerts), 0, f"Found raw alert() calls: {raw_alerts}")
        self.assertEqual(len(raw_confirms), 0, f"Found raw confirm() calls: {raw_confirms}")

    def test_30_frontend_card_template_and_actions(self):
        """T6.2: Verify artifact-card buttons and click events."""
        app_js_path = os.path.join(APP_DIR, "web", "app.js")
        with open(app_js_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Button text requirement R4
        self.assertIn("📂 直接用本机软件打开", content)
        self.assertIn("📁 打开所在目录", content)

        # Classes
        self.assertIn("art-btn-open", content)
        self.assertIn("art-btn-reveal", content)
        self.assertIn("artifact-card", content)

        # Event handling calls /api/file/open
        self.assertIn('api("/api/file/open", { method: "POST"', content)

    def test_31_frontend_card_styling(self):
        """T6.3: Verify style.css defines .artifact-card with white background and rounded corners."""
        css_path = os.path.join(APP_DIR, "web", "style.css")
        with open(css_path, "r", encoding="utf-8") as f:
            css = f.read()

        self.assertIn(".artifact-card", css)
        # Verify white background and border-radius
        self.assertTrue(re.search(r"\.artifact-card\s*\{[^}]*background:\s*#FFFFFF", css, re.IGNORECASE))
        self.assertTrue(re.search(r"\.artifact-card\s*\{[^}]*border-radius:\s*12px", css))


if __name__ == "__main__":
    unittest.main(verbosity=2)
