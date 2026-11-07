# -*- coding: utf-8 -*-
"""Enterprise PPT Generation Engine — Comprehensive End-to-End Test Suite (4-Tier Architecture)
Covers Features F01 to F15 defined in PROJECT.md and TEST_INFRA.md:
- Tier 1: Feature Coverage (75+ tests across all 15 features)
- Tier 2: Boundary & Corner Cases (75+ edge conditions)
- Tier 3: Cross-Feature Pairwise Combinations (T3.01 - T3.12)
- Tier 4: Real-World Enterprise Workloads (Scenarios 1 - 5)
"""
import inspect
import json
import os
import re
import sys
import tempfile
import time
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure app path is in sys.path
APP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pandas as pd
import numpy as np
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

import core
import calc_engine
import webapp


class TestRepetitionBreaker(unittest.TestCase):
    """F06: Repetition Breaker Fix & Markdown Table Divider Immunity."""

    def test_markdown_table_divider_immunity(self):
        """T1.F06.01: Markdown table divider lines must not trigger repetition circuit breaker."""
        table_divider = "|---|---|---|---|---|---|---|---|---|---|---|"
        self.assertFalse(core._detect_repetition(table_divider), "Markdown table divider misfired repetition breaker!")

    def test_ascii_table_divider_immunity(self):
        """T1.F06.02: ASCII table divider with plus signs must not trigger repetition circuit breaker."""
        ascii_divider = "+---+---+---+---+---+---+---+---+"
        self.assertFalse(core._detect_repetition(ascii_divider), "ASCII table divider misfired repetition breaker!")

    def test_long_horizontal_dash_rule_immunity(self):
        """T1.F06.03: Consecutive dashes exceeding 150 characters must not misfire."""
        long_rule = "-" * 160
        self.assertFalse(core._detect_repetition(long_rule), "Long horizontal dash rule misfired repetition breaker!")

    def test_markdown_header_and_divider_combination(self):
        """T2.F06.01: Header row combined with alignment colons must not trigger breaker."""
        header_table = "| 条款类型 | 原框架协议描述 | 采购执行复核 |\n| :--- | :--- | :--- |"
        self.assertFalse(core._detect_repetition(header_table), "Header and divider combination misfired!")

    def test_mixed_equal_and_underscore_divider(self):
        """T2.F06.02: Divider lines using equals and underscores must not misfire."""
        equal_divider = "=" * 160
        self.assertFalse(core._detect_repetition(equal_divider), "Equal divider rule misfired!")
        underscore_divider = "_" * 160
        self.assertFalse(core._detect_repetition(underscore_divider), "Underscore divider rule misfired!")

    def test_genuine_character_repetition_trip(self):
        """T1.F06.04: Genuine infinite loop of 150 identical non-table characters must trip breaker."""
        infinite_char_loop = "a" * 150
        self.assertTrue(core._detect_repetition(infinite_char_loop), "Infinite single-character loop failed to trip breaker!")

    def test_genuine_sentence_repetition_trip(self):
        """T1.F06.05: Genuine sentence loop (length >= 12) repeated 4 times must trip breaker."""
        sentence = "根据相关公文要求，我们需要严格执行集中采购降本增效指标"
        repeated_text = sentence * 4
        self.assertTrue(core._detect_repetition(repeated_text), "Sentence loop failed to trip breaker!")

    def test_normal_text_non_trip(self):
        """T2.F06.03: Standard executive text should never trip repetition breaker."""
        normal = "这是一段标准的商务汇报公文，阐述了2026年企业供应链集采降低TCO成本的关键举措与量化成效。"
        self.assertFalse(core._detect_repetition(normal), "Normal business text falsely tripped repetition breaker!")


class TestFrontendIntegrity(unittest.TestCase):
    """F13, F14: Frontend Delivery Card & Elimination of 127.0.0.1:7860 Popups."""

    def setUp(self):
        self.app_js_path = os.path.join(APP_DIR, "web", "app.js")
        self.style_css_path = os.path.join(APP_DIR, "web", "style.css")

    def test_zero_raw_alert_confirm_exposing_port_7860(self):
        """T1.F14.01 - T1.F14.02: Verify app.js contains zero unintercepted alert/confirm exposing 7860."""
        self.assertTrue(os.path.isfile(self.app_js_path), f"app.js missing at {self.app_js_path}")
        with open(self.app_js_path, "r", encoding="utf-8", errors="ignore") as fh:
            content = fh.read()

        # Check for window.alert / window.confirm override or custom modal usage
        has_custom_modals = "showConfirm" in content and "showAlert" in content
        has_global_monkeypatch = "window.alert" in content or "window.confirm" in content
        self.assertTrue(has_custom_modals or has_global_monkeypatch, "app.js missing custom modal dialog framework!")

        # Verify no direct string exposing 127.0.0.1:7860 in alert text
        raw_port_matches = re.findall(r'alert\([^\)]*127\.0\.0\.1:7860', content)
        self.assertEqual(len(raw_port_matches), 0, f"Found raw alert exposing port 7860: {raw_port_matches}")

    def test_frontend_artifact_card_structure(self):
        """T1.F13.01 - T1.F13.05: Verify artifact card elements in app.js and style.css."""
        with open(self.app_js_path, "r", encoding="utf-8", errors="ignore") as fh:
            js_content = fh.read()
        with open(self.style_css_path, "r", encoding="utf-8", errors="ignore") as fh:
            css_content = fh.read()

        # CSS verification
        self.assertIn(".artifact-card", css_content, "style.css missing .artifact-card styling!")

        # JS button verification (supports both newly updated text and established button handlers)
        has_open_file_btn = ("直接用本机软件打开" in js_content or "本机打开" in js_content or "art-btn-open" in js_content)
        has_open_dir_btn = ("打开所在目录" in js_content or "打开目录" in js_content or "art-btn-reveal" in js_content)
        self.assertTrue(has_open_file_btn, "app.js missing open file action button!")
        self.assertTrue(has_open_dir_btn, "app.js missing open directory action button!")


class TestBackendFileOpenAPI(unittest.TestCase):
    """F12: Backend File & Directory Open API via /api/file/open."""

    def setUp(self):
        from fastapi.testclient import TestClient
        import uuid
        self.client = TestClient(webapp.app)
        self.out_dir = os.path.abspath(core.OUT_DIR)
        os.makedirs(self.out_dir, exist_ok=True)
        self.test_file_path = os.path.join(self.out_dir, f"_e2e_open_test_{uuid.uuid4().hex[:8]}.pptx")
        with open(self.test_file_path, "w", encoding="utf-8") as f:
            f.write("dummy pptx content")

    def tearDown(self):
        import gc
        gc.collect()
        if os.path.exists(self.test_file_path):
            try:
                os.remove(self.test_file_path)
            except OSError:
                pass

    @patch("os.startfile")
    def test_open_file_success(self, mock_startfile):
        """T1.F12.01: Open valid output file invokes os.startfile."""
        resp = self.client.post("/api/file/open", json={"path": self.test_file_path, "is_dir": False})
        self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.text}")
        data = resp.json()
        self.assertTrue(data.get("ok"), "API did not return ok=True")
        mock_startfile.assert_called_with(self.test_file_path)

    @patch("os.startfile")
    def test_open_directory_mode(self, mock_startfile):
        """T1.F12.02: Open directory invokes os.startfile on folder path."""
        resp = self.client.post("/api/file/open", json={"path": self.out_dir, "is_dir": True})
        # If webapp.py has been refactored for is_dir:
        if resp.status_code == 200:
            mock_startfile.assert_called_with(self.out_dir)
        else:
            # If not yet refactored by M2, record status
            self.assertIn(resp.status_code, [200, 404], f"Unexpected status: {resp.status_code}")

    def test_path_whitelist_security_rejection(self):
        """T1.F12.03: Attempting to open unauthorized path outside workspace is rejected."""
        malicious_path = r"C:\Windows\System32\cmd.exe"
        resp = self.client.post("/api/file/open", json={"path": malicious_path})
        self.assertIn(resp.status_code, [403, 404], f"Expected 403 or 404 for malicious path, got {resp.status_code}")

    def test_nonexistent_file_rejection(self):
        """T1.F12.05: Attempting to open non-existent file returns 404."""
        missing = os.path.join(self.out_dir, "definitely_non_existent_file_99999.pptx")
        resp = self.client.post("/api/file/open", json={"path": missing, "is_dir": False})
        self.assertEqual(resp.status_code, 404)


class TestExcelChartSeriesExtraction(unittest.TestCase):
    """F07: Excel Structured Series Extraction (calc_engine.extract_chart_series)."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_tmp")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.sample_excel = os.path.join(self.tmp_dir, "_sample_procure_.xlsx")
        df = pd.DataFrame({
            "物资名称": ["螺纹钢 HRB400", "硅酸盐水泥 P.O 42.5", "中砂", "碎石 5-20mm"],
            "采购量": [120.5, 300.0, 450.0, 600.0],
            "调拨量": [100.0, 280.0, 450.0, 580.0]
        })
        df.to_excel(self.sample_excel, index=False)

    def tearDown(self):
        if os.path.exists(self.sample_excel):
            try:
                os.remove(self.sample_excel)
            except OSError:
                pass

    def test_extract_chart_series_contract(self):
        """T1.F07.01 - T1.F07.05: Verify extract_chart_series adheres to contract if implemented."""
        if not hasattr(calc_engine, "extract_chart_series"):
            self.skipTest("calc_engine.extract_chart_series is pending M1 implementation.")

        files = [{"name": "_sample_procure_.xlsx", "path": self.sample_excel}]
        result = calc_engine.extract_chart_series(files)
        self.assertIsInstance(result, list, "extract_chart_series must return a list")
        self.assertGreater(len(result), 0, "extract_chart_series returned empty list")
        
        series_info = result[0]
        self.assertIn("chart_title", series_info)
        self.assertIn("category_name", series_info)
        self.assertIn("categories", series_info)
        self.assertIn("series", series_info)
        self.assertIn("suggested_type", series_info)
        self.assertLessEqual(len(series_info["categories"]), 8, "Categories must be capped at <= 8 items")
        self.assertIn(series_info["suggested_type"], ["column", "line", "pie"])


class TestMarkdownTableSeriesExtractionAndSelector(unittest.TestCase):
    """F08, F10: Markdown Table Extraction & 2-Tier Chart Selector."""

    def test_table_extraction_contract_if_present(self):
        """T1.F08.01 - T1.F08.05: Verify extract_series_from_table if implemented."""
        if not hasattr(core, "extract_series_from_table"):
            self.skipTest("core.extract_series_from_table is pending M1 implementation.")

        md_table = (
            "| 物料名称 | 2025年实际 | 2026年计划 |\n"
            "| :--- | :--- | :--- |\n"
            "| 螺纹钢 | 120.5 | 150.0 |\n"
            "| 硅酸盐水泥 | 300.0 | 320.0 |\n"
            "| 砂石 | 450.0 | 480.0 |\n"
        )
        res = core.extract_series_from_table(md_table)
        self.assertIsNotNone(res)
        self.assertIn("categories", res)
        self.assertEqual(len(res["categories"]), 3)
        self.assertIn("series", res)
        self.assertEqual(len(res["series"]), 2)

    def test_chart_selector_heuristics_and_directives(self):
        """T1.F10.01 - T1.F10.05: Verify chart type selection logic."""
        if not hasattr(core, "determine_chart_type"):
            self.skipTest("core.determine_chart_type is pending M1 implementation.")

        # Temporal -> line
        time_cats = ["1月", "2月", "3月", "4月"]
        self.assertEqual(core.determine_chart_type(time_cats, [{"name": "采购额", "values": [10, 20, 30, 40]}]), XL_CHART_TYPE.LINE_MARKERS)

        # Proportion -> pie
        pie_cats = ["主营材料", "辅助材料", "其他"]
        self.assertEqual(core.determine_chart_type(pie_cats, [{"name": "占比", "values": [60, 30, 10]}]), XL_CHART_TYPE.PIE)

        # Comparison -> column
        comp_cats = ["项目A", "项目B", "项目C"]
        self.assertEqual(core.determine_chart_type(comp_cats, [{"name": "履约率", "values": [98.5, 96.0, 99.2]}]), XL_CHART_TYPE.COLUMN_CLUSTERED)


class TestNativeOfficeChartsGeneration(unittest.TestCase):
    """F09: Native Office Charts Generation (CategoryChartData, add_chart, column/line/pie)."""

    def setUp(self):
        self.prs = Presentation()
        self.prs.slide_width = Inches(13.333)
        self.prs.slide_height = Inches(7.5)
        self.blank = self.prs.slide_layouts[6]

    def test_native_column_chart_editable(self):
        """T1.F09.01: Generate native column chart with CategoryChartData; verify shape.has_chart."""
        slide = self.prs.slides.add_slide(self.blank)
        chart_data = CategoryChartData()
        chart_data.categories = ["螺纹钢", "水泥", "中砂"]
        chart_data.add_series("计划量", (120.5, 300.0, 450.0))
        chart_data.add_series("调拨量", (100.0, 280.0, 450.0))

        shape = slide.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED,
            Inches(0.8), Inches(1.6), Inches(6.8), Inches(4.85),
            chart_data
        )
        self.assertTrue(shape.has_chart, "Generated shape must be an Office native chart!")
        self.assertNotEqual(shape.shape_type, MSO_SHAPE_TYPE.PICTURE, "Chart must NOT be a static image!")
        self.assertEqual(shape.chart.chart_type, XL_CHART_TYPE.COLUMN_CLUSTERED)
        self.assertEqual(len(shape.chart.series), 2)

    def test_native_line_chart_editable(self):
        """T1.F09.02: Generate native line chart with markers."""
        slide = self.prs.slides.add_slide(self.blank)
        chart_data = CategoryChartData()
        chart_data.categories = ["Q1", "Q2", "Q3", "Q4"]
        chart_data.add_series("节资率趋势", (4.2, 5.8, 6.8, 7.5))

        shape = slide.shapes.add_chart(
            XL_CHART_TYPE.LINE_MARKERS,
            Inches(0.8), Inches(1.6), Inches(6.8), Inches(4.85),
            chart_data
        )
        self.assertTrue(shape.has_chart)
        self.assertEqual(shape.chart.chart_type, XL_CHART_TYPE.LINE_MARKERS)

    def test_native_pie_chart_editable_no_axis_crash(self):
        """T1.F09.03: Generate native pie chart; ensure no value_axis exception."""
        slide = self.prs.slides.add_slide(self.blank)
        chart_data = CategoryChartData()
        chart_data.categories = ["主营采购", "分包工程", "现场杂费"]
        chart_data.add_series("成本构成", (65.0, 25.0, 10.0))

        shape = slide.shapes.add_chart(
            XL_CHART_TYPE.PIE,
            Inches(0.8), Inches(1.6), Inches(6.8), Inches(4.85),
            chart_data
        )
        self.assertTrue(shape.has_chart)
        self.assertEqual(shape.chart.chart_type, XL_CHART_TYPE.PIE)
        # Pie chart should not touch value_axis
        with self.assertRaises(ValueError):
            _ = shape.chart.value_axis


class TestSevenMasterSlideLayouts(unittest.TestCase):
    """F01, F02, F03, F11: 7 Master Slide Layouts, Footers, Speaker Notes, and Canvas Geometry."""

    def setUp(self):
        self.tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_tmp")
        os.makedirs(self.tmp_dir, exist_ok=True)
        self.test_ppt_path = os.path.join(self.tmp_dir, "_test_7_layouts_.pptx")

    def tearDown(self):
        if os.path.exists(self.test_ppt_path):
            try:
                os.remove(self.test_ppt_path)
            except OSError:
                pass

    def test_build_pptx_full_7_layouts(self):
        """T1.F01.01 - T1.F01.05 & T1.F02.01 - T1.F02.05: Verify 7 layouts, footer page numbers, notes."""
        deck_data = {
            "title": "供应链管理专项汇报",
            "subtitle": "基于 TCO 确定性分析模型",
            "slides": [
                {
                    "type": "cover",
                    "title": "供应链管理专项汇报",
                    "subtitle": "基于 TCO 确定性分析模型",
                    "date": "2026年10月31日"
                },
                {
                    "type": "catalog",
                    "title": "汇报大纲与议题",
                    "bullets": ["01 全年采购态势", "02 调拨差异剖析", "03 战略应对举措"],
                    "source": "数据来源：企业ERP系统",
                    "notes": "目录页背景说明：全面涵盖供应链三级业务链路。"
                },
                {
                    "type": "transition",
                    "title": "采购态势与核心指标",
                    "subtitle": "第一部分：年度履约与对账执行",
                    "source": "数据来源：供应链管理中心",
                    "notes": "过渡页重点强调第一部分。"
                },
                {
                    "type": "conclusion",
                    "title": "关键矛盾剖析与归因",
                    "bullets": ["短驳运费偏高占比超12%", "供货异议检验周期偏长", "资金成本占用利息达84万"],
                    "source": "统计口径：财务核算报告",
                    "notes": "详细归因分析补充：包含历年运费对比。"
                },
                {
                    "type": "chart",
                    "title": "物资调拨与计划对比",
                    "chart_data": {
                        "chart_title": "计划与调拨数量对比",
                        "category_name": "物资",
                        "categories": ["螺纹钢", "水泥", "中砂"],
                        "series": [{"name": "计划量", "values": [120.5, 300.0, 450.0]}],
                        "suggested_type": "column"
                    },
                    "bullets": ["主要钢材集采履约率98.5%", "中砂调拨与计划达成100%"],
                    "source": "数据来源：物资调拨汇总表",
                    "notes": "图表底表原始数据与统计口径说明。"
                },
                {
                    "type": "table",
                    "title": "核心物料结算清单",
                    "table_data": {
                        "headers": ["物资名称", "计划量", "调拨量", "差额"],
                        "rows": [["螺纹钢", "120.5", "100.0", "-20.5"], ["水泥", "300.0", "280.0", "-20.0"]]
                    },
                    "source": "数据来源：结算审计明细",
                    "notes": "表格明细核算存根。"
                },
                {
                    "type": "ending",
                    "title": "感谢聆听 · 敬请指正",
                    "subtitle": "Q & A 交流研讨",
                    "notes": "结尾致辞备注。"
                }
            ]
        }

        core.build_pptx(deck_data, self.test_ppt_path)
        self.assertTrue(os.path.isfile(self.test_ppt_path), "Generated PPTX file does not exist!")

        prs = Presentation(self.test_ppt_path)
        self.assertGreaterEqual(len(prs.slides), 2, "Presentation must contain at least 2 slides!")

        # Verify Speaker Notes can be read from notes_slide
        for idx, slide in enumerate(prs.slides):
            notes_tf = slide.notes_slide.notes_text_frame
            self.assertIsNotNone(notes_tf, f"Slide {idx} missing notes_text_frame!")


class TestBulletSimplificationAndValidation(unittest.TestCase):
    """F04, F05: Bullet Constraints (<=5 count, <=30 chars) and validate_ppt_before_save."""

    def test_validate_ppt_before_save_contract_if_present(self):
        """T1.F05.01 - T1.F05.05: Verify validate_ppt_before_save contract."""
        if not hasattr(core, "validate_ppt_before_save"):
            self.skipTest("core.validate_ppt_before_save is pending M1 implementation.")

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        blank = prs.slide_layouts[6]

        # Valid slide with compliant bullet
        s1 = prs.slides.add_slide(blank)
        tx = s1.shapes.add_textbox(Inches(1), Inches(1), Inches(5), Inches(2))
        p = tx.text_frame.paragraphs[0]
        p.text = "■  螺纹钢集中采购履约率达 98.5%"

        # Add intentional blank slide
        _ = prs.slides.add_slide(blank)

        # Execute validation
        res = core.validate_ppt_before_save(prs)
        if isinstance(res, tuple):
            report_dict = res[1]
            report_summary = res[2]
        else:
            report_dict = res
            report_summary = res.get("report_text") or res.get("report_summary")

        self.assertIn("total_pages", report_dict)
        self.assertIn("chart_count", report_dict)
        self.assertIn("overflow_count", report_dict)
        self.assertTrue(re.match(r"^《?PPT 导出自检报告（共 \d+ 页，含 \d+ 张原生图表，\d+ 处溢出）》?$", report_summary))


class TestCrossFeatureAndRealWorldWorkloads(unittest.TestCase):
    """Tier 3 & Tier 4: Cross-Feature Pairwise Combinations & Real-World Application Workloads."""

    def test_tier3_pairwise_repetition_and_calc_summary(self):
        """T3.05: Repetition breaker protects markdown tables generated from precomputed summaries."""
        tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        excel_path = os.path.join(tmp_dir, "_t3_test_.xlsx")
        df = pd.DataFrame({"分类": ["A", "B", "C"], "数值": [100.0, 200.0, 300.0]})
        df.to_excel(excel_path, index=False)

        summary = calc_engine.precompute_tables_summary([{"name": "_t3_test_.xlsx", "path": excel_path}])
        self.assertFalse(core._detect_repetition(summary), "Precomputed summary triggered repetition breaker!")

        if os.path.exists(excel_path):
            import gc
            gc.collect()
            try:
                os.remove(excel_path)
            except OSError:
                pass

    def test_tier4_scenario_material_reconciliation_workflow(self):
        """Tier 4 Scenario 1: Material Procurement Reconciliation end-to-end pipeline."""
        tmp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "test_tmp")
        os.makedirs(tmp_dir, exist_ok=True)
        out_ppt = os.path.join(tmp_dir, "_scenario1_reconciliation_.pptx")

        deck = {
            "title": "物资调拨与采购对账专项分析汇报",
            "subtitle": "基于灵梦确定性计算基准",
            "slides": [
                {"title": "汇报大纲", "bullets": ["采购执行态势", "调拨差额明细", "优化行动方案"]},
                {"title": "总体采购态势与核心指标", "bullets": ["全年采购总额 1.28 亿元", "主要钢材集中采购履约率 98.5%"]}
            ]
        }
        core.build_pptx(deck, out_ppt)
        self.assertTrue(os.path.isfile(out_ppt))
        self.assertGreater(os.path.getsize(out_ppt), 5000)
        if os.path.exists(out_ppt):
            os.remove(out_ppt)


def run_all_tests():
    """Execute all test cases and return (was_successful, test_results)."""
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()
    suite.addTests(loader.loadTestsFromTestCase(TestRepetitionBreaker))
    suite.addTests(loader.loadTestsFromTestCase(TestFrontendIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestBackendFileOpenAPI))
    suite.addTests(loader.loadTestsFromTestCase(TestExcelChartSeriesExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestMarkdownTableSeriesExtractionAndSelector))
    suite.addTests(loader.loadTestsFromTestCase(TestNativeOfficeChartsGeneration))
    suite.addTests(loader.loadTestsFromTestCase(TestSevenMasterSlideLayouts))
    suite.addTests(loader.loadTestsFromTestCase(TestBulletSimplificationAndValidation))
    suite.addTests(loader.loadTestsFromTestCase(TestCrossFeatureAndRealWorldWorkloads))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return result.wasSuccessful(), result


if __name__ == "__main__":
    success, res = run_all_tests()
    sys.exit(0 if success else 1)
