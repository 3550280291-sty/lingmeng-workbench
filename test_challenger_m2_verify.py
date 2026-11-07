# -*- coding: utf-8 -*-
"""Adversarial Verification Suite for Milestone 2 — Challenger Verification
Focus: Frontend delivery card mounting, action button bindings, dialog safety, and API robustness.
"""
import json
import os
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure app path in sys.path
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(WORKSPACE_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
import webapp
import core


class TestMilestone2Challenger(unittest.TestCase):
    """Empirical adversarial verification test suite for M2."""

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.app_js_path = os.path.join(APP_DIR, "web", "app.js")
        cls.index_html_path = os.path.join(APP_DIR, "web", "index.html")
        cls.style_css_path = os.path.join(APP_DIR, "web", "style.css")
        with open(cls.app_js_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.app_js = f.read()
        with open(cls.index_html_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.index_html = f.read()
        with open(cls.style_css_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.style_css = f.read()

    # =========================================================================
    # 1. Frontend Delivery Card Structure & Mounting (.artifact-card)
    # =========================================================================

    def test_css_artifact_card_specification(self):
        """Verify .artifact-card in style.css has white rounded styling."""
        self.assertIn(".artifact-card", cls_css := self.style_css)
        # Check white background and border-radius
        match = re.search(r'\.artifact-card\s*\{([^}]+)\}', cls_css)
        self.assertIsNotNone(match, "Could not find .artifact-card rule in style.css")
        card_rules = match.group(1)
        self.assertTrue(
            "background: #FFFFFF" in card_rules or "background:#FFFFFF" in card_rules or "#fff" in card_rules.lower(),
            f"Artifact card background should be white (#FFFFFF), got: {card_rules}"
        )
        self.assertTrue(
            "border-radius: 12px" in card_rules or "border-radius:12px" in card_rules,
            f"Artifact card should have border-radius: 12px, got: {card_rules}"
        )

    def test_artifact_card_icon_mapping(self):
        """Verify icon mappings in app.js for PPTX (📊), XLSX (📈), DOCX (📄)."""
        self.assertIn('icon = "📊"', self.app_js)
        self.assertIn('icon = "📈"', self.app_js)
        self.assertIn('icon = "📄"', self.app_js)
        self.assertIn('.pptx', self.app_js)
        self.assertIn('.xlsx', self.app_js)
        self.assertIn('.docx', self.app_js)

    def test_render_artifact_card_button_labels(self):
        """Verify artifact card buttons strictly match the required text."""
        self.assertIn("📂 直接用本机软件打开", self.app_js)
        self.assertIn("📁 打开所在目录", self.app_js)
        self.assertIn("art-btn-open", self.app_js)
        self.assertIn("art-btn-reveal", self.app_js)

    def test_render_messages_mounting_hierarchy(self):
        """Verify in app.js that artHtml is mounted right below the bubble body and before tools."""
        # Check the message HTML generation template
        # `<div class="body"><div class="md${streaming}" data-idx="${i}">${thinkHtml}${kpiHtml}${bodyHtml}</div>${artHtml}${thinkLine}${tools}</div>`
        pattern = r'<div class="md\$\{streaming\}"[^>]*>\$\{thinkHtml\}\$\{kpiHtml\}\$\{bodyHtml\}</div>\s*\$\{artHtml\}'
        match = re.search(pattern, self.app_js)
        self.assertIsNotNone(
            match,
            "artHtml is not mounted immediately below the AI markdown message body (<div class=\"md...\">)!"
        )

    def test_doexport_artifact_construction_and_render_call(self):
        """Verify doExport constructs artObj with full metadata and calls renderMessages."""
        self.assertIn("async function doExport", self.app_js)
        # Check that doExport assigns targetMsg.meta.artifact and invokes renderMessages()
        self.assertIn("targetMsg.meta.artifact = artObj", self.app_js)
        self.assertIn("renderMessages()", self.app_js)

    # =========================================================================
    # 2. Button Event Bindings & /api/file/open Backend API
    # =========================================================================

    def test_app_js_event_delegation_for_artifact_buttons(self):
        """Verify click event delegation routes art-btn-open and art-btn-reveal to /api/file/open."""
        self.assertIn('closest(".art-btn-open")', self.app_js)
        self.assertIn('closest(".art-btn-reveal")', self.app_js)
        self.assertIn('/api/file/open', self.app_js)
        # Verify art-btn-reveal passes is_dir: true
        reveal_snippet_match = re.search(r'artReveal[\s\S]*?api\("/api/file/open"[\s\S]*?is_dir:\s*true', self.app_js)
        self.assertIsNotNone(reveal_snippet_match, "art-btn-reveal must pass is_dir: true to /api/file/open!")

    @patch("os.startfile")
    def test_open_pptx_file_success(self, mock_startfile):
        """Verify POST /api/file/open with valid PPTX invokes os.startfile on file path."""
        test_file = os.path.join(core.OUT_DIR, "_challenger_test_.pptx")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("mock pptx binary")
        try:
            resp = self.client.post("/api/file/open", json={"path": test_file, "is_dir": False})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertFalse(data.get("is_dir"))
            self.assertEqual(data.get("path"), test_file)
            mock_startfile.assert_called_once_with(test_file)
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    @patch("os.startfile")
    def test_open_directory_mode_from_file_path(self, mock_startfile):
        """Verify POST /api/file/open with is_dir=True extracts parent dir and opens it."""
        test_file = os.path.join(core.OUT_DIR, "_challenger_test_dir_.xlsx")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("mock xlsx binary")
        try:
            resp = self.client.post("/api/file/open", json={"path": test_file, "is_dir": True})
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertTrue(data.get("ok"))
            self.assertTrue(data.get("is_dir"))
            self.assertEqual(data.get("path"), os.path.abspath(core.OUT_DIR))
            mock_startfile.assert_called_once_with(os.path.abspath(core.OUT_DIR))
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    @patch("os.startfile")
    def test_open_directory_direct(self, mock_startfile):
        """Verify POST /api/file/open with is_dir=True directly on OUT_DIR."""
        resp = self.client.post("/api/file/open", json={"path": core.OUT_DIR, "is_dir": True})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("is_dir"))
        mock_startfile.assert_called_once_with(os.path.abspath(core.OUT_DIR))

    def test_open_file_security_traversal_rejection(self):
        """Verify traversal attempts outside workspace are strictly rejected with 403."""
        malicious_paths = [
            r"C:\Windows\System32\cmd.exe",
            os.path.join(core.OUT_DIR, r"..\..\Windows\System32\calc.exe"),
            os.path.join(core.OUT_DIR, r"..\..\..\etc\passwd"),
            r"D:\AI\app\webapp.py",  # Not in whitelist bases
        ]
        with patch("os.startfile") as mock_startfile:
            for bad_path in malicious_paths:
                resp = self.client.post("/api/file/open", json={"path": bad_path, "is_dir": False})
                self.assertEqual(resp.status_code, 403, f"Path {bad_path} should be blocked with 403, got {resp.status_code}")
                mock_startfile.assert_not_called()

    def test_open_nonexistent_file_returns_404(self):
        """Verify attempting to open a non-existent file returns 404."""
        nonexistent = os.path.join(core.OUT_DIR, "non_existent_file_xyz_123.pptx")
        resp = self.client.post("/api/file/open", json={"path": nonexistent, "is_dir": False})
        self.assertEqual(resp.status_code, 404)

    # =========================================================================
    # 3. Export Pipeline Integration & Database Meta Persistence
    # =========================================================================

    def test_end_to_end_export_and_message_meta_persistence(self):
        """Verify backend _run_export generates artifact and updates message meta in SQLite."""
        # 1. Create a conversation
        c_resp = self.client.post("/api/conversations", json={"mode": "data"})
        self.assertEqual(c_resp.status_code, 200)
        cid = c_resp.json()["id"]

        # 2. Insert user and assistant messages with Markdown table via webapp.db()
        table_md = (
            "以下为物料集中采购核算表：\n\n"
            "| 物料编码 | 物料名称 | 规格型号 | 采购数量 | 采购单价 | 采购总额 |\n"
            "| :--- | :--- | :--- | :--- | :--- | :--- |\n"
            "| MAT-001 | 螺纹钢 | HRB400E 20mm | 120 | 3850 | 462000 |\n"
            "| MAT-002 | 水泥 | P.O 42.5 | 300 | 420 | 126000 |\n"
            "| MAT-003 | 中砂 | 细度模数2.6 | 450 | 135 | 60750 |\n"
        )
        import uuid
        mid = uuid.uuid4().hex[:12]
        with webapp.db() as conn:
            conn.execute(
                "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                (mid, cid, "assistant", table_md, "{}", webapp.now()),
            )

        # 3. Request excel export
        exp_resp = self.client.post("/api/export", json={
            "conversation_id": cid,
            "kind": "excel",
            "message_id": mid
        })
        self.assertEqual(exp_resp.status_code, 200)
        job_id = exp_resp.json()["job_id"]

        # 4. Wait for export job
        import time
        job_data = None
        for _ in range(30):
            time.sleep(0.2)
            st_resp = self.client.get(f"/api/export/{job_id}")
            self.assertEqual(st_resp.status_code, 200)
            job_data = st_resp.json()
            if job_data.get("status") in ["done", "error"]:
                break

        self.assertEqual(job_data.get("status"), "done", f"Export job failed: {job_data.get('error')}")
        self.assertIn("artifact", job_data)
        art = job_data["artifact"]
        self.assertEqual(art["filetype"], "excel")
        self.assertTrue(art["filename"].endswith(".xlsx"))
        self.assertTrue(os.path.isfile(art["filepath"]))

        # 5. Verify message meta in DB is updated
        conv_get = self.client.get(f"/api/conversations/{cid}")
        self.assertEqual(conv_get.status_code, 200)
        conv_detail = conv_get.json()
        target_msg = next((m for m in conv_detail["messages"] if m["id"] == mid), None)
        self.assertIsNotNone(target_msg, "Message not found in conversation")
        self.assertIn("meta", target_msg)
        meta_dict = json.loads(target_msg["meta"]) if isinstance(target_msg["meta"], str) else target_msg["meta"]
        self.assertIn("artifact", meta_dict, "meta.artifact was not persisted in database!")
        self.assertEqual(meta_dict["artifact"]["filename"], art["filename"])

    # =========================================================================
    # 4. Dialog Safety & Zero Exposure of Port 7860
    # =========================================================================

    def test_global_window_alert_confirm_monkeypatch_installed(self):
        """Verify window.alert and window.confirm are globally intercepted."""
        self.assertIn("window.alert = function", self.app_js)
        self.assertIn("window.confirm = function", self.app_js)
        self.assertIn("window.prompt = function", self.app_js)

    def test_zero_raw_alert_with_port_7860(self):
        """Scan all frontend source code for unintercepted native alert exposing 7860."""
        # 1. Regex check for raw alert(...) exposing 127.0.0.1:7860
        matches = re.findall(r'alert\([^\)]*127\.0\.0\.1:7860', self.app_js)
        self.assertEqual(len(matches), 0, f"Found raw alert exposing 7860: {matches}")

        # 2. Check that no active alert() calls exist anywhere in app.js outside the monkeypatch
        code_without_comments = re.sub(r'//.*', '', self.app_js)
        code_without_comments = re.sub(r'/\*[\s\S]*?\*/', '', code_without_comments)

        # Look for standalone alert(...) calls (excluding window.alert = ...)
        raw_alerts = re.findall(r'(?<!window\.)\balert\s*\(', code_without_comments)
        self.assertEqual(len(raw_alerts), 0, f"Found unhandled raw alert() calls: {raw_alerts}")

    def test_html_modal_and_toast_dom_elements_exist(self):
        """Verify index.html contains the necessary DOM elements for custom modal dialogs."""
        self.assertIn('id="toastContainer"', self.index_html)
        self.assertIn('id="customModalMask"', self.index_html)
        self.assertIn('id="modalTitle"', self.index_html)
        self.assertIn('id="modalBody"', self.index_html)
        self.assertIn('id="modalConfirmBtn"', self.index_html)
        self.assertIn('id="modalCancelBtn"', self.index_html)


    # =========================================================================
    # 5. Adversarial Stress Testing & Boundary Attack Surfaces
    # =========================================================================

    @patch("os.startfile")
    def test_path_normalization_inside_whitelist(self, mock_startfile):
        """Verify normalized paths that resolve inside OUT_DIR succeed."""
        test_file = os.path.join(core.OUT_DIR, "_norm_test_.pptx")
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("content")
        try:
            tricky_path = os.path.join(core.OUT_DIR, "..", "output", "_norm_test_.pptx")
            resp = self.client.post("/api/file/open", json={"path": tricky_path, "is_dir": False})
            self.assertEqual(resp.status_code, 200)
            mock_startfile.assert_called_once_with(os.path.abspath(test_file))
        finally:
            if os.path.exists(test_file):
                os.remove(test_file)

    def test_unc_and_scheme_path_traversal_blocking(self):
        """Verify UNC paths, drive jumps, and URI schemes are blocked with 403."""
        hostile_paths = [
            r"\\127.0.0.1\c$\Windows\System32\cmd.exe",
            r"\\localhost\d$\AI\output",
            r"C:\Users\Default\Desktop",
            r"D:\AI\.agents\teamwork\ORIGINAL_REQUEST.md",
        ]
        with patch("os.startfile") as mock_startfile:
            for hp in hostile_paths:
                resp = self.client.post("/api/file/open", json={"path": hp, "is_dir": False})
                self.assertEqual(resp.status_code, 403, f"Hostile path {hp} was not blocked!")
                mock_startfile.assert_not_called()

    def test_artifact_card_xss_and_long_name_resilience(self):
        """Verify artifact card handles XSS payloads and ultra-long filenames safely."""
        # Check that esc is used in renderArtifactCard
        card_func = self.app_js[self.app_js.find("function renderArtifactCard"):self.app_js.find("function showArtifact")]
        self.assertIn("const name = esc(rawName)", card_func)
        self.assertIn("const size = esc(", card_func)
        self.assertIn("const p = esc(", card_func)
        self.assertIn("esc(valStatus)", card_func)
        self.assertIn("esc(valReport || valStatus)", card_func)

    def test_artifact_card_case_insensitivity_and_legacy_extensions(self):
        """Verify uppercase and legacy file extensions (.PPTX, .XLS, .DOC) map properly."""
        card_func = self.app_js[self.app_js.find("function renderArtifactCard"):self.app_js.find("function showArtifact")]
        self.assertIn("const lowerName = rawName.toLowerCase()", card_func)
        self.assertIn('.endsWith(".pptx")', card_func)
        self.assertIn('.endsWith(".ppt")', card_func)
        self.assertIn('.endsWith(".xlsx")', card_func)
        self.assertIn('.endsWith(".xls")', card_func)
        self.assertIn('.endsWith(".docx")', card_func)
        self.assertIn('.endsWith(".doc")', card_func)


if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestMilestone2Challenger)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        print(f"FAILED: {len(result.failures)} failures, {len(result.errors)} errors")
        sys.exit(1)
    else:
        print("ALL CHALLENGER TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)

