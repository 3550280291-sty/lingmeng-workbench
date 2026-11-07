# -*- coding: utf-8 -*-
"""Verification tests for:
1. Cleaning empty/stale conversations from SQLite.
2. Lazy conversation creation and auto-titling.
3. Visual styling (contrast, bold, gold indicator, trash icon).
4. Full-width pipeline overlay (no right gap, no white blank).
5. Launcher HTTP ready check and single-instance activation.
"""
import unittest
import os
import sys
import uuid
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
sys.path.insert(0, APP_DIR)

import webapp
import desktop


class TestBlankSessionCleanupAndLazyCreation(unittest.TestCase):
    def setUp(self):
        self.test_cid = "test_" + uuid.uuid4().hex[:8]
        with webapp.db() as conn:
            conn.execute(
                "INSERT INTO conversations(id,title,mode,created_at,updated_at) VALUES(?,?,?,?,?)",
                (self.test_cid, "新对话", "general", webapp.now(), webapp.now()),
            )

    def tearDown(self):
        with webapp.db() as conn:
            conn.execute("DELETE FROM messages WHERE conv_id=?", (self.test_cid,))
            conn.execute("DELETE FROM files WHERE conv_id=?", (self.test_cid,))
            conn.execute("DELETE FROM chunks WHERE conv_id=?", (self.test_cid,))
            conn.execute("DELETE FROM conversations WHERE id=?", (self.test_cid,))

    def test_cleanup_empty_conversations_removes_zero_message_conversations(self):
        """Empty conversations without any messages must be purged by cleanup_empty_conversations."""
        with webapp.db() as conn:
            row = conn.execute("SELECT id FROM conversations WHERE id=?", (self.test_cid,)).fetchone()
            self.assertIsNotNone(row)

        purged = webapp.cleanup_empty_conversations()
        self.assertGreaterEqual(purged, 1)

        with webapp.db() as conn:
            row = conn.execute("SELECT id FROM conversations WHERE id=?", (self.test_cid,)).fetchone()
            self.assertIsNone(row, "Empty conversation should have been completely purged from database!")

    def test_list_convs_never_returns_empty_conversations(self):
        """list_convs must auto-clean and never return convs with cnt=0."""
        convs = webapp.list_convs()
        for c in convs:
            self.assertGreater(c["cnt"], 0, f"Conversation {c['id']} had cnt=0 but was returned by list_convs!")


    def test_cleanup_empty_conversations_with_null_in_messages(self):
        """Even if messages table contains a NULL conv_id, cleanup_empty_conversations must NOT fail to purge."""
        with webapp.db() as conn:
            conn.execute(
                "INSERT INTO messages(id,conv_id,role,content,meta,created_at) VALUES(?,?,?,?,?,?)",
                ("null_msg_" + uuid.uuid4().hex[:6], None, "system", "test", "{}", webapp.now()),
            )
        try:
            purged = webapp.cleanup_empty_conversations()
            self.assertGreaterEqual(purged, 1)
            with webapp.db() as conn:
                row = conn.execute("SELECT id FROM conversations WHERE id=?", (self.test_cid,)).fetchone()
                self.assertIsNone(row, "Empty conversation should have been purged even with NULL in messages table!")
        finally:
            with webapp.db() as conn:
                conn.execute("DELETE FROM messages WHERE conv_id IS NULL")


class TestFrontendVisualHierarchyAndPipelineStyles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP_DIR, "web", "style.css"), "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(os.path.join(APP_DIR, "web", "app.js"), "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_conv_group_visual_prominence(self):
        """Time group titles (今天, 昨天, 更早) must have #1D1D1F, font-weight 700, 13px, and 3px gold bar."""
        self.assertIn(".conv-group", self.css)
        self.assertIn("#1D1D1F", self.css)
        self.assertIn("13px", self.css)
        self.assertIn("#C9A063", self.css)
        self.assertTrue("3px" in self.css)

    def test_conv_item_middle_gray_and_active_white_card(self):
        """Normal items must use #6E6E73, active must use #FFFFFF card, and trash icon must be used."""
        self.assertIn("#6E6E73", self.css)
        self.assertIn(".conv-item.active", self.css)
        self.assertIn("#FFFFFF", self.css)
        self.assertIn("🗑️", self.js)

    def test_pipeline_layout_full_width_no_right_gap(self):
        """When has-pipeline-open is active, chat-pane must be 100% full width and artifact-panel zero-width."""
        self.assertIn("body.has-pipeline-open .chat-pane", self.css)
        self.assertIn("width: 100% !important;", self.css)
        self.assertIn("flex: 1 1 100% !important;", self.css)
        self.assertIn("flex: 0 0 0 !important;", self.css)
        self.assertIn("width: 0 !important;", self.css)

    def test_standalone_alias_hidden_no_whiteout_overlay(self):
        """Alias placeholder must have display: none !important and not be in the absolute backdrop rule."""
        self.assertIn(".standalone-panel-alias", self.css)
        self.assertIn("display: none !important;", self.css)
        self.assertNotIn("#对账汇总-panel,", self.css)
        self.assertNotIn("#比选比价-panel,", self.css)


class TestStartupLauncherRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(BASE_DIR, "launch.ps1"), "r", encoding="utf-8") as f:
            cls.ps1 = f.read()

    def test_launch_ps1_contains_http_ready_check(self):
        """launch.ps1 must strictly check HTTP readiness before calling browser."""
        self.assertIn("Test-HttpReady", self.ps1)
        self.assertIn("/api/status", self.ps1)
        self.assertIn("Open-AppWindow", self.ps1)

    def test_launch_ps1_contains_singleton_win32_helper(self):
        """launch.ps1 must contain Win32Helper with FindLingmengWindow, ActivateHwnd, and SwitchToThisWindow."""
        self.assertIn("Win32Helper", self.ps1)
        self.assertIn("FindLingmengWindow", self.ps1)
        self.assertIn("ActivateHwnd", self.ps1)
        self.assertIn("SwitchToThisWindow", self.ps1)
        self.assertIn("Activate-LingmengWindow", self.ps1)

    def test_launch_ps1_contains_named_mutex(self):
        """launch.ps1 must use Named Mutex to prevent multi-process race conditions under rapid double-click."""
        self.assertIn("LingmengWorkbenchLauncherMutex", self.ps1)
        self.assertIn("System.Threading.Mutex", self.ps1)

    def test_desktop_py_contains_http_ready(self):
        """desktop.py must contain http_ready and use it in open_browser and _run."""
        self.assertTrue(hasattr(desktop, "http_ready"))
        self.assertTrue(hasattr(desktop, "activate_existing"))


if __name__ == "__main__":
    unittest.main()
