# -*- coding: utf-8 -*-
r"""Phase 3 Comprehensive Test Suite:
Deterministic Pipelines for 供应商比选/比价 (mode: price) and 采购合同审查 (mode: review).

Verifies:
1. Python TCO Calculation Engine: Tax-incl/excl conversion, payment terms interest deduction,
   lowest price tagging, diff rate calculation, missing freight/delivery screening into unverified items,
   4-dimensional scoring weights (Price 40%, Delivery 20%, Payment 20%, Quality 20%), ranking & negotiation points.
2. Excel Export: 2 styled sheets (比价校验表 and 授标建议与谈判要点).
3. PPT Export: Native editable clustered column chart (XL_CHART_TYPE.COLUMN_CLUSTERED).
4. Contract Review Engine: 6 core clause libraries, 3-part acceptance report, KPI dashboard
   ([🔴 致命风险], [🟡 商务瑕疵], [⚪ 缺失条款], [🟢 合规项]), comparison table, missing clauses checklist.
5. Contract Review Exports: Word (.docx) and PPT (.pptx).
6. FastAPI Endpoints: /api/calc/price_compare, /api/calc/price_export, /api/calc/price_ppt,
   /api/calc/contract_review, /api/calc/contract_export, build_system_extra integration.
7. Frontend DOM & Controller Integrity: #pricePipeline and #reviewPipeline structures, controls,
   PricePipeline and ReviewPipeline in app.js, and CSS styling.

Run with:
    & "D:\AI\runtime\python\python.exe" D:\AI\test_phase3_pipelines.py
"""
import os
import sys
import unittest
import openpyxl
import pandas as pd
from pptx import Presentation
from pptx.enum.chart import XL_CHART_TYPE
from docx import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, "app")
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from fastapi.testclient import TestClient
import webapp
import core
import calc_engine


class TestPriceComparisonEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(BASE_DIR, "data", "test_tmp")
        os.makedirs(cls.test_dir, exist_ok=True)

        # Create sample supplier quotation files
        # Supplier A (Fast delivery, standard payment, competitive price, freight included)
        cls.file_supplier_a = os.path.join(cls.test_dir, "quote_supplier_a.xlsx")
        df_a = pd.DataFrame([
            {
                "物资名称": "螺纹钢",
                "规格型号": "HRB400E Φ20",
                "计量单位": "吨",
                "数量": 100,
                "含税单价": 3800.0,
                "账期": "月结60天",
                "交货期": "3天",
                "运费承担": "供方送货上门"
            },
            {
                "物资名称": "盘螺",
                "规格型号": "HRB400E Φ8-10",
                "计量单位": "吨",
                "数量": 50,
                "含税单价": 3950.0,
                "账期": "月结60天",
                "交货期": "3天",
                "运费承担": "供方包运"
            }
        ])
        df_a.to_excel(cls.file_supplier_a, index=False)

        # Supplier B (Lowest face price for 螺纹钢, but shorter payment, buyer pays freight)
        cls.file_supplier_b = os.path.join(cls.test_dir, "quote_supplier_b.xlsx")
        df_b = pd.DataFrame([
            {
                "物资名称": "螺纹钢",
                "规格型号": "HRB400E Φ20",
                "计量单位": "吨",
                "数量": 100,
                "含税单价": 3780.0,
                "账期": "货到验收后30天",
                "交货期": "7天",
                "运费承担": "需方自提"
            },
            {
                "物资名称": "盘螺",
                "规格型号": "HRB400E Φ8-10",
                "计量单位": "吨",
                "数量": 50,
                "含税单价": 4000.0,
                "账期": "货到验收后30天",
                "交货期": "7天",
                "运费承担": "需方自提"
            }
        ])
        df_b.to_excel(cls.file_supplier_b, index=False)

        # Supplier C (High price, prepayment trap, missing delivery date & freight)
        cls.file_supplier_c = os.path.join(cls.test_dir, "quote_supplier_c.xlsx")
        df_c = pd.DataFrame([
            {
                "物资名称": "螺纹钢",
                "规格型号": "HRB400E Φ20",
                "计量单位": "吨",
                "数量": 100,
                "含税单价": 4100.0,
                "账期": "预付30%，发货前付60%，质保金10%一年",
                "交货期": "未注明",
                "运费承担": ""
            },
            {
                "物资名称": "盘螺",
                "规格型号": "HRB400E Φ8-10",
                "计量单位": "吨",
                "数量": 50,
                "含税单价": 4200.0,
                "账期": "款到发货",
                "交货期": "",
                "运费承担": "待定"
            }
        ])
        df_c.to_excel(cls.file_supplier_c, index=False)

        cls.files = [
            {"name": "供方A报价.xlsx", "path": cls.file_supplier_a},
            {"name": "供方B报价.xlsx", "path": cls.file_supplier_b},
            {"name": "供方C报价.xlsx", "path": cls.file_supplier_c},
        ]

    def test_01_tco_tax_and_interest_calculation(self):
        """T1.1: Verify tax conversion and payment terms interest deduction formula."""
        res = calc_engine.calculate_supplier_price_comparison(
            self.files,
            tax_rate=0.13,
            annual_interest_rate=0.06
        )
        self.assertTrue(res.get("ok"), "TCO calculation returned ok=False")
        matrix = res.get("comparison_matrix", [])
        self.assertGreaterEqual(len(matrix), 6, "Expected at least 6 price items")

        # Verify tax conversion: price_excl == round(price_incl / 1.13, 2)
        for row in matrix:
            p_incl = row["price_incl"]
            p_excl = row["price_excl"]
            self.assertAlmostEqual(p_excl, round(p_incl / 1.13, 2), delta=0.02)

            # Verify interest calculation: p_incl * 0.06 * payment_days / 365
            expected_interest = round(p_incl * 0.06 * row["payment_days"] / 365.0, 2)
            self.assertAlmostEqual(row["capital_benefit"], expected_interest, delta=0.02)
            self.assertAlmostEqual(row["interest_adj"], expected_interest, delta=0.02)

            # Verify TCO price: price_incl - interest_adj + freight_adj
            expected_tco = round(p_incl - expected_interest + row["freight_adj"], 2)
            self.assertAlmostEqual(row["tco_price"], expected_tco, delta=0.02)

    def test_02_lowest_price_and_diff_rate(self):
        """T1.2: Verify lowest price tagging and differential rate calculation."""
        res = calc_engine.calculate_supplier_price_comparison(self.files)
        matrix = res.get("comparison_matrix", [])

        # Group by material & spec
        grouped = {}
        for row in matrix:
            key = (row["material"], row["spec"])
            grouped.setdefault(key, []).append(row)

        for key, items in grouped.items():
            lowest_item = min(items, key=lambda x: x["price_incl"])
            for row in items:
                if abs(row["price_incl"] - lowest_item["price_incl"]) < 0.001:
                    self.assertTrue(row["is_lowest"], f"{row['vendor']} should be marked is_lowest")
                    self.assertEqual(row["diff_rate"], 0.0, "Lowest item diff rate must be 0.0%")
                else:
                    self.assertFalse(row["is_lowest"])
                    expected_diff = round((row["price_incl"] - lowest_item["price_incl"]) / lowest_item["price_incl"] * 100.0, 2)
                    self.assertAlmostEqual(row["diff_rate"], expected_diff, delta=0.2)

    def test_03_unverified_items_screening(self):
        """T1.3: Verify missing delivery lead time and unstated freight screening into unverified items."""
        res = calc_engine.calculate_supplier_price_comparison(self.files)
        unverified = res.get("verification_items", []) or res.get("unverified_items", [])
        self.assertGreater(len(unverified), 0, "Supplier C missing fields must be screened into unverified items")

        c_issues = [u for u in unverified if "供方C" in u["vendor"]]
        self.assertGreaterEqual(len(c_issues), 2, "Supplier C must have at least 2 unverified issues")
        issue_types = {u["issue_type"] for u in c_issues}
        self.assertTrue(any("交期" in it for it in issue_types), "Missing lead time not flagged")
        self.assertTrue(any("运费" in it for it in issue_types), "Missing freight not flagged")

    def test_04_four_dimensional_scoring_and_ranking(self):
        """T1.4: Verify 4D weighted score matrix (Price, Delivery, Payment, Quality)."""
        custom_weights = {"price": 40, "delivery": 20, "payment": 20, "quality": 20}
        res = calc_engine.calculate_supplier_price_comparison(self.files, weights=custom_weights)
        scores = res.get("score_matrix", [])
        self.assertEqual(len(scores), 3, "Expected 3 suppliers evaluated")

        # Ranks must be 1, 2, 3 in descending order of total_score
        ranks = [s["rank"] for s in scores]
        self.assertEqual(ranks, [1, 2, 3])
        self.assertGreaterEqual(scores[0]["total_score"], scores[1]["total_score"])
        self.assertGreaterEqual(scores[1]["total_score"], scores[2]["total_score"])

        # Rank 1 must have recommendation '首选授标'
        self.assertIn("首选授标", scores[0]["recommendation"])
        # Supplier C with missing data and high price should be lowest ranked
        self.assertIn("供方C", scores[2]["vendor"])

    def test_05_negotiation_points_generation(self):
        """T1.5: Verify grounded negotiation points generated for each vendor."""
        res = calc_engine.calculate_supplier_price_comparison(self.files)
        nego = res.get("negotiation_points", [])
        self.assertEqual(len(nego), 3)

        for n in nego:
            self.assertTrue(len(n["strategy"]) > 20, "Strategy text too short")
            if n["rank"] == 1:
                self.assertIn("首选", n["strategy"])
            else:
                self.assertIn("压价", n["strategy"])

    def test_06_excel_export_2_sheets(self):
        """T1.6: Verify Excel export generates 2 styled sheets (比价校验表 & 授标建议与谈判要点)."""
        res = calc_engine.calculate_supplier_price_comparison(self.files)
        excel_res = calc_engine.generate_price_tco_excel(res, self.test_dir)
        self.assertTrue(excel_res.get("ok"))
        out_path = excel_res.get("path")
        self.assertTrue(os.path.isfile(out_path))

        wb = openpyxl.load_workbook(out_path)
        sheet_names = wb.sheetnames
        self.assertGreaterEqual(len(sheet_names), 2, "Excel must have at least 2 sheets")
        self.assertIn("比价校验表", sheet_names[0])
        self.assertIn("授标建议与谈判要点", sheet_names[1])

        # Inspect Sheet 1
        ws1 = wb[sheet_names[0]]
        self.assertGreater(ws1.max_row, 4, "Sheet 1 must contain data rows")
        # Check header contains TCO
        headers = [ws1.cell(3, c).value for c in range(1, ws1.max_column + 1)]
        self.assertTrue(any("TCO" in str(h) for h in headers), "Sheet 1 must have TCO column")

        # Inspect Sheet 2
        ws2 = wb[sheet_names[1]]
        self.assertGreater(ws2.max_row, 4, "Sheet 2 must contain ranking and negotiation rows")

    def test_07_ppt_export_with_native_column_chart(self):
        """T1.7: Verify PPT export generates valid presentation with native clustered column chart."""
        res = calc_engine.calculate_supplier_price_comparison(self.files)
        ppt_res = calc_engine.generate_price_tco_ppt(res, self.test_dir)
        self.assertTrue(ppt_res.get("ok"))
        out_path = ppt_res.get("path")
        self.assertTrue(os.path.isfile(out_path))

        prs = Presentation(out_path)
        self.assertGreaterEqual(len(prs.slides), 4, "Expected at least 4 slides in PPT")

        # Find native chart shape
        chart_found = False
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_chart:
                    chart = shape.chart
                    chart_found = True
                    self.assertEqual(chart.chart_type, XL_CHART_TYPE.COLUMN_CLUSTERED, "Chart type must be COLUMN_CLUSTERED")
                    self.assertIn("TCO", chart.chart_title.text_frame.text)
        self.assertTrue(chart_found, "Native clustered column chart shape not found in PPT")


class TestContractReviewEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_dir = os.path.join(BASE_DIR, "data", "test_tmp")
        os.makedirs(cls.test_dir, exist_ok=True)

        cls.dangerous_contract = (
            "工业品买卖框架合同\n"
            "第一条 付款方式：需方在签订合同后3个工作日内支付100%全额预付款，概不退还。\n"
            "第二条 违约责任：需方逾期付款的，每日按逾期金额的千分之五向供方支付违约金；"
            "供方因故延期交货的，免于承担一切赔偿责任。\n"
            "第三条 质量验收：标的物送达需方现场后24小时内未提出书面异议的，视为质量合格，需方放弃一切隐蔽瑕疵追偿权。\n"
            "第四条 知识产权：买方提供的原始技术图纸及双方合作开发之技术成果，其知识产权均归供方所有，供方不承担侵犯第三方知识产权责任。\n"
            "第五条 保密条款：买方对供方报价及商业信息负有严格保密义务，供方对买方信息无需保密。\n"
            "第六条 争议解决：因本合同履行发生争议的，双方协商解决，协商不成的，由供方所在地基层人民法院管辖。"
        )

        cls.compliant_contract = (
            "标准采购物资采购合同\n"
            "第一条 付款节点与发票：买方在标的物运抵现场经双方验收合格并签署验收报告后，"
            "且收到供方开具的税率13%增值税专用发票后支付进度款；留5%质保金于质保期满12个月后15个工作日内无息付清。\n"
            "第二条 违约责任对等：双方违约责任严格对等，供方逾期交货的，按日万分之五承担违约金；买方逾期付款的，按日万分之五承担逾期利息；"
            "任何一方违约金总额累计不超过合同总额的5%。\n"
            "第三条 质量验收标准：严格执行国家标准GB/T相关技术规范验收；买方在质保期12个月内对隐蔽瑕疵享有提出异议并要求负责保修、调换及赔偿的权利。\n"
            "第四条 知识产权保护：买方提供图纸资料及定制成果独家归买方所有；供方保证交付产品不侵犯第三方知识产权，如有纠纷由供方独立承担应诉及赔偿。\n"
            "第五条 商业秘密保护：双方对商务信息及技术成果负有严格保密义务，该保密义务持续5年且不因合同终止而失效。\n"
            "第六条 司法管辖：争议协商不成时，向买方所在地人民法院起诉。"
        )

    def test_01_six_clause_rules_completeness(self):
        """T2.1: Verify built-in CONTRACT_REVIEW_RULES has all 6 core categories with full metadata."""
        rules = calc_engine.CONTRACT_REVIEW_RULES
        self.assertEqual(len(rules), 6, "Must define exactly 6 core clause libraries")
        expected_ids = {"payment", "penalty", "quality", "ip", "confidentiality", "dispute"}
        rule_ids = {r["id"] for r in rules}
        self.assertEqual(expected_ids, rule_ids)

        for r in rules:
            self.assertIn("category", r)
            self.assertIn("standard_clause", r)
            self.assertIn("missing_warning", r)
            self.assertIn("missing_addition", r)
            self.assertGreater(len(r["fatal_patterns"]), 0)
            self.assertGreater(len(r["flaw_patterns"]), 0)
            self.assertGreater(len(r["compliance_patterns"]), 0)

    def test_02_dangerous_contract_detection(self):
        """T2.2: Verify high-risk contract triggers fatal risks (红灯项) across clauses."""
        res = calc_engine.analyze_contract_full(self.dangerous_contract)
        self.assertTrue(res.get("ok"))
        summary = res.get("summary", {})

        # Must flag multiple fatal risks
        fatal_cnt = summary.get("fatal_count", res.get("fatal_count", 0))
        self.assertGreaterEqual(fatal_cnt, 4, "Dangerous contract must trip at least 4 fatal risks")
        self.assertIn("高风险", res.get("rating", ""))

        table = res.get("comparison_table", [])
        fatal_entries = [t for t in table if t["risk_level_code"] == "fatal"]
        self.assertGreaterEqual(len(fatal_entries), 4)

        # Check specific fatal clauses caught
        fatal_cats = {t["category"] for t in fatal_entries}
        self.assertIn("付款节点与账期", fatal_cats)
        self.assertIn("延期交货违约金对等性", fatal_cats)
        self.assertIn("质量验收标准与异议期", fatal_cats)
        self.assertIn("争议解决与管辖法院", fatal_cats)

    def test_03_compliant_contract_detection(self):
        """T2.3: Verify compliant contract identifies green compliant clauses (绿灯项) and 0 fatal risks."""
        res = calc_engine.analyze_contract_full(self.compliant_contract)
        self.assertTrue(res.get("ok"))
        summary = res.get("summary", {})

        fatal_cnt = summary.get("fatal_count", res.get("fatal_count", 0))
        ok_cnt = summary.get("ok_count", res.get("compliant_count", 0))
        self.assertEqual(fatal_cnt, 0, "Compliant contract must have 0 fatal risks")
        self.assertGreaterEqual(ok_cnt, 4, "Compliant contract must identify at least 4 ok clauses")
        self.assertIn("低风险", res.get("rating", ""))

        table = res.get("comparison_table", [])
        ok_entries = [t for t in table if t["risk_level_code"] == "compliance"]
        self.assertGreaterEqual(len(ok_entries), 4)

    def test_04_missing_clauses_detection(self):
        """T2.4: Verify short contract missing IP, confidentiality & dispute resolution flags missing clauses."""
        short_contract = (
            "简易物资采购合同：甲方采购乙方轴承100套，单价500元，货到验收后30天内付款。"
            "供方逾期按每日0.05%承担违约金。"
        )
        res = calc_engine.analyze_contract_full(short_contract)
        missing = res.get("missing_clauses", []) or res.get("missing_list", [])
        self.assertGreaterEqual(len(missing), 3, "Short contract must report at least 3 missing clause categories")

        missing_cats = {m["category"] for m in missing}
        self.assertTrue({"知识产权归属", "保密义务", "争议解决与管辖法院"}.issubset(missing_cats))
        for m in missing:
            self.assertTrue(len(m["recommended_addition"]) > 10, "Missing clause must include recommended addition")

    def test_05_word_docx_export(self):
        """T2.5: Verify contract review Word export generates valid formatted .docx."""
        rev_res = calc_engine.analyze_contract_full(self.dangerous_contract)
        docx_res = calc_engine.generate_contract_review_docx(rev_res, self.test_dir)
        self.assertTrue(docx_res.get("ok"))
        out_path = docx_res.get("path")
        self.assertTrue(os.path.isfile(out_path))

        doc = Document(out_path)
        self.assertGreaterEqual(len(doc.paragraphs), 4, "Word document should contain paragraphs")
        self.assertGreaterEqual(len(doc.tables), 1, "Word document must have review tables")

    def test_06_pptx_export(self):
        """T2.6: Verify contract review PPT export generates executive risk slides."""
        rev_res = calc_engine.analyze_contract_full(self.dangerous_contract)
        ppt_res = calc_engine.generate_contract_review_pptx(rev_res, self.test_dir)
        self.assertTrue(ppt_res.get("ok"))
        out_path = ppt_res.get("path")
        self.assertTrue(os.path.isfile(out_path))

        prs = Presentation(out_path)
        self.assertGreaterEqual(len(prs.slides), 3, "Review PPT must contain at least 3 slides")


class TestFastApiPhase3Endpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(webapp.app)
        cls.test_dir = os.path.join(BASE_DIR, "data", "test_tmp")
        os.makedirs(cls.test_dir, exist_ok=True)

        cls.quote_file_1 = os.path.join(cls.test_dir, "api_quote1.xlsx")
        cls.quote_file_2 = os.path.join(cls.test_dir, "api_quote2.xlsx")
        pd.DataFrame([
            {"物资名称": "水泥", "规格型号": "P.O 42.5", "计量单位": "吨", "含税单价": 420.0, "账期": "月结60天", "交货期": "2天", "运费承担": "包运"}
        ]).to_excel(cls.quote_file_1, index=False)
        pd.DataFrame([
            {"物资名称": "水泥", "规格型号": "P.O 42.5", "计量单位": "吨", "含税单价": 435.0, "账期": "现结", "交货期": "5天", "运费承担": "自提"}
        ]).to_excel(cls.quote_file_2, index=False)

        cls.api_files = [
            {"name": "海螺水泥报价.xlsx", "path": cls.quote_file_1},
            {"name": "冀东水泥报价.xlsx", "path": cls.quote_file_2},
        ]

    def test_01_api_price_compare(self):
        """T3.1: POST /api/calc/price_compare returns structured TCO data."""
        resp = self.client.post("/api/calc/price_compare", json={
            "files": self.api_files,
            "weights": {"price": 40, "delivery": 20, "payment": 20, "quality": 20},
            "tax_rate": 0.13,
            "annual_interest_rate": 0.06
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("comparison_matrix", data)
        self.assertIn("score_matrix", data)
        self.assertIn("negotiation_points", data)

    def test_02_api_price_export_excel(self):
        """T3.2: POST /api/calc/price_export returns Excel artifact."""
        resp = self.client.post("/api/calc/price_export", json={
            "files": self.api_files,
            "tax_rate": 0.13
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("path").endswith(".xlsx"))
        self.assertTrue(os.path.isfile(data.get("path")))

    def test_03_api_price_ppt_export(self):
        """T3.3: POST /api/calc/price_ppt returns PPT artifact."""
        resp = self.client.post("/api/calc/price_ppt", json={
            "files": self.api_files
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        self.assertTrue(data.get("path").endswith(".pptx"))
        self.assertTrue(os.path.isfile(data.get("path")))

    def test_04_api_contract_review(self):
        """T3.4: POST /api/calc/contract_review returns 6-clause risk report."""
        resp = self.client.post("/api/calc/contract_review", json={
            "text": "合同条款：买方预付100%全款且概不退还。因合同引起的争议由供方所在地法院管辖。"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("ok"))
        fatal_cnt = data.get("summary", {}).get("fatal_count", data.get("fatal_count", 0))
        self.assertGreaterEqual(fatal_cnt, 2)
        self.assertIn("comparison_table", data)

    def test_05_api_contract_export_docx_and_pptx(self):
        """T3.5: POST /api/calc/contract_export supports docx and pptx formats."""
        text = "合同条款：买方预付100%款项。质保期内有异议供方48小时内到场处理。"
        resp_doc = self.client.post("/api/calc/contract_export", json={"text": text, "type": "doc"})
        self.assertEqual(resp_doc.status_code, 200)
        self.assertTrue(resp_doc.json()["path"].endswith(".docx"))

        resp_ppt = self.client.post("/api/calc/contract_export", json={"text": text, "type": "ppt"})
        self.assertEqual(resp_ppt.status_code, 200)
        self.assertTrue(resp_ppt.json()["path"].endswith(".pptx"))

    def test_06_build_system_extra_injections(self):
        """T3.6: Verify build_system_extra injects TCO matrix for price mode and 6-clause scan for review mode."""
        # Price mode extra
        price_extra = webapp.build_system_extra("price", self.api_files)
        self.assertIn("确定性比选与TCO计算基准", price_extra)
        self.assertIn("水泥", price_extra)

        # Review mode extra
        contract_file = os.path.join(self.test_dir, "contract_test.txt")
        with open(contract_file, "w", encoding="utf-8") as f:
            f.write("合同条款：预付100%货款。争议由供方所在地法院管辖。")
        review_extra = webapp.build_system_extra("review", [{"name": "contract_test.txt", "path": contract_file}])
        self.assertIn("确定性采购合同风控审查基准", review_extra)
        self.assertIn("致命风险", review_extra)


class TestFrontendPipelineIntegrity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP_DIR, "web", "index.html"), "r", encoding="utf-8", errors="ignore") as f:
            cls.index_html = f.read()
        with open(os.path.join(APP_DIR, "web", "app.js"), "r", encoding="utf-8", errors="ignore") as f:
            cls.app_js = f.read()
        with open(os.path.join(APP_DIR, "web", "style.css"), "r", encoding="utf-8", errors="ignore") as f:
            cls.style_css = f.read()

    def test_01_index_html_price_pipeline_dom(self):
        """T4.1: Verify #pricePipeline DOM elements and controls in index.html."""
        html = self.index_html
        self.assertIn('id="pricePipeline"', html)
        self.assertIn('id="pricePipelineStep1"', html)
        self.assertIn('id="pricePipelineStep2"', html)
        self.assertIn('id="pricePipelineStep3"', html)
        self.assertIn('id="pricePipelineStep4"', html)
        self.assertIn('id="sliderWeightPrice"', html)
        self.assertIn('id="sliderWeightDelivery"', html)
        self.assertIn('id="sliderWeightPayment"', html)
        self.assertIn('id="sliderWeightQuality"', html)
        self.assertIn('id="selectTaxRate"', html)
        self.assertIn('id="selectInterestRate"', html)
        self.assertIn('id="pricePipelineStep2NextBtn"', html)
        self.assertIn('id="priceExportExcelBtn"', html)
        self.assertIn('id="priceExportPptBtn"', html)
        self.assertIn('id="priceToReportBtn"', html)

    def test_02_index_html_review_pipeline_dom(self):
        """T4.2: Verify #reviewPipeline DOM elements and 6 clause cards in index.html."""
        html = self.index_html
        self.assertIn('id="reviewPipeline"', html)
        self.assertIn('id="reviewPipelineStep1"', html)
        self.assertIn('id="reviewPipelineStep2"', html)
        self.assertIn('id="reviewPipelineStep3"', html)
        self.assertIn('id="reviewPipelineStep4"', html)
        self.assertIn('id="reviewContractTextarea"', html)
        self.assertIn('id="reviewPipelineFileInput"', html)
        self.assertIn('id="reviewPipelineStep2NextBtn"', html)
        self.assertIn('id="reviewExportDocxBtn"', html)
        self.assertIn('id="reviewExportPptBtn"', html)
        self.assertIn('id="reviewToReportBtn"', html)
        # Check 6 core clauses mentioned in step 2
        for clause in ["付款节点与账期", "延期交货违约金", "质量验收标准与异议期", "知识产权归属", "保密义务", "争议解决与管辖法院"]:
            self.assertIn(clause, html)

    def test_03_app_js_controllers_and_switching(self):
        """T4.3: Verify PricePipeline and ReviewPipeline controllers and pipeline close/switch logic in app.js."""
        js = self.app_js
        self.assertIn("const PricePipeline = {", js)
        self.assertIn("const ReviewPipeline = {", js)
        self.assertIn("closeAllPipelines", js)
        self.assertIn("openPricePipeline", js)
        self.assertIn("openReviewPipeline", js)
        self.assertIn("runPriceCompareAndRender", js)
        self.assertIn("runContractReviewAndRender", js)
        self.assertIn("executePriceExportExcel", js)
        self.assertIn("executePriceExportPpt", js)
        self.assertIn("executeReviewExportDocx", js)
        self.assertIn("sendPriceToReportWorkflow", js)
        self.assertIn("sendReviewToReportWorkflow", js)

    def test_04_style_css_rules(self):
        """T4.4: Verify CSS classes for parameter grid, badges, and audit tables."""
        css = self.style_css
        self.assertIn(".params-config-grid", css)
        self.assertIn(".slider-weight", css)
        self.assertIn(".review-rules-grid", css)
        self.assertIn(".badge-risk", css)
        self.assertIn(".badge-risk.red", css)
        self.assertIn(".badge-risk.yellow", css)
        self.assertIn(".badge-risk.green", css)


if __name__ == "__main__":
    unittest.main()
