# -*- coding: utf-8 -*-
r"""Adversarial & Edge Case Verification Suite for Milestone 2:
3+2 Layout, Untagged Thinking Folding, and Reconcile Pipeline 4-step.
"""
import io
import json
import os
import re
import sys
import tempfile
import unittest
import pandas as pd
import openpyxl

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
import webapp
import core
import calc_engine


class TestMilestone2Adversarial(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.app_js_path = os.path.join(APP_DIR, "web", "app.js")
        cls.index_html_path = os.path.join(APP_DIR, "web", "index.html")
        cls.style_css_path = os.path.join(APP_DIR, "web", "style.css")
        with open(cls.app_js_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.app_js = f.read()

    # =========================================================================
    # 1. JS 语法与占位符字典完整性
    # =========================================================================
    def test_01_update_placeholder_syntax_integrity(self):
        """Verify updatePlaceholder has valid closed object literal for tips."""
        match = re.search(r"function\s+updatePlaceholder\s*\(\)\s*\{([\s\S]*?)\n\}", self.app_js)
        self.assertIsNotNone(match, "updatePlaceholder function must exist")
        fn_body = match.group(1)
        # Ensure 'const tips = {' is properly closed with '};' before assignment
        self.assertIn("const tips = {", fn_body)
        self.assertIn("};", fn_body)
        self.assertIn('merge: "上传调拨表与对账清单，运行确定性对账流水线…"', fn_body)
        self.assertIn('$("#input").placeholder = tips[S.mode] || tips.general;', fn_body)

    # =========================================================================
    # 2. Thinking 模型无标签思考过程复杂边界验证
    # =========================================================================
    def test_02_split_think_adversarial_crlf_and_leading_newlines(self):
        """Verify splitThink logic handles CRLF line endings and leading newlines without breaking."""
        delim_re = re.compile(
            r'(?:<\/think>|\r?\n[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$)|\r?\n{2,}(?=您已选定|您目前提供|您好|抱歉|哎呀|感谢|很抱歉)|\r?\n{2,}(?=###?\s*(?:\[?[✅📊🔍💡📌🚨]|一、|[0-9]+[、.]|\*\*))|\r?\n{2,}(?=\*\*(?:报告标题|示范|印尼|项目|总体|采购|方案|对账|自查|需求))|\r?\n{2,}(?=[✅📊🔍💡📌🚨])|\r?\n(?=[✅📊🔍💡📌🚨])|\r?\n{2,}(?=[一二三四五]、)|\r?\n\r?\n\r?\n+)'
        )
        mono_prefixes = ["首先", "思考", "我需要"]

        # Case A: Leading newlines + CRLF delimiter
        text_a = "\r\n\r\n首先，核对调拨表与财务清单物料条目。\r\n---\r\n这是为您核验的正式报告："
        lead_offset = len(text_a) - len(text_a.lstrip())
        trim_s = text_a[lead_offset:]
        self.assertTrue(any(trim_s.startswith(p) for p in mono_prefixes))
        m_delim = delim_re.search(trim_s)
        self.assertIsNotNone(m_delim)
        think_a = trim_s[:m_delim.start()].strip()
        body_a = trim_s[m_delim.start():]
        body_a = re.sub(r'^(?:<\/think>|\r?\n?[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$))', '', body_a).lstrip()
        self.assertEqual(think_a, "首先，核对调拨表与财务清单物料条目。")
        self.assertEqual(body_a, "这是为您核验的正式报告：")

        # Case B: Tagged <think> with unclosed ending but delimiter ---
        text_b = "<think>\n内部推理分析中...\n---\n正式交付物正文"
        open_match = re.search(r"<think[^>]*>([\s\S]*)$", text_b, re.IGNORECASE)
        self.assertIsNotNone(open_match)
        inside = open_match.group(1)
        m_delim_b = delim_re.search(inside)
        self.assertIsNotNone(m_delim_b)
        think_b = inside[:m_delim_b.start()].strip()
        body_b = inside[m_delim_b.start():]
        body_b = re.sub(r'^(?:<\/think>|\r?\n?[ \t]*(?:---|===|\*\*\*)[ \t]*(?:\r?\n|$))', '', body_b).lstrip()
        self.assertEqual(think_b, "内部推理分析中...")
        self.assertEqual(body_b, "正式交付物正文")

    # =========================================================================
    # 3. 文件上传双路由与会话归属验证
    # =========================================================================
    def test_03_file_upload_both_endpoints_and_conv_id_binding(self):
        """Verify both /api/upload and /api/files/upload accept conversation_id and persist it."""
        # Create test conversation
        c_resp = self.client.post("/api/conversations", json={"mode": "merge"})
        cid = c_resp.json()["id"]

        test_content = b"header1,header2\nval1,val2\n"

        # 1. Test /api/upload
        up1 = self.client.post(
            "/api/upload",
            data={"conversation_id": cid},
            files={"file": ("test_up1.csv", io.BytesIO(test_content), "text/csv")}
        )
        self.assertEqual(up1.status_code, 200)
        res1 = up1.json()
        self.assertIn("id", res1)
        self.assertIn("path", res1)

        # 2. Test /api/files/upload alias
        up2 = self.client.post(
            "/api/files/upload",
            data={"conversation_id": cid},
            files={"file": ("test_up2.csv", io.BytesIO(test_content), "text/csv")}
        )
        self.assertEqual(up2.status_code, 200)
        res2 = up2.json()
        self.assertIn("id", res2)
        self.assertIn("path", res2)

        # 3. Verify in database that conv_id was persisted
        with webapp.db() as conn:
            rows = conn.execute("SELECT id, name, conv_id FROM files WHERE conv_id=?", (cid,)).fetchall()
            row_names = [r["name"] for r in rows]
            self.assertIn("test_up1.csv", row_names)
            self.assertIn("test_up2.csv", row_names)

        # Cleanup
        for path in [res1.get("path"), res2.get("path")]:
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    # =========================================================================
    # 4. 复杂业务对账：多批次调拨汇总与列名冲突防串扰
    # =========================================================================
    def test_04_calc_engine_multi_batch_and_identical_column_names(self):
        """Verify multi-batch transfers sum properly and identical '数量' columns don't collide."""
        tmp = tempfile.gettempdir()
        f_transfer = os.path.join(tmp, "m2_adv_transfer.xlsx")
        f_reconcile = os.path.join(tmp, "m2_adv_reconcile.xlsx")

        # Table 1: Transfer has TWO batches of 螺纹钢 (50 + 50 = 100), and Cement (200)
        # Note: both tables use column name '数量'!
        df_trans = pd.DataFrame([
            {"物资名称": "螺纹钢", "规格型号": "Φ20", "数量": 50.0, "调出单位": "一号库", "调入单位": "项目A"},
            {"物资名称": "螺纹钢", "规格型号": "Φ20", "数量": 50.0, "调出单位": "二号库", "调入单位": "项目A"},
            {"物资名称": "水泥", "规格型号": "42.5", "数量": 200.0, "调出单位": "一号库", "调入单位": "项目B"},
        ])
        df_trans.to_excel(f_transfer, index=False)

        # Table 2: Reconcile has 螺纹钢 (100) and Cement (180, discrepancy -20)
        df_rec = pd.DataFrame([
            {"物资名称": "螺纹钢", "规格型号": "Φ20", "数量": 100.0, "调出单位": "一号库", "调入单位": "项目A"},
            {"物资名称": "水泥", "规格型号": "42.5", "数量": 180.0, "调出单位": "一号库", "调入单位": "项目B"},
        ])
        df_rec.to_excel(f_reconcile, index=False)

        files = [
            {"name": "调拨明细表.xlsx", "path": f_transfer},
            {"name": "财务对账清单.xlsx", "path": f_reconcile},
        ]

        try:
            # 1. Test audit calculation
            audit = calc_engine.generate_reconciliation_audit(files)
            self.assertTrue(audit["ok"])
            self.assertEqual(audit["passed_count"], 1, "螺纹钢 50+50 vs 100 must be PASSED")
            self.assertEqual(audit["discrepancy_count"], 1, "水泥 180 vs 200 must have discrepancy")

            steel_item = next(p for p in audit["passed_items"] if p["name"] == "螺纹钢")
            self.assertEqual(steel_item["book_qty"], 100.0)
            self.assertEqual(steel_item["actual_qty"], 100.0)
            self.assertEqual(steel_item["diff"], 0.0)

            cement_item = next(d for d in audit["discrepancy_items"] if d["name"] == "水泥")
            self.assertEqual(cement_item["book_qty"], 180.0)
            self.assertEqual(cement_item["actual_qty"], 200.0)
            self.assertEqual(cement_item["diff"], -20.0)

            # 2. Test generate_summary_excel
            out_res = calc_engine.generate_summary_excel(files, tmp)
            self.assertTrue(out_res["ok"])
            self.assertEqual(out_res["total_qty"], 280.0, "Total book qty should be 100+180=280")
            self.assertEqual(out_res["total_transfer"], 300.0, "Total transfer qty should be 100+200=300")

            wb = openpyxl.load_workbook(out_res["path"], data_only=True)
            ws = wb.active
            rows = list(ws.iter_rows(values_only=True))
            # Verify row 4 & 5 data
            data_rows = [r for r in rows if isinstance(r[0], int)]
            self.assertEqual(len(data_rows), 2)
            steel_row = next(r for r in data_rows if r[4] == "螺纹钢")
            # header order: 序号(0), 调拨量(1), 调拨日期(2), 物资类别(3), 物资名称(4), 规格型号(5), 单位(6), 数量(7)
            self.assertEqual(steel_row[1], 100.0, "Steel transfer qty")
            self.assertEqual(steel_row[7], 100.0, "Steel book qty")
            self.assertEqual(steel_row[11], "账实相符", "Steel remark")

            wb.close()
            if os.path.exists(out_res["path"]):
                os.remove(out_res["path"])

        finally:
            for p in [f_transfer, f_reconcile]:
                if os.path.exists(p):
                    os.remove(p)

    # =========================================================================
    # 5. 表头带有合并标题或多余前置行的自动清理测试
    # =========================================================================
    def test_05_header_cleaning_banner_row_immunity(self):
        """Verify _clean_header_dataframe promotes real headers when title row exists."""
        df_raw = pd.DataFrame([
            ["物资调拨与结算汇总总表", None, None],
            ["物资名称", "规格型号", "数量"],
            ["盘条", "Φ8", 120.0],
        ])
        df_cleaned = calc_engine._clean_header_dataframe(df_raw)
        self.assertIn("物资名称", df_cleaned.columns)
        self.assertIn("规格型号", df_cleaned.columns)
        self.assertIn("数量", df_cleaned.columns)
        self.assertEqual(len(df_cleaned), 1)
        self.assertEqual(df_cleaned.iloc[0]["物资名称"], "盘条")


if __name__ == "__main__":
    unittest.main()
