# -*- coding: utf-8 -*-
r"""Supply Chain Mock Data Generator for Automated Business Evaluation.

Generates 15 sets of simulation test files with realistic business traps
into tests/mock_data/:
- Cases 01-05: Material Reconciliation (Normal, +60.5 Diff, Custom Headers, Dirty/Duplicates, Large Composite Table)
- Cases 06-10: Supplier Price Comparison & TCO (3-vendor Standard, Mixed Tax-excl/incl, Payment Terms Leverage, Missing Lead-time/Freight, Tight Margin Tie-breaker)
- Cases 11-15: Contract Review & PPT Stress (Missing Penalty Cap/Short Inspection, Remote Venue Bias, Full Compliance, 10+ Row Dense Table, Long-text Bullet Simplification)

Run:
    & "D:\AI\runtime\python\python.exe" tests/generate_mock_data.py
"""
import os
import sys
import json

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOCK_DIR = os.path.join(BASE_DIR, "tests", "mock_data")
os.makedirs(MOCK_DIR, exist_ok=True)


def _style_excel(ws, title, subtitle, headers, rows):
    ws.views.sheetView[0].showGridLines = True
    # Title
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws.cell(1, 1, title).font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    ws.cell(1, 1).alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 28

    # Subtitle
    if subtitle:
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
        ws.cell(2, 1, subtitle).font = Font(name="微软雅黑", size=9.5, color="555555")
        ws.cell(2, 1).alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 18
        h_row = 3
    else:
        h_row = 2

    # Headers
    h_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    h_font = Font(name="微软雅黑", size=10.5, bold=True, color="FFFFFF")
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.row_dimensions[h_row].height = 24
    for col_idx, h in enumerate(headers, 1):
        c = ws.cell(h_row, col_idx, h)
        c.font = h_font
        c.fill = h_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border

    # Data
    alt_fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
    r_font = Font(name="微软雅黑", size=10)
    for r_idx, row in enumerate(rows, h_row + 1):
        ws.row_dimensions[r_idx].height = 20
        use_alt = (r_idx % 2 == 0)
        for c_idx, val in enumerate(row, 1):
            cell = ws.cell(r_idx, c_idx, val)
            cell.font = r_font
            cell.border = border
            if use_alt:
                cell.fill = alt_fill
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center" if len(str(val)) <= 8 else "left", vertical="center")

    # Column widths
    for col in ws.columns:
        max_len = 0
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        for cell in col:
            if cell.row < h_row:
                continue
            v_str = str(cell.value or "")
            # Count Chinese characters as 2
            length = sum(2 if ord(ch) > 127 else 1 for ch in v_str)
            if length > max_len:
                max_len = length
        ws.column_dimensions[col_letter].width = max(max_len + 3, 11)


# ==============================================================================
# Group 1: 调拨对账测试集 (Cases 01 - 05)
# ==============================================================================
def gen_case01_normal_match():
    """Case 01: 正常账实相符对账表 (0 差额)"""
    headers = ["序号", "物资名称", "规格型号", "计量单位", "调拨数量", "调出单位", "调入单位", "业务日期"]
    rows = [
        [1, "热轧带肋钢筋", "HRB400E Φ18mm", "吨", 120.0, "华南一号总库", "前海二期项目", "2026-10-05"],
        [2, "高线热轧盘条", "HPB300 Φ8mm", "吨", 80.0, "华南一号总库", "前海二期项目", "2026-10-06"],
        [3, "热轧优质圆钢", "Q235B Φ16mm", "吨", 45.0, "华南二号分库", "龙岗三期项目", "2026-10-07"],
        [4, "碳素结构角钢", "Q235B 50*5mm", "吨", 35.0, "华南一号总库", "前海二期项目", "2026-10-08"],
    ]

    wb1 = openpyxl.Workbook()
    _style_excel(wb1.active, "现场调拨出库发运清单", "口径：实物出库称重净重", headers, rows)
    p1 = os.path.join(MOCK_DIR, "case01_调拨清单.xlsx")
    wb1.save(p1)

    # 对账单数据完全相符
    headers_book = ["序号", "物资名称", "规格型号", "单位", "数量", "调出项目", "调入项目", "记账日期"]
    rows_book = [
        [1, "热轧带肋钢筋", "HRB400E Φ18mm", "吨", 120.0, "华南一号总库", "前海二期项目", "2026-10-05"],
        [2, "高线热轧盘条", "HPB300 Φ8mm", "吨", 80.0, "华南一号总库", "前海二期项目", "2026-10-06"],
        [3, "热轧优质圆钢", "Q235B Φ16mm", "吨", 45.0, "华南二号分库", "龙岗三期项目", "2026-10-07"],
        [4, "碳素结构角钢", "Q235B 50*5mm", "吨", 35.0, "华南一号总库", "前海二期项目", "2026-10-08"],
    ]
    wb2 = openpyxl.Workbook()
    _style_excel(wb2.active, "财务物资入账确认台账", "口径：财务结算入账净值", headers_book, rows_book)
    p2 = os.path.join(MOCK_DIR, "case01_账面清单.xlsx")
    wb2.save(p2)
    return p1, p2


def gen_case02_diff_60_5():
    """Case 02: 故意相差 60.5 的账实差额表 (账面 1470.5 vs 实拨 1410.0，差额 +60.5)"""
    headers_actual = ["序号", "物资名称", "规格型号", "单位", "调拨量", "调出单位", "调入单位", "调拨日期"]
    rows_actual = [
        [1, "螺纹钢", "HRB400 Φ20mm", "吨", 500.0, "广州黄埔基地", "深圳南山项目", "2026-10-10"],
        [2, "盘圆", "HPB300 Φ10mm", "吨", 300.0, "广州黄埔基地", "深圳南山项目", "2026-10-11"],
        [3, "热轧中板", "Q235B 14mm", "吨", 610.0, "佛山顺德仓", "东莞松山湖工区", "2026-10-12"],
    ]
    wb1 = openpyxl.Workbook()
    _style_excel(wb1.active, "实物调拨出库总表", "实际出库累计：1,410.0 吨", headers_actual, rows_actual)
    p1 = os.path.join(MOCK_DIR, "case02_调拨总表.xlsx")
    wb1.save(p1)

    headers_book = ["序号", "物资名称", "规格型号", "单位", "数量", "调出单位", "调入单位", "核算日期"]
    rows_book = [
        [1, "螺纹钢", "HRB400 Φ20mm", "吨", 500.0, "广州黄埔基地", "深圳南山项目", "2026-10-10"],
        [2, "盘圆", "HPB300 Φ10mm", "吨", 300.0, "广州黄埔基地", "深圳南山项目", "2026-10-11"],
        [3, "热轧中板", "Q235B 14mm", "吨", 670.5, "佛山顺德仓", "东莞松山湖工区", "2026-10-12"],
    ]
    wb2 = openpyxl.Workbook()
    _style_excel(wb2.active, "财务对账确认表", "账面应收累计：1,470.5 吨 (存在 +60.5 差额)", headers_book, rows_book)
    p2 = os.path.join(MOCK_DIR, "case02_对账底表.xlsx")
    wb2.save(p2)
    return p1, p2


def gen_case03_custom_headers():
    """Case 03: 口语化异构表头需下拉映射 (发货数 vs 实收数量, 物料品名 vs 材料名称)"""
    h1 = ["序号", "物料品名", "型号标号", "发货数", "发货地", "目的地"]
    r1 = [
        [1, "镀锌方矩管", "50*50*3.0mm", 85.0, "总库一号", "珠海横琴项目"],
        [2, "无缝流体钢管", "DN100*4.0mm", 320.0, "总库一号", "珠海横琴项目"],
        [3, "热镀锌工字钢", "16# 6米定尺", 42.5, "佛山加工厂", "珠海横琴项目"],
    ]
    wb1 = openpyxl.Workbook()
    _style_excel(wb1.active, "加工发货明细单", "", h1, r1)
    p1 = os.path.join(MOCK_DIR, "case03_仓库出货表.xlsx")
    wb1.save(p1)

    h2 = ["序号", "材料名称", "规格", "实收数量", "供货方", "收货项目"]
    r2 = [
        [1, "镀锌方矩管", "50*50*3.0mm", 85.0, "总库一号", "珠海横琴项目"],
        [2, "无缝流体钢管", "DN100*4.0mm", 320.0, "总库一号", "珠海横琴项目"],
        [3, "热镀锌工字钢", "16# 6米定尺", 42.5, "佛山加工厂", "珠海横琴项目"],
    ]
    wb2 = openpyxl.Workbook()
    _style_excel(wb2.active, "现场签收登记册", "", h2, r2)
    p2 = os.path.join(MOCK_DIR, "case03_项目签收单.xlsx")
    wb2.save(p2)
    return p1, p2


def gen_case04_dirty_data():
    """Case 04: 含空行、缺失物资名称/规格的坏行、同单号多批次分录"""
    h = ["单据编号", "物资名称", "规格型号", "单位", "数量", "发车时间"]
    r = [
        ["DB-202610-001", "无缝钢管", "108*4.5mm", "吨", 40.0, "2026-10-15 08:30"],
        ["", "", "", "", "", ""],  # 全空行
        ["DB-202610-002", "", "89*4.0mm", "吨", 15.0, "2026-10-15 09:15"],  # 缺失名称
        ["DB-202610-001", "无缝钢管", "108*4.5mm", "吨", 60.0, "2026-10-15 14:00"],  # 同物料分批送达(合计100.0)
        ["DB-202610-003", "螺旋焊管", "Φ426*8mm", "吨", 55.0, "2026-10-16 10:00"],
    ]
    wb1 = openpyxl.Workbook()
    _style_excel(wb1.active, "现场实收分批流水(含脏数据)", "", h, r)
    p1 = os.path.join(MOCK_DIR, "case04_现场混乱调拨表.xlsx")
    wb1.save(p1)

    h_book = ["序号", "物资名称", "规格型号", "单位", "数量"]
    r_book = [
        [1, "无缝钢管", "108*4.5mm", "吨", 100.0],  # 对应 40 + 60
        [2, "螺旋焊管", "Φ426*8mm", "吨", 55.0],
    ]
    wb2 = openpyxl.Workbook()
    _style_excel(wb2.active, "财务对账底表", "", h_book, r_book)
    p2 = os.path.join(MOCK_DIR, "case04_财务底表.xlsx")
    wb2.save(p2)
    return p1, p2


def gen_case05_large_composite():
    """Case 05: 复合大标题合并单元格表头 + 20+ 行大表"""
    wb1 = openpyxl.Workbook()
    ws1 = wb1.active
    ws1.views.sheetView[0].showGridLines = True
    # Row 1 Big composite banner
    ws1.merge_cells("A1:G1")
    ws1["A1"] = "2026年度重点工程建设物资跨区域调拨综合台账（第三季度）"
    ws1["A1"].font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws1.row_dimensions[1].height = 30

    # Row 2 Headers
    headers = ["序号", "物资类别", "物资名称", "规格型号", "计量单位", "调拨量", "调入项目部"]
    h_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
    h_font = Font(name="微软雅黑", size=10.5, bold=True, color="FFFFFF")
    thin = Side(border_style="thin", color="CCCCCC")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws1.row_dimensions[2].height = 24
    for c_idx, h in enumerate(headers, 1):
        c = ws1.cell(2, c_idx, h)
        c.font = h_font
        c.fill = h_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border

    # 24 rows
    categories = ["建筑钢材", "型材", "管材", "板材"]
    items = [
        ("螺纹钢", "HRB400E 12mm", 60.0), ("螺纹钢", "HRB400E 14mm", 80.0),
        ("螺纹钢", "HRB400E 16mm", 120.0), ("螺纹钢", "HRB400E 18mm", 150.0),
        ("螺纹钢", "HRB400E 20mm", 200.0), ("螺纹钢", "HRB400E 22mm", 180.0),
        ("螺纹钢", "HRB400E 25mm", 140.0), ("高线", "HPB300 6.5mm", 50.0),
        ("高线", "HPB300 8.0mm", 90.0), ("高线", "HPB300 10.0mm", 75.0),
        ("工字钢", "16# 6m", 30.0), ("工字钢", "20# 6m", 45.0),
        ("工字钢", "25# 6m", 60.0), ("槽钢", "10# 6m", 25.0),
        ("槽钢", "14# 6m", 35.0), ("槽钢", "16# 6m", 40.0),
        ("角钢", "50*5mm", 20.0), ("角钢", "63*6mm", 30.0),
        ("角钢", "75*8mm", 40.0), ("无缝管", "108*4.5mm", 55.0),
        ("无缝管", "159*6.0mm", 70.0), ("热轧板", "Q235B 6mm", 85.0),
        ("热轧板", "Q235B 8mm", 110.0), ("热轧板", "Q235B 10mm", 130.0),
    ]

    alt_fill = PatternFill(start_color="F9FAFB", end_color="F9FAFB", fill_type="solid")
    r_font = Font(name="微软雅黑", size=10)
    for r_idx, (name, spec, qty) in enumerate(items, 3):
        cat = categories[(r_idx - 3) // 6]
        row_vals = [r_idx - 2, cat, name, spec, "吨", qty, "前海深港联合工区"]
        ws1.row_dimensions[r_idx].height = 20
        use_alt = (r_idx % 2 == 0)
        for c_idx, val in enumerate(row_vals, 1):
            cell = ws1.cell(r_idx, c_idx, val)
            cell.font = r_font
            cell.border = border
            if use_alt:
                cell.fill = alt_fill
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center" if len(str(val)) <= 8 else "left", vertical="center")

    for col in ws1.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws1.column_dimensions[col_letter].width = 16

    p1 = os.path.join(MOCK_DIR, "case05_大表调拨表.xlsx")
    wb1.save(p1)

    # 对账单
    wb2 = openpyxl.Workbook()
    ws2 = wb2.active
    ws2.views.sheetView[0].showGridLines = True
    ws2.merge_cells("A1:E1")
    ws2["A1"] = "财务入账对账清单"
    ws2["A1"].font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    ws2["A1"].alignment = Alignment(horizontal="center", vertical="center")
    ws2.row_dimensions[1].height = 28

    h_book = ["序号", "物资名称", "规格型号", "单位", "数量"]
    ws2.row_dimensions[2].height = 24
    for c_idx, h in enumerate(h_book, 1):
        c = ws2.cell(2, c_idx, h)
        c.font = h_font
        c.fill = h_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = border

    for r_idx, (name, spec, qty) in enumerate(items, 3):
        row_vals = [r_idx - 2, name, spec, "吨", qty]
        ws2.row_dimensions[r_idx].height = 20
        use_alt = (r_idx % 2 == 0)
        for c_idx, val in enumerate(row_vals, 1):
            cell = ws2.cell(r_idx, c_idx, val)
            cell.font = r_font
            cell.border = border
            if use_alt:
                cell.fill = alt_fill
            if isinstance(val, (int, float)):
                cell.alignment = Alignment(horizontal="right", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="center" if len(str(val)) <= 8 else "left", vertical="center")

    for col in ws2.columns:
        col_letter = openpyxl.utils.get_column_letter(col[0].column)
        ws2.column_dimensions[col_letter].width = 16

    p2 = os.path.join(MOCK_DIR, "case05_大表对账单.xlsx")
    wb2.save(p2)
    return p1, p2


# ==============================================================================
# Group 2: 供应商比价与 TCO 测算测试集 (Cases 06 - 10)
# ==============================================================================
def gen_case06_3vendors_standard():
    """Case 06: 3 家标准规范供应商报价单"""
    headers = ["序号", "材料名称", "规格型号", "计量单位", "未税单价", "税率", "交货期", "付款账期", "运杂费承担"]

    v_data = [
        ("晨光钢铁实业", [
            [1, "热轧带肋钢筋", "HRB400E Φ20mm", "吨", 3500.0, "13%", "3天", "月结60天", "供方承担"],
            [2, "热轧优质盘圆", "HPB300 Φ8mm", "吨", 3650.0, "13%", "3天", "月结60天", "供方承担"],
        ]),
        ("建工物资供应链", [
            [1, "热轧带肋钢筋", "HRB400E Φ20mm", "吨", 3450.0, "13%", "7天", "月结30天", "需方自提每吨加50元"],
            [2, "热轧优质盘圆", "HPB300 Φ8mm", "吨", 3600.0, "13%", "7天", "月结30天", "需方自提每吨加50元"],
        ]),
        ("华达建材贸易", [
            [1, "热轧带肋钢筋", "HRB400E Φ20mm", "吨", 3600.0, "13%", "2天", "季度结90天", "供方直发包运费"],
            [2, "热轧优质盘圆", "HPB300 Φ8mm", "吨", 3750.0, "13%", "2天", "季度结90天", "供方直发包运费"],
        ]),
    ]

    paths = []
    for vname, rows in v_data:
        wb = openpyxl.Workbook()
        _style_excel(wb.active, f"工程物资竞争性报价单 - {vname}", "基准税率：13%", headers, rows)
        p = os.path.join(MOCK_DIR, f"case06_报价_{vname}.xlsx")
        wb.save(p)
        paths.append(p)
    return paths


def gen_case07_tax_inclusive_mixed():
    """Case 07: 混用未税价与 13% 含税价陷阱"""
    h = ["材料名称", "规格型号", "报价类型", "单价", "税率", "交货期", "付款方式", "运费"]
    v_data = [
        ("A厂格泰", [
            ["热轧带肋钢筋", "HRB400E Φ18mm", "未税价", 3400.0, "13%", "5天", "月结30天", "包到价"],
        ]),  # 折算含税 3400 * 1.13 = 3842.0 元
        ("B厂联信", [
            ["热轧带肋钢筋", "HRB400E Φ18mm", "含税价", 3800.0, "13%", "5天", "月结30天", "包到价"],
        ]),  # 含税 3800.0 元 (折算未税 3362.83 元) -> 真实更低！
        ("C厂万丰", [
            ["热轧带肋钢筋", "HRB400E Φ18mm", "含税价", 3950.0, "13%", "4天", "月结30天", "包到价"],
        ]),
    ]
    paths = []
    for vname, rows in v_data:
        wb = openpyxl.Workbook()
        _style_excel(wb.active, f"材料报价表 - {vname}", "", h, rows)
        p = os.path.join(MOCK_DIR, f"case07_报价_{vname}.xlsx")
        wb.save(p)
        paths.append(p)
    return paths


def gen_case08_payment_terms_leverage():
    """Case 08: 现结0天 vs 30天 vs 90天 资金成本折算杠杆"""
    h = ["序号", "物资名称", "规格型号", "单位", "含税单价", "交期", "付款账期", "运杂费"]
    v_data = [
        ("现结0天", [[1, "工字钢", "25# 6m", "吨", 3500.0, "3天", "现结0天", "包运"]]),
        ("月结30天", [[1, "工字钢", "25# 6m", "吨", 3525.0, "3天", "月结30天", "包运"]]),
        ("季结90天", [[1, "工字钢", "25# 6m", "吨", 3560.0, "3天", "季结90天", "包运"]]),
    ]
    paths = []
    for vname, rows in v_data:
        wb = openpyxl.Workbook()
        _style_excel(wb.active, f"结构型材报价单 - {vname}", "", h, rows)
        p = os.path.join(MOCK_DIR, f"case08_报价_{vname}.xlsx")
        wb.save(p)
        paths.append(p)
    return paths


def gen_case09_missing_lead_time_freight():
    """Case 09: 供应商故意漏填交期或运费标注“待协商”"""
    h = ["序号", "材料名称", "规格型号", "单位", "含税单价", "交货期", "付款账期", "运费说明"]
    v_data = [
        ("恒利物资", [[1, "螺旋焊管", "Φ529*9mm", "吨", 4100.0, "", "月结30天", "供方承担"]]),  # 漏填交期
        ("远东管道", [[1, "螺旋焊管", "Φ529*9mm", "吨", 4050.0, "7天", "月结30天", "待协商另计"]]),  # 运费待定
        ("正泰实业", [[1, "螺旋焊管", "Φ529*9mm", "吨", 4150.0, "5天", "月结30天", "供方送货上门"]]),
    ]
    paths = []
    for vname, rows in v_data:
        wb = openpyxl.Workbook()
        _style_excel(wb.active, f"管道报价单 - {vname}", "提示：请核验待核实项", h, rows)
        p = os.path.join(MOCK_DIR, f"case09_报价_{vname}.xlsx")
        wb.save(p)
        paths.append(p)
    return paths


def gen_case10_tight_margin_tie():
    """Case 10: 极端微小价差(差 0.3 元)多维度次优决标"""
    h = ["序号", "材料名称", "规格型号", "含税单价", "交货期", "付款账期", "运费", "历史质量评分"]
    v_data = [
        ("天河材料", [[1, "热轧卷板", "Q235B 6.0mm", 3500.2, "2天", "月结60天", "包运", 95]]),
        ("银河实业", [[1, "热轧卷板", "Q235B 6.0mm", 3500.5, "10天", "月结30天", "包运", 80]]),
    ]
    paths = []
    for vname, rows in v_data:
        wb = openpyxl.Workbook()
        _style_excel(wb.active, f"板材比选报价单 - {vname}", "", h, rows)
        p = os.path.join(MOCK_DIR, f"case10_报价_{vname}.xlsx")
        wb.save(p)
        paths.append(p)
    return paths


# ==============================================================================
# Group 3: 合同审查与 PPT 极限压力测试集 (Cases 11 - 15)
# ==============================================================================
def gen_case11_contract_fatal_penalty():
    """Case 11: 采购合同含致命风险 (不设违约金上限 + 24小时检验期)"""
    doc = Document()
    doc.add_heading("工程钢构件加工采购承揽框架合同", level=0)
    p_sub = doc.add_paragraph("合同编号：CG-2026-F011  |  签约主体：买方建设集团 vs 卖方重工机械")
    p_sub.runs[0].font.size = Pt(10)
    p_sub.runs[0].font.color.rgb = RGBColor(100, 100, 100)

    doc.add_heading("第一条 付款节点与结算账期", level=1)
    doc.add_paragraph("合同签订后3个工作日内买方支付30%预付款；产品制作完成发货前支付60%进度款；剩余10%作为质保金，自工程竣工验收合格满1年后无息支付。")

    doc.add_heading("第二条 延期履约违约金责任", level=1)
    doc.add_paragraph("【致命风险陷阱】供方延期交货或买方延期付款的，每日按迟延履行部分金额的1%向对方支付违约金。该违约金持续累计计算，不设任何累计总额上限，直至违约行为实际纠正为止。")

    doc.add_heading("第三条 质量验收标准与异议期", level=1)
    doc.add_paragraph("【异议期过短陷阱】产品运抵现场后，买方应在到货后24小时内完成全部外观、尺寸及力学性能抽样检验并提出书面异议。若买方逾期未提出异议的，即视为产品完全合格，卖方免除一切后续质量瑕疵担保责任。")

    doc.add_heading("第四条 知识产权归属", level=1)
    doc.add_paragraph("本合同履行过程中由供方依据买方图纸深化设计产生的各类图纸、工装方案及专利申请权均归供方单独所有。")

    doc.add_heading("第五条 保密义务", level=1)
    doc.add_paragraph("双方对履行合同过程中获知的商业秘密与图纸信息承担保密义务，保密期限为合同解除或终止后2年。")

    doc.add_heading("第六条 争议解决与管辖法院", level=1)
    doc.add_paragraph("因本合同引起的或与本合同有关的争议，双方应友好协商；协商不成的，由原告住所地人民法院管辖。")

    p = os.path.join(MOCK_DIR, "case11_采购合同_违约金异议期陷阱.docx")
    doc.save(p)
    return p


def gen_case12_contract_venue_bias():
    """Case 12: 争议管辖偏远法院 + 发票付款脱节商务瑕疵"""
    doc = Document()
    doc.add_heading("大型工业特种电缆采购供货协议", level=0)
    p_sub = doc.add_paragraph("合同编号：DL-2026-V012  |  签约主体：需方电力工程公司 vs 供方西北线缆实业")

    doc.add_heading("第一条 价款与发票约定", level=1)
    doc.add_paragraph("【商务瑕疵】买方收到货物后应在15日内付清全款。发票提供时间视供方当月税务开票额度统筹安排，供方力争在款项结清后6个月内提供增值税专用发票。")

    doc.add_heading("第二条 违约责任", level=1)
    doc.add_paragraph("供方逾期交货的，每日按应交未交货物价款的0.05%向买方支付违约金，违约金累计总额不超过该批次货物金额的5%。")

    doc.add_heading("第三条 质量检验与质保期", level=1)
    doc.add_paragraph("买方收到电缆后应在15日内组织开盘抽检，质保期为通电试运行合格后12个月。")

    doc.add_heading("第四条 知识产权条款", level=1)
    doc.add_paragraph("双方不涉及专用知识产权转让，供方保证提供的电缆不侵犯任何第三方知识产权。")

    doc.add_heading("第五条 保密协议", level=1)
    doc.add_paragraph("双方对电缆布线走向及工程技术参数予以保密，保密期3年。")

    doc.add_heading("第六条 争议解决管辖", level=1)
    doc.add_paragraph("【管辖偏远陷阱】凡因本协议引起的争议，双方协商不成时，必须向供方住所地乌鲁木齐市达坂城区人民法院提起诉讼管辖。")

    p = os.path.join(MOCK_DIR, "case12_采购合同_管辖法院偏远.docx")
    doc.save(p)
    return p


def gen_case13_contract_full_compliance():
    """Case 13: 6 大条款规范完备合同样本"""
    doc = Document()
    doc.add_heading("机电设备成套采购安装标准合同", level=0)
    p_sub = doc.add_paragraph("合同编号：GF-2026-OK013  |  示范合规文本")

    doc.add_heading("第一条 付款节点与结算账期", level=1)
    doc.add_paragraph("【合规完备】按节点分期支付：合同生效后支付10%预付款；设备运抵现场且双方签署书面验收合格报告、收到供方开具的13%增值税专用发票后支付至75%；安装调试并取得最终验收合格单后支付至95%；质保金在质保期满1年且无质量异议后15个工作日内无息退还。")

    doc.add_heading("第二条 违约责任与对等约束", level=1)
    doc.add_paragraph("【对等合规】任何一方违约的，每日按迟延履行金额的0.05%计付违约金，双方违约金总额上限均严格限定为合同总金额的5%。逾期超过15日买方有权单方书面解除合同。")

    doc.add_heading("第三条 质量验收标准与异议期", level=1)
    doc.add_paragraph("【充足异议期】标的物质量符合国家标准GB/T相关技术规范要求。到货后外观检验期为7个工作日；隐蔽工程及性能异议期为安装调试完成后30个工作日。在质保期内买方享有质量保证追偿权，若需第三方检测机构复验，检验费用由责任方承担。")

    doc.add_heading("第四条 知识产权归属保护", level=1)
    doc.add_paragraph("【买方权益保护】定制开发图纸与技术成果独家归买方所有，供方明确保证其交付产品不侵犯第三方知识产权，如发生侵权纠纷供方负责独立应诉并承担诉讼费、律师费及全额赔偿买方损失。")

    doc.add_heading("第五条 商业秘密保护", level=1)
    doc.add_paragraph("【规范保密】双方恪守商业保密准则，保密范围涵盖商业报价、技术资料及图纸，保密有效期为合同终止后5年。任何一方违反保密义务的应支付违约金人民币10万元并全额赔偿守约方损失。")

    doc.add_heading("第六条 争议管辖约定", level=1)
    doc.add_paragraph("【公平管辖】本合同履行发生争议的，由需方住所地或合同签署地人民法院管辖。")

    p = os.path.join(MOCK_DIR, "case13_采购合同_示范合规文本.docx")
    doc.save(p)
    return p


def gen_case14_ppt_dense_table():
    """Case 14: PPT 12 行密集表格数据压测"""
    data = {
        "title": "2026年三季度跨区域物资调拨对账明细",
        "subtitle": "压力测试：12行密集供应链表格排版与字号自适应",
        "headers": ["序号", "物资名称", "规格型号", "调拨量", "账面数", "净差额", "状态判定"],
        "rows": [
            [1, "热轧带肋钢筋", "HRB400E 12mm", "60.0 吨", "60.0 吨", "0.0", "账实相符"],
            [2, "热轧带肋钢筋", "HRB400E 14mm", "80.0 吨", "80.0 吨", "0.0", "账实相符"],
            [3, "热轧带肋钢筋", "HRB400E 16mm", "120.0 吨", "120.0 吨", "0.0", "账实相符"],
            [4, "热轧带肋钢筋", "HRB400E 18mm", "150.0 吨", "150.0 吨", "0.0", "账实相符"],
            [5, "热轧带肋钢筋", "HRB400E 20mm", "200.0 吨", "200.0 吨", "0.0", "账实相符"],
            [6, "热轧优质高线", "HPB300 8.0mm", "90.0 吨", "90.0 吨", "0.0", "账实相符"],
            [7, "热轧优质工字钢", "16# 6m定尺", "30.0 吨", "30.0 吨", "0.0", "账实相符"],
            [8, "热轧优质槽钢", "14# 6m定尺", "35.0 吨", "35.0 吨", "0.0", "账实相符"],
            [9, "结构热轧角钢", "50*5mm定尺", "20.0 吨", "20.0 吨", "0.0", "账实相符"],
            [10, "流体无缝钢管", "108*4.5mm", "55.0 吨", "55.0 吨", "0.0", "账实相符"],
            [11, "优质碳素热轧板", "Q235B 8.0mm", "110.0 吨", "110.0 吨", "0.0", "账实相符"],
            [12, "优质碳素热轧板", "Q235B 14mm", "610.0 吨", "670.5 吨", "+60.5", "差额警示"],
        ],
    }
    p = os.path.join(MOCK_DIR, "case14_ppt_dense_table.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p


def gen_case15_ppt_long_text():
    """Case 15: 超长公文文本段落(150+字/条)压测与 <=30 字精简"""
    data = {
        "title": "跨区域供应链调拨与战略采购复盘报告",
        "subtitle": "极限压测：超长公文段落自动精简至 <=30 字并写入演讲备注",
        "raw_bullets": [
            "经全面梳理本季度物资调拨台账与现场称重单据，共核算调拨记录1,470.5吨，整体账实匹配率达到95.8%，实现重大物资零损耗交付与精准供应链跨区域协同调配。",
            "针对热轧中板Q235B出现的+60.5吨账实差额，经多方核对确认为东莞松山湖工区分批到货未及时入账所致，已责令现场仓管员于3个工作日内补齐全部入库验收手续。",
            "在供应商横向TCO比选过程中，建工物资因未税单价3450元且近端自提节约二次倒运费50元/吨，综合评分达到92.4分，确立为第一中标候选人并授予70%采购份额。",
            "针对合同审查中暴露的违约金不设上限及24小时检验期过短等2项重大法务红灯缺陷，已向分包商发送正式律师函，强制统一采用标准示范合规模板进行条款重签。",
        ],
    }
    p = os.path.join(MOCK_DIR, "case15_ppt_long_text.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return p


def generate_all():
    print("[MockDataGen] Starting generation of 15 simulation test scenarios...")
    p1 = gen_case01_normal_match()
    print("  [OK] Case 01: 正常账实相符对账表")
    p2 = gen_case02_diff_60_5()
    print("  [OK] Case 02: 故意相差 60.5 账实差额表")
    p3 = gen_case03_custom_headers()
    print("  [OK] Case 03: 口语化异构表头需映射")
    p4 = gen_case04_dirty_data()
    print("  [OK] Case 04: 空行/脏行/分批重复单号表")
    p5 = gen_case05_large_composite()
    print("  [OK] Case 05: 复合大标题表头大表")
    p6 = gen_case06_3vendors_standard()
    print("  [OK] Case 06: 3家标准供应商报价单")
    p7 = gen_case07_tax_inclusive_mixed()
    print("  [OK] Case 07: 混用未税与13%含税价陷阱")
    p8 = gen_case08_payment_terms_leverage()
    print("  [OK] Case 08: 现结 vs 30天 vs 90天账期杠杆")
    p9 = gen_case09_missing_lead_time_freight()
    print("  [OK] Case 09: 漏填交期/运费待协商筛查")
    p10 = gen_case10_tight_margin_tie()
    print("  [OK] Case 10: 极微小价差多维度次优决标")
    p11 = gen_case11_contract_fatal_penalty()
    print("  [OK] Case 11: 采购合同违约金异议期陷阱")
    p12 = gen_case12_contract_venue_bias()
    print("  [OK] Case 12: 争议管辖法院偏远偏向")
    p13 = gen_case13_contract_full_compliance()
    print("  [OK] Case 13: 示范合规合同文本")
    p14 = gen_case14_ppt_dense_table()
    print("  [OK] Case 14: PPT 12行密集表格排版")
    p15 = gen_case15_ppt_long_text()
    print("  [OK] Case 15: 超长公文文本段落精简")
    print(f"[MockDataGen] All 15 simulation test files successfully created in {MOCK_DIR}")


if __name__ == "__main__":
    generate_all()
