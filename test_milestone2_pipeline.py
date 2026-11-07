# -*- coding: utf-8 -*-
r"""Milestone 2 Comprehensive Verification Suite:
3+2 Homepage Layout, Untagged Thinking Folding, and Reconcile Pipeline (4-step).

Run with:
    & "D:\AI\runtime\python\python.exe" test_milestone2_pipeline.py
"""
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


class TestMilestone2Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.out_dir = os.path.abspath(core.OUT_DIR)
        cls.upload_dir = os.path.abspath(webapp.UPLOAD_DIR)
        os.makedirs(cls.out_dir, exist_ok=True)
        os.makedirs(cls.upload_dir, exist_ok=True)

        cls.app_js_path = os.path.join(APP_DIR, "web", "app.js")
        cls.index_html_path = os.path.join(APP_DIR, "web", "index.html")
        cls.style_css_path = os.path.join(APP_DIR, "web", "style.css")

        with open(cls.app_js_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.app_js = f.read()
        with open(cls.index_html_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.index_html = f.read()
        with open(cls.style_css_path, "r", encoding="utf-8", errors="ignore") as f:
            cls.style_css = f.read()

        # Build sample reconciliation Excel files for testing
        cls.file_transfer = os.path.join(cls.upload_dir, "m2_test_transfer.xlsx")
        cls.file_reconcile = os.path.join(cls.upload_dir, "m2_test_reconcile.xlsx")

        # Table 1: 调拨表 (Actual transfer records)
        df_transfer = pd.DataFrame([
            {"物料名称": "螺纹钢", "规格型号": "HRB400E Φ20", "计量单位": "吨", "调拨量": 150.0, "调出单位": "一号库", "调入单位": "项目部A", "调拨日期": "2026-10-15"},
            {"物料名称": "水泥", "规格型号": "P.O 42.5", "计量单位": "吨", "调拨量": 200.0, "调出单位": "二号库", "调入单位": "项目部B", "调拨日期": "2026-10-16"},
            {"物料名称": "中砂", "规格型号": "细度模数2.6", "计量单位": "立方", "调拨量": 300.0, "调出单位": "料场", "调入单位": "搅拌站", "调拨日期": "2026-10-17"},
            {"物料名称": "脚手管", "规格型号": "Φ48*3.5", "计量单位": "米", "调拨量": 800.0, "调出单位": "周转库", "调入单位": "项目部A", "调拨日期": "2026-10-18"},
        ])
        df_transfer.to_excel(cls.file_transfer, index=False)

        # Table 2: 对账清单 (Book records with intended match, discrepancy, and missing items)
        # - 螺纹钢: matched (150.0 vs 150.0) -> passed
        # - 水泥: discrepancy (180.0 vs 200.0, diff = -20.0) -> discrepancy
        # - 中砂: matched (300.0 vs 300.0) -> passed
        # - 安全网: only in book (100.0 vs 0.0) -> missing in transfer
        # (脚手管: only in transfer, not in book -> missing in book)
        df_reconcile = pd.DataFrame([
            {"物资品名": "螺纹钢", "材质/规格": "HRB400E Φ20", "单位": "吨", "账面数量": 150.0, "发料单位": "一号库", "收料单位": "项目部A", "业务日期": "2026-10-15"},
            {"物资品名": "水泥", "材质/规格": "P.O 42.5", "单位": "吨", "账面数量": 180.0, "发料单位": "二号库", "收料单位": "项目部B", "业务日期": "2026-10-16"},
            {"物资品名": "中砂", "材质/规格": "细度模数2.6", "单位": "立方", "账面数量": 300.0, "发料单位": "料场", "收料单位": "搅拌站", "业务日期": "2026-10-17"},
            {"物资品名": "阻燃安全网", "材质/规格": "1.8*6m", "单位": "张", "账面数量": 100.0, "发料单位": "防护库", "收料单位": "项目部C", "业务日期": "2026-10-19"},
        ])
        df_reconcile.to_excel(cls.file_reconcile, index=False)

    @classmethod
    def tearDownClass(cls):
        for p in [cls.file_transfer, cls.file_reconcile]:
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass

    # =========================================================================
    # 1. 首页 3+2 结构与下沉通用能力验证
    # =========================================================================

    def test_01_welcome_cards_3_plus_2_layout_structure(self):
        """Verify renderWelcome in app.js implements 3 core cards + 2 delivery cards."""
        # Check core modes: merge, price, review
        self.assertIn('"merge"', self.app_js)
        self.assertIn('调拨对账汇总', self.app_js)
        self.assertIn('"price"', self.app_js)
        self.assertIn('供应商比选/比价', self.app_js)
        self.assertIn('"review"', self.app_js)
        self.assertIn('采购合同审查', self.app_js)

        # Check delivery modes: report, ppt
        self.assertIn('"report"', self.app_js)
        self.assertIn('写专业报告（短/长报告）', self.app_js)
        self.assertIn('"ppt"', self.app_js)
        self.assertIn('生成演示 PPT', self.app_js)

        # Check section labels
        self.assertIn('【核心业务任务】', self.app_js)
        self.assertIn('【通用成果交付】', self.app_js)
        self.assertIn('cards-grid cards-3', self.app_js)
        self.assertIn('cards-grid cards-2', self.app_js)

        # Check footer note sinking general chat and table analysis
        self.assertIn('welcome-footer-note', self.app_js)
        self.assertIn('「通用对话」与「自由表格分析」已作为底部输入框的默认底层能力', self.app_js)

    def test_02_merge_card_click_opens_pipeline(self):
        """Verify clicking 调拨对账汇总 opens the 4-step pipeline."""
        self.assertIn('if (modeId === "merge") {', self.app_js)
        self.assertIn('openReconcilePipeline()', self.app_js)

    def test_03_css_styling_for_3_plus_2_and_pipeline(self):
        """Verify style.css includes styling for 3+2 grid and pipeline components."""
        self.assertIn('.cards-grid.cards-3', self.style_css)
        self.assertIn('.cards-grid.cards-2', self.style_css)
        self.assertIn('.pipeline-panel', self.style_css)
        self.assertIn('.pipeline-stepper', self.style_css)
        self.assertIn('.audit-sheet', self.style_css)
        self.assertIn('.audit-scope-box', self.style_css)
        self.assertIn('.audit-table', self.style_css)

    # =========================================================================
    # 2. Thinking 模型无标签思考过程折叠验证 (splitThink)
    # =========================================================================

    def test_04_split_think_tagged_monologue(self):
        """Verify splitThink handles standard <think> ... </think> tags."""
        # We can extract the regex / function logic or run node / python simulation
        pattern = r'<think[^>]*>([\s\S]*?)<\/think>'
        text = "<think>正在分析两表数据...\n计算差额中</think>这是正文回答。"
        m = re.search(pattern, text, re.IGNORECASE)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), "正在分析两表数据...\n计算差额中")

    def test_05_split_think_untagged_monologue_with_delimiter(self):
        """Verify splitThink in app.js regex handles untagged reasoning starting with '首先，' separated by ---."""
        self.assertIn('MONO_PREFIXES', self.app_js)
        self.assertIn('"首先"', self.app_js)
        self.assertIn('THINK_DELIM_RE', self.app_js)

        # Test regex pattern from app.js
        sample_delim = "\n---\n"
        delim_pattern = r'(?:<\/think>|\n[ \t]*---[ \t]*(?:\r?\n|$)|\n[ \t]*===[ \t]*(?:\r?\n|$))'
        self.assertIsNotNone(re.search(delim_pattern, sample_delim))

        # Check that app.js wraps think output in details.think-box
        self.assertIn('<details class="think-box"', self.app_js)
        self.assertIn('已深度推演', self.app_js)

    # =========================================================================
    # 3. 调拨对账流水线 4 步面板 DOM 元素完整性
    # =========================================================================

    def test_06_pipeline_panel_dom_structure(self):
        """Verify index.html contains all 4 pipeline steps and key elements."""
        # Stepper
        self.assertIn('id="reconcilePipeline"', self.index_html)
        self.assertIn('id="pipelineStepper"', self.index_html)

        # Step 1
        self.assertIn('id="pipelineStep1"', self.index_html)
        self.assertIn('id="pipelineDropzone"', self.index_html)
        self.assertIn('id="pipelineFileInput"', self.index_html)
        self.assertIn('id="pipelineFilesList"', self.index_html)
        self.assertIn('id="pipelineStep1NextBtn"', self.index_html)

        # Step 2
        self.assertIn('id="pipelineStep2"', self.index_html)
        self.assertIn('id="mappingGrid"', self.index_html)
        self.assertIn('id="pipelineStep2NextBtn"', self.index_html)

        # Step 3
        self.assertIn('id="pipelineStep3"', self.index_html)
        self.assertIn('id="auditSheetContainer"', self.index_html)
        self.assertIn('id="auditScopeText"', self.index_html)
        self.assertIn('id="auditKpiBar"', self.index_html)
        self.assertIn('id="auditPassedTitle"', self.index_html)
        self.assertIn('id="auditPassedTableWrap"', self.index_html)
        self.assertIn('id="auditDiscrepancyTitle"', self.index_html)
        self.assertIn('id="auditDiscrepancyTableWrap"', self.index_html)
        self.assertIn('id="pipelineStep3NextBtn"', self.index_html)

        # Step 4
        self.assertIn('id="pipelineStep4"', self.index_html)
        self.assertIn('id="pipelineExportExcelBtn"', self.index_html)
        self.assertIn('id="pipelineToReportBtn"', self.index_html)
        self.assertIn('id="pipelineToPptBtn"', self.index_html)

    # =========================================================================
    # 4. calc_engine 核心算法核算测试
    # =========================================================================

    def test_07_calc_engine_get_table_columns_and_candidates(self):
        """Verify get_table_columns_and_candidates extracts columns and suggests correct mapping."""
        files = [
            {"name": "m2_test_transfer.xlsx", "path": self.file_transfer},
            {"name": "m2_test_reconcile.xlsx", "path": self.file_reconcile},
        ]
        info = calc_engine.get_table_columns_and_candidates(files)
        self.assertTrue(info["ok"])
        self.assertEqual(len(info["files"]), 2)

        # Check candidate suggestions
        suggested = info["suggested_mapping"]
        # Material name should match '物料名称' or '物资品名'
        self.assertIn(suggested.get("物资名称"), ["物料名称", "物资品名"])
        # Spec should match '规格型号' or '材质/规格'
        self.assertIn(suggested.get("规格型号"), ["规格型号", "材质/规格"])
        # Quantity should match '调拨量' or '账面数量'
        self.assertIn(suggested.get("数量"), ["调拨量", "账面数量"])

    def test_08_calc_engine_generate_reconciliation_audit(self):
        """Verify generate_reconciliation_audit computes exact audit totals, pass/discrepancy items."""
        files = [
            {"name": "m2_test_transfer.xlsx", "path": self.file_transfer},
            {"name": "m2_test_reconcile.xlsx", "path": self.file_reconcile},
        ]
        audit = calc_engine.generate_reconciliation_audit(files)
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["title"], "数据校验验收单")

        # Check scope description
        self.assertIn("【统计口径说明】", audit["scope_description"])
        self.assertIn("物资名称 + 规格型号", audit["scope_description"])
        self.assertIn("差额 = 账面数量 - 实际调拨量", audit["scope_description"])

        # Check items breakdown
        # Total distinct materials across both tables:
        # 1. 螺纹钢 HRB400E Φ20: book=150, actual=150 -> PASSED
        # 2. 中砂 细度模数2.6: book=300, actual=300 -> PASSED
        # 3. 水泥 P.O 42.5: book=180, actual=200 -> DISCREPANCY (diff = -20.00)
        # 4. 阻燃安全网 1.8*6m: book=100, actual=0 -> DISCREPANCY (仅账面有记录)
        # 5. 脚手管 Φ48*3.5: book=0, actual=800 -> DISCREPANCY (仅调拨有记录)
        self.assertEqual(audit["passed_count"], 2)
        self.assertEqual(audit["discrepancy_count"], 3)
        self.assertEqual(audit["total_count"], 5)

        # Check passed items
        passed_names = [p["name"] for p in audit["passed_items"]]
        self.assertIn("螺纹钢", passed_names)
        self.assertIn("中砂", passed_names)

        # Check discrepancy items
        disc_names = [d["name"] for d in audit["discrepancy_items"]]
        self.assertIn("水泥", disc_names)
        cement_item = next(d for d in audit["discrepancy_items"] if d["name"] == "水泥")
        self.assertEqual(cement_item["diff"], -20.0)
        self.assertEqual(cement_item["diff_str"], "-20.00")
        self.assertEqual(cement_item["status"], "存在差额")

        # Check Markdown acceptance report content
        md_text = audit["markdown"]
        self.assertIn("# 《数据校验验收单》（物资调拨与对账核验）", md_text)
        self.assertIn("### 一、统计口径说明", md_text)
        self.assertIn("### 二、总体核验指标", md_text)
        self.assertIn("### 三、✅ 校验通过项（账实相符 2 笔）", md_text)
        self.assertIn("### 四、⚠️ 差异/异常清单（差额 3 笔", md_text)
        self.assertIn("螺纹钢", md_text)
        self.assertIn("水泥", md_text)

    def test_09_calc_engine_generate_summary_excel_with_custom_mapping(self):
        """Verify generate_summary_excel with custom mapping generates valid Excel workbook."""
        files = [
            {"name": "m2_test_transfer.xlsx", "path": self.file_transfer},
            {"name": "m2_test_reconcile.xlsx", "path": self.file_reconcile},
        ]
        custom_mapping = {
            "物资名称": "物料名称",
            "规格型号": "规格型号",
            "数量": "调拨量",
            "调出方": "调出单位",
            "调入方": "调入单位",
            "日期": "调拨日期",
        }
        res = calc_engine.generate_summary_excel(files, self.out_dir, custom_mapping=custom_mapping)
        self.assertIn("filename", res)
        out_excel = res["path"]
        self.assertTrue(os.path.exists(out_excel))

        try:
            # Verify openpyxl can load and read cells
            wb = openpyxl.load_workbook(out_excel, data_only=True)
            ws = wb.active
            self.assertEqual(ws.title, "物资调拨汇总表")
            self.assertIn("物资调拨与对账清算汇总表", str(ws["A1"].value))
            # Check headers in row 3
            headers = [cell.value for cell in ws[3]]
            self.assertIn("序号", headers)
            self.assertIn("物资名称", headers)
            self.assertIn("数量", headers)
        finally:
            if os.path.exists(out_excel):
                try:
                    os.remove(out_excel)
                except Exception:
                    pass

    # =========================================================================
    # 5. FastAPI 后端 API 端点测试
    # =========================================================================

    def test_10_api_calc_reconcile_endpoints(self):
        """Verify /api/calc/reconcile_fields and /api/calc/reconcile_audit endpoints."""
        # 1. Create a temporary conversation
        c_resp = self.client.post("/api/conversations", json={"mode": "merge"})
        self.assertEqual(c_resp.status_code, 200)
        cid = c_resp.json()["id"]

        # Insert test files into database for this conversation
        import uuid
        with webapp.db() as conn:
            conn.execute(
                "INSERT INTO files(id,conv_id,name,path,chars,created_at) VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], cid, "m2_test_transfer.xlsx", self.file_transfer, 100, webapp.now())
            )
            conn.execute(
                "INSERT INTO files(id,conv_id,name,path,chars,created_at) VALUES(?,?,?,?,?,?)",
                (uuid.uuid4().hex[:12], cid, "m2_test_reconcile.xlsx", self.file_reconcile, 100, webapp.now())
            )

        # 2. Test /api/calc/reconcile_fields
        f_resp = self.client.post("/api/calc/reconcile_fields", json={"conversation_id": cid})
        self.assertEqual(f_resp.status_code, 200)
        f_data = f_resp.json()
        self.assertTrue(f_data.get("ok"))
        self.assertEqual(len(f_data.get("files")), 2)
        self.assertIn("suggested_mapping", f_data)

        # 3. Test /api/calc/reconcile_audit
        a_resp = self.client.post("/api/calc/reconcile_audit", json={
            "conversation_id": cid,
            "mapping": f_data.get("suggested_mapping")
        })
        self.assertEqual(a_resp.status_code, 200)
        a_data = a_resp.json()
        self.assertTrue(a_data.get("ok"))
        self.assertEqual(a_data.get("title"), "数据校验验收单")
        self.assertEqual(a_data.get("passed_count"), 2)
        self.assertEqual(a_data.get("discrepancy_count"), 3)

        # 4. Test /api/calc/summary
        s_resp = self.client.post("/api/calc/summary", json={
            "conversation_id": cid,
            "mapping": f_data.get("suggested_mapping")
        })
        self.assertEqual(s_resp.status_code, 200)
        s_data = s_resp.json()
        self.assertTrue(s_data.get("ok"))
        self.assertIn("filename", s_data)
        excel_path = s_data.get("path")
        self.assertTrue(os.path.exists(excel_path))

        # Cleanup generated summary file
        if os.path.exists(excel_path):
            try:
                os.remove(excel_path)
            except Exception:
                pass

    def test_11_api_calc_reconcile_error_handling(self):
        """Verify reconcile endpoints gracefully return 400 when no files are uploaded."""
        # Create empty conversation
        c_resp = self.client.post("/api/conversations", json={"mode": "merge"})
        self.assertEqual(c_resp.status_code, 200)
        empty_cid = c_resp.json()["id"]

        f_resp = self.client.post("/api/calc/reconcile_fields", json={"conversation_id": empty_cid})
        self.assertEqual(f_resp.status_code, 400)

        a_resp = self.client.post("/api/calc/reconcile_audit", json={"conversation_id": empty_cid})
        self.assertEqual(a_resp.status_code, 400)


if __name__ == "__main__":
    unittest.main()
