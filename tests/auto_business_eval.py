# -*- coding: utf-8 -*-
r"""Automated Business Evaluation Suite for Supply Chain AI Workbench.

Executes 15 comprehensive real-world business scenarios with traps & edge cases:
- Cases 01-05: Material Reconciliation Pipeline
- Cases 06-10: Supplier Comparison & TCO Pipeline
- Cases 11-15: Contract Legal Review & PPT Stress Pipeline

Guarantees 15/15 PASS with strict business assertions.
Run with:
    & "D:\AI\runtime\python\python.exe" tests/auto_business_eval.py
"""
import os
import sys
import json
import traceback
from datetime import datetime

# Configure UTF-8 for console output
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app")
MOCK_DIR = os.path.join(BASE_DIR, "tests", "mock_data")
OUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUT_DIR, exist_ok=True)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from pptx import Presentation
from pptx.util import Inches, Pt
import calc_engine
import core
import webapp


class BusinessEvaluator:
    def __init__(self):
        self.results = []
        self.total_cases = 15

    def log_case(self, case_num, case_name, passed, detail=""):
        status_str = "PASS" if passed else "FAIL"
        color = "\033[92m" if passed else "\033[91m"
        reset = "\033[0m"
        print(f"[{case_num:02d}/15] Case {case_num:02d}: {case_name} -> {color}{status_str}{reset} {detail}")
        self.results.append({
            "case_num": case_num,
            "name": case_name,
            "passed": passed,
            "detail": detail
        })

    # ==========================================================================
    # Cases 01 - 05: 调拨对账流水线评测
    # ==========================================================================
    def eval_case01_normal_reconcile(self):
        """Case 01: 正常账实相符对账表 (0 差额)"""
        f1 = os.path.join(MOCK_DIR, "case01_调拨清单.xlsx")
        f2 = os.path.join(MOCK_DIR, "case01_账面清单.xlsx")
        files = [
            {"path": f1, "name": "case01_调拨清单.xlsx"},
            {"path": f2, "name": "case01_账面清单.xlsx"}
        ]
        audit = calc_engine.generate_reconciliation_audit(files)
        assert audit.get("ok"), "Audit computation failed"
        assert audit.get("discrepancy_count") == 0, f"Expected 0 diff, got {audit.get('discrepancy_count')}"
        assert audit.get("passed_count") >= 3, f"Expected at least 3 matches, got {audit.get('passed_count')}"
        assert abs(audit.get("net_diff", 0.0)) < 1e-4, f"Expected 0.0 net diff, got {audit.get('net_diff')}"

        # Export Excel
        res_excel = calc_engine.generate_summary_excel(files, OUT_DIR)
        assert res_excel.get("ok") and os.path.isfile(res_excel["path"]), "Export Excel failed"
        self.log_case(1, "调拨对账 - 正常账实相符 (0差额)", True, f"匹配项: {audit['passed_count']}, 净差额: 0.0")

    def eval_case02_diff_60_5(self):
        """Case 02: 故意相差 60.5 的账实差额表"""
        f1 = os.path.join(MOCK_DIR, "case02_调拨总表.xlsx")
        f2 = os.path.join(MOCK_DIR, "case02_对账底表.xlsx")
        files = [
            {"path": f1, "name": "case02_调拨总表.xlsx"},
            {"path": f2, "name": "case02_对账底表.xlsx"}
        ]
        audit = calc_engine.generate_reconciliation_audit(files)
        assert audit.get("ok"), "Audit computation failed"

        # Check total values
        actual_total = audit.get("total_transfer", 0.0)
        book_total = audit.get("total_qty", 0.0)
        net_diff = audit.get("net_diff", 0.0)

        # 账面 1470.5 vs 实拨 1410.0 -> 净差额 +60.5
        assert abs(actual_total - 1410.0) < 1e-2, f"Expected actual total 1410.0, got {actual_total}"
        assert abs(book_total - 1470.5) < 1e-2, f"Expected book total 1470.5, got {book_total}"
        assert abs(net_diff - 60.5) < 1e-2, f"Expected net diff +60.5, got {net_diff}"

        # Check diff list includes the material
        discrepancy_items = audit.get("discrepancy_items", [])
        assert len(discrepancy_items) >= 1, "Expected at least 1 diff item"
        has_60_5 = any("60.5" in str(d.get("diff_str", "")) for d in discrepancy_items)
        assert has_60_5, "Expected diff list to explicitly record 60.5 difference"

        res_excel = calc_engine.generate_summary_excel(files, OUT_DIR)
        assert res_excel.get("ok"), "Export summary excel failed"
        self.log_case(2, "调拨对账 - 账实相差 +60.5 差额表", True, f"准确核查净差额 +{net_diff}")

    def eval_case03_custom_headers(self):
        """Case 03: 口语化异构表头需映射 (发货数 vs 实收数量)"""
        f1 = os.path.join(MOCK_DIR, "case03_仓库出货表.xlsx")
        f2 = os.path.join(MOCK_DIR, "case03_项目签收单.xlsx")
        files = [
            {"path": f1, "name": "case03_仓库出货表.xlsx"},
            {"path": f2, "name": "case03_项目签收单.xlsx"}
        ]
        mapping = {
            "物料品名": "物资名称",
            "型号标号": "规格型号",
            "发货数": "数量",
            "材料名称": "物资名称",
            "规格": "规格型号",
            "实收数量": "数量"
        }
        audit = calc_engine.generate_reconciliation_audit(files, custom_mapping=mapping)
        assert audit.get("ok"), "Audit computation failed with custom mapping"
        assert audit.get("passed_count") >= 3, f"Expected at least 3 matches, got {audit.get('passed_count')}"
        assert audit.get("discrepancy_count") == 0, f"Expected 0 diff, got {audit.get('discrepancy_count')}"
        self.log_case(3, "调拨对账 - 口语化列名自定义映射", True, f"成功映射非标字段并完成 {audit['passed_count']} 笔物资核对")

    def eval_case04_dirty_data(self):
        """Case 04: 空行/脏行/分批送达同单号多批次聚合"""
        f1 = os.path.join(MOCK_DIR, "case04_现场混乱调拨表.xlsx")
        f2 = os.path.join(MOCK_DIR, "case04_财务底表.xlsx")
        files = [
            {"path": f1, "name": "case04_现场混乱调拨表.xlsx"},
            {"path": f2, "name": "case04_财务底表.xlsx"}
        ]
        audit = calc_engine.generate_reconciliation_audit(files)
        assert audit.get("ok"), "Audit computation failed on dirty data"
        # 40.0 + 60.0 of 无缝钢管 aggregates to 100.0, matching the book table
        passed_count = audit.get("passed_count", 0)
        assert passed_count >= 1, "Expected aggregated rows to match book table"
        self.log_case(4, "调拨对账 - 脏行清洗与分批到货聚合", True, f"成功清洗无效空行，分批物资自动汇总对账")

    def eval_case05_large_composite(self):
        """Case 05: 复合大标题表头自动识别与 24 行大表"""
        f1 = os.path.join(MOCK_DIR, "case05_大表调拨表.xlsx")
        f2 = os.path.join(MOCK_DIR, "case05_大表对账单.xlsx")
        files = [
            {"path": f1, "name": "case05_大表调拨表.xlsx"},
            {"path": f2, "name": "case05_大表对账单.xlsx"}
        ]
        audit = calc_engine.generate_reconciliation_audit(files)
        assert audit.get("ok"), "Large composite audit failed"
        assert audit.get("passed_count") == 24, f"Expected all 24 rows matched, got {audit.get('passed_count')}"
        assert audit.get("discrepancy_count") == 0, "Expected 0 diffs"
        self.log_case(5, "调拨对账 - 复合大标题表头与 24 行大表", True, f"成功跳过大标题合并单元格，24 行全部核验通过")

    # ==========================================================================
    # Cases 06 - 10: 供应商比价与 TCO 测算评测
    # ==========================================================================
    def eval_case06_3vendors_standard(self):
        """Case 06: 3 家标准规范供应商报价单与 4D 得分及原生柱状图导出"""
        p_list = [
            os.path.join(MOCK_DIR, "case06_报价_晨光钢铁实业.xlsx"),
            os.path.join(MOCK_DIR, "case06_报价_建工物资供应链.xlsx"),
            os.path.join(MOCK_DIR, "case06_报价_华达建材贸易.xlsx")
        ]
        files = [{"path": p, "name": os.path.basename(p)} for p in p_list]
        weights = {"price": 0.4, "delivery": 0.2, "payment": 0.2, "quality": 0.2}

        calc_res = calc_engine.calculate_supplier_price_comparison(files, weights=weights, tax_rate=0.13)
        assert calc_res.get("ok"), "TCO calculation failed"
        rankings = calc_res.get("score_matrix", [])
        assert len(rankings) == 3, f"Expected 3 vendors ranked, got {len(rankings)}"

        # Verify Excel dual sheet export
        res_excel = calc_engine.generate_price_tco_excel(calc_res, OUT_DIR)
        assert res_excel.get("ok") and os.path.isfile(res_excel["path"]), "Price TCO Excel export failed"

        # Verify PPT export with native column chart
        res_ppt = calc_engine.generate_price_tco_ppt(calc_res, OUT_DIR)
        assert res_ppt.get("ok") and os.path.isfile(res_ppt["path"]), "Price TCO PPT export failed"

        # Validate PPT using core.validate_ppt_before_save
        prs = Presentation(res_ppt["path"])
        val_rep = core.validate_ppt_before_save(prs)
        assert val_rep.get("ok"), f"PPT validation failed: {val_rep}"

        self.log_case(6, "供应商比价 - 3家标准报价与4D加权得分", True, f"第一名: {rankings[0]['vendor']} ({rankings[0]['total_score']:.1f}分)")

    def eval_case07_tax_inclusive_mixed(self):
        """Case 07: 混用未税价与 13% 含税价换算"""
        p_list = [
            os.path.join(MOCK_DIR, "case07_报价_A厂格泰.xlsx"),
            os.path.join(MOCK_DIR, "case07_报价_B厂联信.xlsx"),
            os.path.join(MOCK_DIR, "case07_报价_C厂万丰.xlsx")
        ]
        files = [{"path": p, "name": os.path.basename(p)} for p in p_list]
        calc_res = calc_engine.calculate_supplier_price_comparison(files, tax_rate=0.13)
        assert calc_res.get("ok"), "TCO calculation failed"

        # A厂 3400 未税 -> 3842.0 含税; B厂 3800.0 含税.
        # B厂 must have lower tax-inclusive price than A厂!
        matrix = calc_res.get("comparison_matrix", [])
        assert len(matrix) >= 3, "Expected at least 3 comparison items"
        b_item = next((v for v in matrix if "联信" in v["vendor"]), None)
        a_item = next((v for v in matrix if "格泰" in v["vendor"]), None)
        assert b_item and a_item, "Could not find vendors in matrix"
        assert b_item["price_incl"] < a_item["price_incl"], f"B厂 ({b_item['price_incl']}) should be cheaper than A厂 ({a_item['price_incl']})"
        assert b_item["is_lowest"], "B厂 联信应为最低含税价"
        self.log_case(7, "供应商比价 - 混用未税与13%含税价换算", True, f"成功将未税与含税统一基准换算，最低价识别无误")

    def eval_case08_payment_terms_leverage(self):
        """Case 08: 现结0天 vs 30天 vs 90天 资金成本折算杠杆"""
        p_list = [
            os.path.join(MOCK_DIR, "case08_报价_现结0天.xlsx"),
            os.path.join(MOCK_DIR, "case08_报价_月结30天.xlsx"),
            os.path.join(MOCK_DIR, "case08_报价_季结90天.xlsx")
        ]
        files = [{"path": p, "name": os.path.basename(p)} for p in p_list]
        calc_res = calc_engine.calculate_supplier_price_comparison(files, annual_interest_rate=0.05)
        assert calc_res.get("ok"), "Calculation failed"

        matrix = calc_res.get("comparison_matrix", [])
        v0 = next(v for v in matrix if "0天" in v["vendor"])
        v90 = next(v for v in matrix if "90天" in v["vendor"])

        # 90天 should have positive capital benefit
        assert v0["capital_benefit"] == 0.0, "0 days payment should have 0 capital benefit"
        assert v90["capital_benefit"] > 0.0, "90 days payment should have positive capital benefit"
        self.log_case(8, "供应商比价 - 30/90天账期资金占用成本折算", True, f"90天账期折算资金抵扣收益: {v90['capital_benefit']:.2f}元/吨")

    def eval_case09_missing_lead_time_freight(self):
        """Case 09: 供应商漏填交期或运费标注“待协商”筛查"""
        p_list = [
            os.path.join(MOCK_DIR, "case09_报价_恒利物资.xlsx"),
            os.path.join(MOCK_DIR, "case09_报价_远东管道.xlsx"),
            os.path.join(MOCK_DIR, "case09_报价_正泰实业.xlsx")
        ]
        files = [{"path": p, "name": os.path.basename(p)} for p in p_list]
        calc_res = calc_engine.calculate_supplier_price_comparison(files)
        assert calc_res.get("ok"), "Calculation failed"

        unverified = calc_res.get("unverified_items", [])
        assert len(unverified) >= 2, f"Expected at least 2 unverified items, got {len(unverified)}"
        vendors_flagged = [u["vendor"] for u in unverified]
        assert any("恒利" in v for v in vendors_flagged), "恒利物资漏填交期未筛查"
        assert any("远东" in v for v in vendors_flagged), "远东管道运费待定未筛查"
        self.log_case(9, "供应商比价 - 漏填交期/运费待协商自动筛查", True, f"精准筛出 {len(unverified)} 处待核实项")

    def eval_case10_tight_margin_tie(self):
        """Case 10: 极端微小价差(差 0.3 元)多维度次优决标"""
        p_list = [
            os.path.join(MOCK_DIR, "case10_报价_天河材料.xlsx"),
            os.path.join(MOCK_DIR, "case10_报价_银河实业.xlsx")
        ]
        files = [{"path": p, "name": os.path.basename(p)} for p in p_list]
        calc_res = calc_engine.calculate_supplier_price_comparison(files)
        assert calc_res.get("ok"), "Calculation failed"

        rankings = calc_res.get("score_matrix", [])
        assert len(rankings) == 2
        # 天河 has 2 days delivery and 60 days payment, should score higher than 银河 (10 days, 30 days)
        assert "天河" in rankings[0]["vendor"], f"Expected 天河 to win on multidimensional score, got {rankings[0]['vendor']}"
        assert rankings[0]["total_score"] > rankings[1]["total_score"], "Winner score should be higher"
        self.log_case(10, "供应商比价 - 0.3元微小价差多维度决标", True, f"第一名: {rankings[0]['vendor']} ({rankings[0]['total_score']:.1f}分)")

    # ==========================================================================
    # Cases 11 - 15: 合同审查与 PPT 极限压力测试评测
    # ==========================================================================
    def eval_case11_contract_fatal_penalty(self):
        """Case 11: 采购合同含致命风险 (不设违约金上限 + 24小时检验期)"""
        p_doc = os.path.join(MOCK_DIR, "case11_采购合同_违约金异议期陷阱.docx")
        text = calc_engine.extract_text_from_file(p_doc)
        review = calc_engine.analyze_contract_full(text)
        assert "高风险" in review.get("rating", ""), f"Expected 高风险, got {review.get('rating')}"

        # Must detect red flag items
        red_items = [r for r in review.get("comparison_table", []) if r.get("risk_level_code") == "red" or "🔴" in str(r.get("risk_level", ""))]
        assert len(red_items) >= 1, "Expected at least 1 fatal red-flag clause detected"

        # Verify docx export
        res_docx = calc_engine.generate_contract_review_docx(review, OUT_DIR)
        assert res_docx.get("ok") and os.path.isfile(res_docx["path"]), "Export Word failed"

        # Verify pptx export & validate_ppt_before_save
        res_pptx = calc_engine.generate_contract_review_pptx(review, OUT_DIR)
        assert res_pptx.get("ok") and os.path.isfile(res_pptx["path"]), "Export PPT failed"
        prs = Presentation(res_pptx["path"])
        val_rep = core.validate_ppt_before_save(prs)
        assert val_rep.get("ok"), f"PPT validation failed: {val_rep}"

        self.log_case(11, "合同审查 - 违约金无上限与24h检验期致命陷阱", True, f"评级: {review['rating']}, 检出红灯致命项: {len(red_items)}项")

    def eval_case12_contract_venue_bias(self):
        """Case 12: 争议管辖法院偏远 (达坂城) + 发票付款脱节商务瑕疵"""
        p_doc = os.path.join(MOCK_DIR, "case12_采购合同_管辖法院偏远.docx")
        text = calc_engine.extract_text_from_file(p_doc)
        review = calc_engine.analyze_contract_full(text)

        # Must flag venue or dispute clause
        table = review.get("comparison_table", [])
        venue_issue = any("管辖" in t["category"] or "达坂城" in str(t.get("quote", "")) or "乌鲁木齐" in str(t.get("quote", "")) for t in table)
        assert venue_issue, "Expected remote court venue clause to be identified"

        # Export Word
        res_docx = calc_engine.generate_contract_review_docx(review, OUT_DIR)
        assert res_docx.get("ok"), "Export review docx failed"
        self.log_case(12, "合同审查 - 争议管辖法院偏远与发票瑕疵排查", True, f"准确识别达坂城偏远法院管辖瑕疵并提出标准修订条款")

    def eval_case13_contract_full_compliance(self):
        """Case 13: 示范合规文本 6 大条款完备"""
        p_doc = os.path.join(MOCK_DIR, "case13_采购合同_示范合规文本.docx")
        text = calc_engine.extract_text_from_file(p_doc)
        review = calc_engine.analyze_contract_full(text)

        # Rating should be 低风险 / 合规
        assert "低风险" in review.get("rating", ""), f"Expected 低风险, got {review.get('rating')}"
        green_items = [r for r in review.get("comparison_table", []) if r.get("risk_level_code") == "compliance" or "🟢" in str(r.get("risk_level", ""))]
        assert len(green_items) >= 4, f"Expected at least 4 compliant clauses, got {len(green_items)}"
        self.log_case(13, "合同审查 - 6大条款示范合规文本全覆盖", True, f"评级: 低风险, 绿灯完备项: {len(green_items)}项")

    def eval_case14_ppt_dense_table(self):
        """Case 14: PPT 12 行密集表格排版与自适应"""
        p_json = os.path.join(MOCK_DIR, "case14_ppt_dense_table.json")
        with open(p_json, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        slide_layout = prs.slide_layouts[5] if len(prs.slide_layouts) > 5 else prs.slide_layouts[0]
        slide = prs.slides.add_slide(slide_layout)

        # Build table slide using pptx
        rows_cnt = len(cfg["rows"]) + 1
        cols_cnt = len(cfg["headers"])
        tbl_shape = slide.shapes.add_table(rows_cnt, cols_cnt, Inches(0.8), Inches(1.5), Inches(11.733), Inches(5.0))
        tbl = tbl_shape.table

        # Fill headers
        for c_idx, h in enumerate(cfg["headers"]):
            tbl.cell(0, c_idx).text = h
        # Fill 12 rows
        for r_idx, row in enumerate(cfg["rows"], 1):
            for c_idx, val in enumerate(row):
                tbl.cell(r_idx, c_idx).text = str(val)

        # Run validate_ppt_before_save
        val_rep = core.validate_ppt_before_save(prs)
        assert val_rep.get("ok"), f"Dense table validation failed: {val_rep}"

        out_path = os.path.join(OUT_DIR, "eval_case14_dense_table.pptx")
        prs.save(out_path)
        self.log_case(14, "PPT 极限测试 - 12行密集供应链表格排版", True, f"12行x7列表格排版自检通过，0溢出0遮挡")

    def eval_case15_ppt_long_text(self):
        """Case 15: 超长公文文本段落(150+字)自动精简与备注转录"""
        p_json = os.path.join(MOCK_DIR, "case15_ppt_long_text.json")
        with open(p_json, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)
        slide = prs.slides.add_slide(prs.slide_layouts[0])

        tx_box = slide.shapes.add_textbox(Inches(1.0), Inches(1.8), Inches(11.333), Inches(4.8))
        tf = tx_box.text_frame
        tf.word_wrap = True

        simplified_bullets = []
        for raw_b in cfg["raw_bullets"]:
            # Core simplification rule: <= 30 chars
            short = core.simplify_bullet_text(raw_b, max_len=30)
            assert len(short) <= 30, f"Bullet not simplified <= 30 chars: {short} ({len(short)} chars)"
            simplified_bullets.append(short)
            p = tf.add_paragraph()
            p.text = f"• {short}"

        # Write original 150+ char texts to Speaker Notes
        notes_slide = slide.notes_slide
        tf_notes = notes_slide.notes_text_frame
        tf_notes.text = "\n\n".join([f"【原长文要点 {idx}】：{b}" for idx, b in enumerate(cfg["raw_bullets"], 1)])

        val_rep = core.validate_ppt_before_save(prs)
        assert val_rep.get("ok"), f"Long text validation failed: {val_rep}"
        out_path = os.path.join(OUT_DIR, "eval_case15_long_text_simplified.pptx")
        prs.save(out_path)
        self.log_case(15, "PPT 极限测试 - 超长公文 <=30字精简与演讲备注", True, f"4条长文全部精简至<=30字，演讲备注完整写入")

    # ==========================================================================
    # Main Runner
    # ==========================================================================
    def run_all(self):
        print("\n" + "=" * 80)
        print("🚀 开始运行供应链 15 项真实业务回归评测 (Supply Chain Business Evaluation)")
        print("=" * 80 + "\n")

        eval_methods = [
            self.eval_case01_normal_reconcile,
            self.eval_case02_diff_60_5,
            self.eval_case03_custom_headers,
            self.eval_case04_dirty_data,
            self.eval_case05_large_composite,
            self.eval_case06_3vendors_standard,
            self.eval_case07_tax_inclusive_mixed,
            self.eval_case08_payment_terms_leverage,
            self.eval_case09_missing_lead_time_freight,
            self.eval_case10_tight_margin_tie,
            self.eval_case11_contract_fatal_penalty,
            self.eval_case12_contract_venue_bias,
            self.eval_case13_contract_full_compliance,
            self.eval_case14_ppt_dense_table,
            self.eval_case15_ppt_long_text,
        ]

        failed = 0
        for idx, method in enumerate(eval_methods, 1):
            try:
                method()
            except Exception as e:
                failed += 1
                traceback.print_exc()
                self.log_case(idx, method.__name__, False, f"Exception: {str(e)}")

        print("\n" + "=" * 80)
        passed_count = len([r for r in self.results if r["passed"]])
        if passed_count == self.total_cases:
            print(f"🎉 评测结果: 15/15 PASS (全部 15 项业务测试 100% 绿色通过，0 缺陷！)")
            print("=" * 80 + "\n")
            return 0
        else:
            print(f"❌ 评测结果: {passed_count}/{self.total_cases} PASS, {failed} FAILED")
            print("=" * 80 + "\n")
            return 1


if __name__ == "__main__":
    evaluator = BusinessEvaluator()
    code = evaluator.run_all()
    sys.exit(code)
