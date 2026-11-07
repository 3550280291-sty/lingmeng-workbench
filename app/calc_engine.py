# -*- coding: utf-8 -*-
"""确定性计算与表格处理引擎（基于 pandas、numpy、openpyxl）。
用于根除 4B/8B 小参数模型直接口算导致的求和、均值、差额及百分比错误。
"""
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
import pandas as pd


def extract_text_from_file(path: str) -> str:
    """从本地文件（.docx, .pdf, .txt 等）提取纯文本。"""
    try:
        import core
        _, txt = core.extract_text(path)
        return txt or ""
    except Exception:
        if str(path).lower().endswith(".docx"):
            import docx
            doc = docx.Document(path)
            return "\n".join(p.text for p in doc.paragraphs)
        elif str(path).lower().endswith(".txt"):
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()
        return ""


def _clean_header_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """如果首行为合并标题行或大部分列名为 Unnamed/数字索引，自动探查并提取真实业务表头行。"""
    if df.empty or df.shape[1] == 0:
        return df
    unnamed_count = sum(1 for c in df.columns if str(c).startswith("Unnamed:") or isinstance(c, (int, np.integer)) or str(c).isdigit())
    if unnamed_count > len(df.columns) * 0.4:
        for row_idx in range(min(6, len(df))):
            row_vals = [str(v).strip() for v in df.iloc[row_idx] if pd.notna(v) and str(v).strip() != ""]
            if len(row_vals) >= 2 and any(any(kw in v for kw in ("名称", "物料", "物资", "品名", "规格", "数量", "单位", "单价", "金额")) for v in row_vals):
                new_headers = [str(c).strip() if pd.notna(c) and str(c).strip() != "" else f"列{i+1}" for i, c in enumerate(df.iloc[row_idx])]
                new_df = df.iloc[row_idx + 1:].copy()
                new_df.columns = new_headers
                return new_df.reset_index(drop=True)
    return df


RECONCILE_HEADER_KEYWORDS = (
    "名称", "规格", "数量", "编码", "单价", "调拨", "金额", "物料",
    "单位", "品名", "实收", "应发", "出库", "入库", "供方", "需方",
    "日期", "序号", "型号", "材质", "调出", "调入", "结算", "总额"
)


def detect_excel_header_row(raw_df: pd.DataFrame, max_scan: int = 15) -> int:
    """自动扫描前 15 行，统计非空单元格数与关键词权重，推断最佳表头所在行号 (0-based)。"""
    if raw_df.empty:
        return 0
    best_row = 0
    best_score = -1.0
    scan_limit = min(max_scan, len(raw_df))
    for r in range(scan_limit):
        row_vals = [str(v).strip() for v in raw_df.iloc[r] if pd.notna(v) and str(v).strip() != "" and str(v).strip().lower() != "nan"]
        if not row_vals:
            continue
        kw_count = sum(1 for v in row_vals if any(kw in v for kw in RECONCILE_HEADER_KEYWORDS))
        non_empty = len(row_vals)
        score = kw_count * 10 + non_empty
        if score > best_score:
            best_score = score
            best_row = r
    return best_row


def read_dataframes_from_file(
    path: str,
    header_row_index: Optional[int] = None,
    sheet_headers: Optional[Dict[str, int]] = None
) -> Dict[str, pd.DataFrame]:
    """读取单文件中的全部数据表，返回 {sheet_name: df}。支持自动扫描前 15 行或手动指定表头行。"""
    ext = os.path.splitext(path)[1].lower()
    dfs = {}
    if ext == ".csv":
        for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030", "latin-1"):
            try:
                target_header = 0
                if sheet_headers and "CSV" in sheet_headers:
                    target_header = int(sheet_headers["CSV"])
                elif header_row_index is not None:
                    target_header = int(header_row_index)
                else:
                    try:
                        raw_sniff = pd.read_csv(path, encoding=enc, header=None, nrows=15)
                        target_header = detect_excel_header_row(raw_sniff, max_scan=15)
                    except Exception:
                        target_header = 0

                df = pd.read_csv(path, encoding=enc, header=target_header)
                if df.shape[1] <= 1:
                    try:
                        df_sniff = pd.read_csv(path, encoding=enc, sep=None, engine="python", header=target_header)
                        if df_sniff.shape[1] > 1:
                            df = df_sniff
                    except Exception:
                        pass
                is_manual_csv = bool((sheet_headers and "CSV" in sheet_headers) or (header_row_index is not None))
                cleaned_df = df if is_manual_csv else _clean_header_dataframe(df)
                cleaned_df.attrs["header_row_index"] = target_header
                dfs["CSV"] = cleaned_df
                break
            except Exception:
                continue
    elif ext in (".xlsx", ".xlsm", ".xls"):
        try:
            with pd.ExcelFile(path) as excel:
                for sheet in excel.sheet_names:
                    try:
                        target_header = None
                        if sheet_headers and sheet in sheet_headers:
                            target_header = int(sheet_headers[sheet])
                        elif header_row_index is not None:
                            target_header = int(header_row_index)

                        if target_header is None:
                            raw_df = pd.read_excel(excel, sheet_name=sheet, header=None, nrows=15)
                            target_header = detect_excel_header_row(raw_df, max_scan=15)

                        df = pd.read_excel(excel, sheet_name=sheet, header=target_header)
                        if not df.empty and df.shape[1] > 0:
                            is_manual_sheet = bool((sheet_headers and sheet in sheet_headers) or (header_row_index is not None))
                            cleaned_df = df if is_manual_sheet else _clean_header_dataframe(df)
                            cleaned_df.attrs["header_row_index"] = target_header
                            dfs[sheet] = cleaned_df
                    except Exception:
                        continue
        except Exception:
            wb = None
            try:
                wb = openpyxl.load_workbook(path, data_only=True)
                for sheet in wb.sheetnames:
                    ws = wb[sheet]
                    rows = list(ws.iter_rows(values_only=True))
                    if len(rows) >= 2:
                        target_header = 0
                        if sheet_headers and sheet in sheet_headers:
                            target_header = int(sheet_headers[sheet])
                        elif header_row_index is not None:
                            target_header = int(header_row_index)
                        else:
                            temp_df = pd.DataFrame(rows[:15])
                            target_header = detect_excel_header_row(temp_df, max_scan=15)

                        target_header = min(target_header, len(rows) - 1)
                        headers = [str(c) if c is not None and str(c).strip() != "" else f"列{i+1}" for i, c in enumerate(rows[target_header])]
                        data = rows[target_header + 1:]
                        raw_df = pd.DataFrame(data, columns=headers)
                        cleaned_df = _clean_header_dataframe(raw_df)
                        cleaned_df.attrs["header_row_index"] = target_header
                        dfs[sheet] = cleaned_df
            except Exception:
                pass
            finally:
                if wb:
                    try:
                        wb.close()
                    except Exception:
                        pass
    return dfs


def precompute_tables_summary(files: List[Dict[str, Any]]) -> str:
    """当检测到表格文件上传时，自动通过 pandas 预计算出 100% 准确的统计与对比数据。
    生成结构化摘要，直接注入 Prompt 供模型作为权威基准使用。
    """
    table_files = []
    for f in files:
        name = f.get("name", "")
        path = f.get("path", "")
        ext = os.path.splitext(name)[1].lower()
        if ext in (".xlsx", ".xlsm", ".xls", ".csv") and os.path.isfile(path):
            table_files.append((name, path))

    if not table_files:
        return ""

    sections = []
    loaded_tables = []  # [(filename, sheet_name, df)]

    for filename, filepath in table_files:
        dfs = read_dataframes_from_file(filepath)
        for sname, df in dfs.items():
            if df.empty or df.shape[0] == 0:
                continue
            loaded_tables.append((filename, sname, df))

            # 清理列名空白
            df.columns = [str(c).strip() for c in df.columns]
            rows_count, cols_count = df.shape

            info = [f"### 【表格】{filename}（工作表：{sname}）"]
            info.append(f"- **基本规格**：共 {rows_count} 行 × {cols_count} 列")
            info.append(f"- **所有列名**：{list(df.columns)}")

            # 数值列精确计算
            numeric_cols = []
            for col in df.columns:
                # 尝试将包含数字但被存为字符串的列转为数值
                ser = pd.to_numeric(
                    df[col].astype(str).str.replace(",", "").str.replace("￥", "").str.replace("$", "").str.strip(),
                    errors="coerce"
                )
                if ser.notna().sum() > max(1, rows_count * 0.3):
                    numeric_cols.append((col, ser))

            if numeric_cols:
                info.append("\n**精确数值统计（由 pandas 确定性计算，绝对精准）：**")
                stat_rows = ["| 列名 | 有效数值数 | 缺失数 | 合计总和（Sum） | 平均值（Mean） | 最小值（Min） | 最大值（Max） |",
                             "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
                for col_name, ser in numeric_cols:
                    v_count = ser.notna().sum()
                    m_count = ser.isna().sum()
                    total = ser.sum()
                    mean = ser.mean()
                    min_v = ser.min()
                    max_v = ser.max()
                    stat_rows.append(
                        f"| {col_name} | {v_count} | {m_count} | {total:,.2f} | {mean:,.2f} | {min_v:,.2f} | {max_v:,.2f} |"
                    )
                info.append("\n".join(stat_rows))

            # 分类列核心频次与汇总
            cat_candidates = [c for c in df.columns if c not in [nc[0] for nc in numeric_cols]]
            key_cat_cols = [c for c in cat_candidates if any(k in c for k in ("供应商", "类别", "类型", "部门", "名称", "状态", "物料"))]
            if key_cat_cols and numeric_cols:
                primary_cat = key_cat_cols[0]
                primary_num, primary_ser = numeric_cols[0]
                temp_df = pd.DataFrame({primary_cat: df[primary_cat], primary_num: primary_ser})
                grp = temp_df.groupby(primary_cat)[primary_num].agg(["count", "sum"]).sort_values(by="sum", ascending=False).head(8)
                if not grp.empty:
                    info.append(f"\n**按「{primary_cat}」对「{primary_num}」的分组求和 Top 8：**")
                    grp_rows = [f"| {primary_cat} | 记录条数 | {primary_num} 合计 |", "| :--- | :--- | :--- |"]
                    for idx, r in grp.iterrows():
                        grp_rows.append(f"| {idx} | {int(r['count'])} | {r['sum']:,.2f} |")
                    info.append("\n".join(grp_rows))

            # 数据预览（前 6 行）
            head_preview = df.head(6).to_markdown(index=False) if hasattr(df, "to_markdown") else df.head(6).to_string(index=False)
            info.append(f"\n**数据样本预览（前 6 行）：**\n{head_preview}")

            sections.append("\n".join(info))

    # 多表对比 / 关联对账分析流水线
    if len(loaded_tables) >= 2:
        diff_section = ["\n### 【多表关联与对账对齐分析（确定性流水线）】"]
        t1_name, t1_sheet, df1 = loaded_tables[0]
        t2_name, t2_sheet, df2 = loaded_tables[1]

        # 寻找可能的关联键
        join_keys = []
        for k in ["物资名称", "物料名称", "名称", "规格型号", "规格", "编码", "物料编码", "物资编码", "编号", "供应商"]:
            if k in df1.columns and k in df2.columns:
                join_keys.append(k)

        if not join_keys:
            # 宽松匹配
            for c1 in df1.columns:
                for c2 in df2.columns:
                    if c1 == c2 and df1[c1].dtype == df2[c2].dtype and not np.issubdtype(df1[c1].dtype, np.number):
                        join_keys.append(c1)
                        break

        if join_keys:
            diff_section.append(f"- **自动识别匹配键（Join Key）**：`{join_keys}`")
            # 统计键的覆盖情况
            s1_keys = set(df1[join_keys].astype(str).agg("-".join, axis=1))
            s2_keys = set(df2[join_keys].astype(str).agg("-".join, axis=1))
            matched = s1_keys & s2_keys
            only_1 = s1_keys - s2_keys
            only_2 = s2_keys - s1_keys
            diff_section.append(
                f"- **两表键匹配统计**：表1独有 {len(only_1)} 项，表2独有 {len(only_2)} 项，两表共有交集 {len(matched)} 项。"
            )

            # 若有数量或金额列，做差额比对
            q_cols1 = [c for c in df1.columns if any(w in c for w in ("数", "量", "额", "价"))]
            q_cols2 = [c for c in df2.columns if any(w in c for w in ("数", "量", "额", "价"))]
            if q_cols1 and q_cols2:
                diff_section.append(f"- **表1指标**：{q_cols1} ； **表2指标**：{q_cols2}")
        else:
            diff_section.append("- 两表无直接同名文本键，建议依据表格实际业务含义进行对照。")

        sections.append("\n".join(diff_section))

    result = "\n\n".join(sections)
    header = (
        "=========================================================\n"
        "【确定性数据计算基准（由本地 Python pandas/numpy 预计算生成，100% 绝对权威硬数据）】\n"
        "【核心准则】语言模型直接口算总和、均值、同比极易出错。你在回答任何数据指标、差异对比与汇总时，"
        "必须无条件优先采用以下预计算得出的真实数字，严禁凭心算编造任何统计值！\n"
        "=========================================================\n"
    )
    return header + result


def _find_matching_col(df: pd.DataFrame, aliases: List[str], target_key: Optional[str] = None) -> Optional[str]:
    """智能匹配列名别名，优先精确匹配，对单位和组织、数量等进行语义去歧义。"""
    cols = list(df.columns)
    # 1. 完全精确匹配（忽略两端空格与大小写）
    for a in aliases:
        a_clean = a.strip().lower()
        for c in cols:
            if str(c).strip().lower() == a_clean:
                return c
    # 2. 规范化精确匹配（忽略空格、下划线、斜杠与括号）
    for a in aliases:
        a_norm = re.sub(r"[\s\-_/\\()（）]+", "", a.lower())
        for c in cols:
            c_norm = re.sub(r"[\s\-_/\\()（）]+", "", str(c).strip().lower())
            if a_norm and c_norm == a_norm:
                return c
    # 3. 包含匹配（进行反向防歧义过滤）
    for a in aliases:
        a_clean = a.strip().lower()
        if not a_clean:
            continue
        for c in cols:
            c_str = str(c).strip()
            c_lower = c_str.lower()
            if a_clean not in c_lower:
                continue

            # 防歧义规则 1：若寻找计量单位（单位/计量单位），严禁误匹配机构/调拨单位
            if target_key == "单位" or a in ("单位", "计量单位"):
                org_keywords = ("出", "入", "供", "需", "发", "收", "编制", "项目", "施工", "建设", "使用", "部门", "公司", "负责", "管理")
                if any(w in c_str for w in org_keywords) and c_str not in ("单位", "计量单位", "物资单位", "核算单位"):
                    continue

            # 防歧义规则 2：若寻找数量/调拨量，严禁误匹配价格/金额/编号/序号
            if target_key in ("数量", "调拨量") or "数" in a or "量" in a:
                if any(w in c_str for w in ("单价", "金额", "总价", "税率", "编号", "代码", "序号", "车型", "日期", "时间")):
                    continue

            # 防歧义规则 3：若寻找物资名称，严禁误匹配客户名称/供应商名称/单位名称
            if target_key == "物资名称" or "名称" in a:
                if any(w in c_str for w in ("供应商", "客户", "单位名称", "公司名称", "姓名", "制单人")):
                    continue

            return c
    return None


def _identify_table_role(df: pd.DataFrame, source_name: str, sheet_name: str, index: int, total_tables: int) -> str:
    """智能推断表格在调拨对账流水线中的业务角色：'actual' (调拨实发) 或 'book' (账面存根)。"""
    combined_name = f"{source_name} {sheet_name}".lower()
    cols = [str(c).strip().lower() for c in df.columns]

    # 文件名/工作表名显式语义
    if any(k in combined_name for k in ("调拨", "出库", "实发", "实物", "发料", "发货", "送货", "物流", "调出", "退库")):
        return "actual"
    if any(k in combined_name for k in ("对账", "账面", "财务", "清单", "库存", "台账", "总账", "入账", "核对", "结算", "原数量", "计划")):
        return "book"

    # 表头特征列名显式语义
    has_actual_col = any(any(k in c for k in ("调拨量", "调出量", "实发量", "调出单位", "调拨日期", "退库量")) for c in cols)
    has_book_col = any(any(k in c for k in ("账面数量", "在册数量", "库存量", "应收量", "账面数", "原数量")) for c in cols)
    if has_actual_col and not has_book_col:
        return "actual"
    if has_book_col and not has_actual_col:
        return "book"

    # 双表兜底：默认第 1 表为调拨表，第 2 表为对账表
    if total_tables == 2:
        return "actual" if index == 0 else "book"
    return "actual"


def generate_summary_excel(
    files: List[Dict[str, Any]],
    out_dir: str,
    custom_mapping: Optional[Dict[str, str]] = None,
    sheet_headers: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """「做汇总表」一键生成真实 Excel 插件：
    支持多表（如《调拨汇总样表.xlsx》与《对账清单.xlsx》）关联对账、分组汇总与差额计算，
    导出带标准专业表头、自适应列宽、求和样式的 .xlsx 文件至 output 目录。
    """
    os.makedirs(out_dir, exist_ok=True)
    table_files = [f for f in files if os.path.splitext(f.get("name", ""))[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]

    if not table_files:
        raise ValueError("请先上传至少一个表格文件（Excel 或 CSV）")

    all_dfs = []
    for f in table_files:
        dfs = read_dataframes_from_file(f["path"], sheet_headers=sheet_headers)
        for sname, df in dfs.items():
            if not df.empty:
                df["__source_file__"] = f["name"]
                df["__sheet__"] = sname
                all_dfs.append(df)

    if not all_dfs:
        raise ValueError("上传的文件中未解析到有效表格数据")

    # 规范目标列
    TARGET_COLUMNS = [
        "序号", "调拨量", "调拨日期", "物资类别", "物资名称",
        "规格型号", "单位", "数量", "调出单位", "调入单位", "车型", "备注"
    ]

    ALIAS_MAP = {
        "调拨量": ["调拨量", "已退库量", "退库量", "调出量", "调出数量", "退库数量", "调拨数"],
        "调拨日期": ["调拨日期", "日期", "业务日期", "出库日期", "变动日期"],
        "物资类别": ["物资类别", "类别", "物料类别", "分类", "物料分类"],
        "物资名称": ["物资名称", "物料名称", "名称", "品名", "材料名称", "项目名称"],
        "规格型号": ["规格型号", "规格", "型号", "材质/规格"],
        "单位": ["单位", "计量单位"],
        "数量": ["数量", "在用量", "库存量", "在册数量", "原数量", "实际数量", "金额"],
        "调出单位": ["调出单位", "供方", "供方单位", "发料单位", "出库单位", "调出方"],
        "调入单位": ["调入单位", "需方", "需方单位", "收料单位", "入库单位", "调入方"],
        "车型": ["车型", "车牌", "车号", "车辆"],
        "备注": ["备注", "说明", "差异说明", "状态"]
    }

    # 如果有多个表，合并、对账并标准化
    rows_data = []

    for df_idx, df in enumerate(all_dfs):
        df.columns = [str(c).strip() for c in df.columns]
        role = _identify_table_role(df, df.get("__source_file__", ""), df.get("__sheet__", ""), df_idx, len(all_dfs))
        matched_map = {}
        for target, aliases in ALIAS_MAP.items():
            found = None
            if custom_mapping:
                # 检查直接映射或同义映射
                custom_keys = [target]
                if target == "调出单位":
                    custom_keys.extend(["调出方", "供方"])
                elif target == "调入单位":
                    custom_keys.extend(["调入方", "需方"])
                elif target == "调拨日期":
                    custom_keys.extend(["日期", "业务日期"])
                for ck in custom_keys:
                    col_cand = custom_mapping.get(ck)
                    if col_cand and col_cand in df.columns:
                        found = col_cand
                        break
            if not found:
                found = _find_matching_col(df, aliases, target)
            if found:
                matched_map[target] = found

        for idx, row in df.iterrows():
            item = {}
            for target in TARGET_COLUMNS:
                if target == "序号":
                    continue
                src_col = matched_map.get(target)
                if src_col and pd.notna(row[src_col]):
                    val = row[src_col]
                    if isinstance(val, (int, float, np.number)):
                        val = round(float(val), 2)
                    item[target] = val
                else:
                    item[target] = "待补充" if target in ("调拨日期", "调入单位", "车型") else ""

            # 若当前表格是调拨表（实际发生），且仅有数量而无调拨量列，则将该数量转为调拨量
            if role == "actual" and len(all_dfs) >= 2:
                if item.get("数量") and not item.get("调拨量"):
                    item["调拨量"] = item["数量"]
                    item["数量"] = 0.0

            # 若名称和规格均为空则跳过空行
            if not item.get("物资名称") and not item.get("物资类别") and not item.get("数量") and not item.get("调拨量"):
                continue

            rows_data.append(item)

    # 如果没有找到任何标准字段，直接采用第一张表内容作为汇总主体
    if not rows_data:
        first_df = all_dfs[0].copy()
        first_df.drop(columns=["__source_file__", "__sheet__"], errors="ignore", inplace=True)
        export_df = first_df
    else:
        base_df = pd.DataFrame(rows_data)
        # 多表智能对账归并：按 物资名称 (+ 规格型号) 聚合对齐两表数据
        if "物资名称" in base_df.columns and len(all_dfs) >= 2:
            group_keys = ["物资名称"]
            if "规格型号" in base_df.columns:
                group_keys.append("规格型号")

            merged_rows = []
            for _, grp in base_df.groupby(group_keys, as_index=False):
                merged_item = {}
                for target in TARGET_COLUMNS:
                    if target == "序号":
                        continue
                    if target in ("数量", "调拨量"):
                        ser = pd.to_numeric(grp[target], errors="coerce").dropna()
                        merged_item[target] = round(float(ser.sum()), 2) if not ser.empty else 0.0
                    else:
                        vals = [v for v in grp[target] if v and str(v).strip() not in ("待补充", "")]
                        merged_item[target] = vals[0] if vals else (grp[target].iloc[0] if not grp[target].empty else "")

                # 自动计算差额与对账备注
                q_val = merged_item.get("数量", 0.0)
                t_val = merged_item.get("调拨量", 0.0)
                if q_val and t_val and abs(q_val - t_val) > 0.001:
                    diff = round(q_val - t_val, 2)
                    merged_item["备注"] = f"对账差额: {diff:+} (原数量{q_val} vs 调拨{t_val})"
                elif q_val and t_val:
                    merged_item["备注"] = "账实相符"
                elif q_val and not t_val:
                    merged_item["备注"] = f"仅账面有记录 (原数量{q_val})"
                elif not q_val and t_val:
                    merged_item["备注"] = f"仅调拨有记录 (调拨量{t_val})"

                merged_rows.append(merged_item)
            export_df = pd.DataFrame(merged_rows)
        else:
            export_df = base_df

        # 重新排序并加上标准序号
        cols = [c for c in TARGET_COLUMNS if c in export_df.columns]
        export_df = export_df[cols]
        export_df.insert(0, "序号", range(1, len(export_df) + 1))

    # 使用 openpyxl 写入高质量 Excel
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = f"调拨对账汇总表-{stamp}.xlsx"
    out_path = os.path.join(out_dir, out_filename)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "物资调拨汇总表"

    # 表头大标题
    ws.merge_cells("A1:L1")
    title_cell = ws["A1"]
    title_cell.value = "物资调拨与对账清算汇总表"
    title_cell.font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    title_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 36

    # 副标题（生成时间与数据源）
    ws.merge_cells("A2:L2")
    sub_cell = ws["A2"]
    sub_cell.value = f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  数据来源：{', '.join(f['name'] for f in table_files)}  |  由确定性计算引擎校验对齐"
    sub_cell.font = Font(name="微软雅黑", size=9, color="6E6E73", italic=True)
    sub_cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18

    # 表头定义
    headers = list(export_df.columns)
    ws.append(headers)
    ws.row_dimensions[3].height = 26

    head_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    thin_border = Side(style="thin", color="D9D9D9")
    box_border = Border(left=thin_border, right=thin_border, top=thin_border, bottom=thin_border)

    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=3, column=c)
        cell.fill = head_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = box_border

    # 数据行
    total_qty = 0.0
    total_transfer = 0.0
    data_start_row = 4

    for r_idx, row in export_df.iterrows():
        current_row_idx = data_start_row + r_idx
        row_vals = []
        for c in headers:
            v = row[c]
            # 数值类型尝试转换
            if c in ("调拨量", "数量"):
                try:
                    num_v = float(str(v).replace(",", "").strip())
                    row_vals.append(num_v)
                    if c == "数量":
                        total_qty += num_v
                    elif c == "调拨量":
                        total_transfer += num_v
                    continue
                except (ValueError, TypeError):
                    pass
            row_vals.append(v)

        ws.append(row_vals)
        ws.row_dimensions[current_row_idx].height = 20

        # 行斑马纹与边框
        row_fill = PatternFill("solid", fgColor="FBFBFD") if r_idx % 2 == 1 else PatternFill(fill_type=None)
        for col_idx in range(1, len(headers) + 1):
            c_cell = ws.cell(row=current_row_idx, column=col_idx)
            if row_fill.fill_type:
                c_cell.fill = row_fill
            c_cell.border = box_border
            c_cell.font = Font(name="微软雅黑", size=9.5)
            # 对齐
            h_name = headers[col_idx - 1]
            if h_name in ("序号", "单位", "车型", "调拨日期"):
                c_cell.alignment = Alignment(horizontal="center", vertical="center")
            elif h_name in ("调拨量", "数量"):
                c_cell.alignment = Alignment(horizontal="right", vertical="center")
                c_cell.number_format = "#,##0.00"
            else:
                c_cell.alignment = Alignment(horizontal="left", vertical="center")

    # 合计行
    summary_row_idx = data_start_row + len(export_df)
    summary_cells = ["合计", "", "", "", f"共 {len(export_df)} 项明细", "", "", total_qty, "", "", "", ""]
    # 填充调拨量
    if "调拨量" in headers:
        t_pos = headers.index("调拨量")
        summary_cells[t_pos] = total_transfer
    if "数量" in headers:
        q_pos = headers.index("数量")
        summary_cells[q_pos] = total_qty

    ws.append(summary_cells)
    ws.row_dimensions[summary_row_idx].height = 24

    sum_fill = PatternFill("solid", fgColor="EBF3FA")
    double_bottom = Border(top=Side(style="thin", color="1F4E79"), bottom=Side(style="double", color="1F4E79"))
    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=summary_row_idx, column=col_idx)
        cell.fill = sum_fill
        cell.font = Font(name="微软雅黑", size=10, bold=True, color="1F4E79")
        cell.border = double_bottom
        h_name = headers[col_idx - 1]
        if h_name in ("调拨量", "数量"):
            cell.alignment = Alignment(horizontal="right", vertical="center")
            cell.number_format = "#,##0.00"
        else:
            cell.alignment = Alignment(horizontal="center", vertical="center")

    # 列宽自适应
    for c in range(1, len(headers) + 1):
        col_letter = get_column_letter(c)
        max_len = len(str(headers[c - 1])) * 2
        for r in range(data_start_row, min(summary_row_idx, data_start_row + 50)):
            v = str(ws.cell(row=r, column=c).value or "")
            max_len = max(max_len, len(v.encode("gbk", "ignore") if isinstance(v, str) else str(v)))
        ws.column_dimensions[col_letter].width = min(max(10, max_len + 3), 42)

    ws.freeze_panes = "A4"
    wb.save(out_path)

    fsize = os.path.getsize(out_path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
    diff_val = round(total_qty - total_transfer, 2)
    diff_str = f"+{diff_val:,.1f}" if diff_val > 0 else f"{diff_val:,.1f}"
    kpis = [
        {"label": "核对明细", "value": f"{len(export_df)} 行", "icon": "📋", "status": "info"},
        {"label": "数量合计", "value": f"{total_qty:,.1f}", "icon": "📦", "status": "info"},
        {"label": "调拨合计", "value": f"{total_transfer:,.1f}", "icon": "🔄", "status": "info"},
        {"label": "对账差额", "value": diff_str, "icon": "⚠️", "status": "warn" if abs(diff_val) > 0.001 else "success", "alert": abs(diff_val) > 0.001},
    ]

    diff_indices = []
    if "数量" in export_df.columns and "调拨量" in export_df.columns:
        for ridx, row in export_df.head(50).iterrows():
            try:
                q1 = float(row.get("数量") or 0)
                q2 = float(row.get("调拨量") or 0)
                if abs(q1 - q2) > 0.001:
                    diff_indices.append(int(ridx))
            except Exception:
                pass

    return {
        "ok": True,
        "filename": out_filename,
        "path": out_path,
        "filepath": out_path,
        "filesize": fsize_str,
        "filetype": "excel",
        "rows": len(export_df),
        "total_qty": round(total_qty, 2),
        "total_transfer": round(total_transfer, 2),
        "kpi_metrics": kpis,
        "preview_data": {
            "columns": list(export_df.columns),
            "rows": export_df.head(50).fillna("").values.tolist(),
            "total_rows": len(export_df),
            "diff_indices": diff_indices,
        },
        "url": f"/files/{out_filename}",
    }


def get_table_columns_and_candidates(
    files: List[Dict[str, Any]],
    sheet_headers: Optional[Dict[str, int]] = None
) -> Dict[str, Any]:
    """读取所有上传表格的表头与候选映射列，支持前端下拉选择及前 2 行真实数据样本预览。"""
    table_files = [f for f in files if os.path.splitext(f.get("name", ""))[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]
    if not table_files:
        return {"ok": False, "files": [], "all_columns": [], "target_fields": [], "suggested_mapping": {}, "column_samples": {}, "detected_header_row": 1}

    extracted_files = []
    combined_cols = []
    all_col_set = set()
    all_column_samples = {}

    TARGET_FIELDS = [
        {"key": "物资名称", "label": "物资名称", "required": True, "aliases": ["物资名称", "物料名称", "名称", "品名", "材料名称", "项目名称", "物料品名"]},
        {"key": "规格型号", "label": "规格型号", "required": False, "aliases": ["规格型号", "规格", "型号", "材质/规格", "型号标号"]},
        {"key": "数量", "label": "数量（账面/原数量）", "required": True, "aliases": ["数量", "原数量", "账面数量", "在用量", "库存量", "计划量", "调拨量", "调出量", "发货数", "实收数量"]},
        {"key": "调出方", "label": "调出方（供方单位）", "required": False, "aliases": ["调出方", "调出单位", "供方", "供方单位", "发料单位", "出库单位", "发货单位"]},
        {"key": "调入方", "label": "调入方（需方单位）", "required": False, "aliases": ["调入方", "调入单位", "需方", "需方单位", "收料单位", "入库单位", "使用部门"]},
        {"key": "日期", "label": "业务日期", "required": False, "aliases": ["日期", "调拨日期", "业务日期", "出库日期", "变动日期", "制单日期"]}
    ]

    for f in table_files:
        path = f.get("path", "")
        if not os.path.isfile(path):
            continue
        dfs = read_dataframes_from_file(path, sheet_headers=sheet_headers)
        f_info = {"name": f.get("name", ""), "sheets": []}
        for sname, df in dfs.items():
            cols = [str(c).strip() for c in df.columns]
            for c in cols:
                if c not in all_col_set:
                    all_col_set.add(c)
                    combined_cols.append(c)

            h_idx = df.attrs.get("header_row_index", 0)
            col_samples = {}
            for c in df.columns:
                c_str = str(c).strip()
                ser_vals = [str(v).strip() for v in df[c].dropna().tolist() if str(v).strip() != "" and str(v).strip().lower() != "nan"]
                col_samples[c_str] = ser_vals[:2]
                if c_str not in all_column_samples:
                    all_column_samples[c_str] = ser_vals[:2]

            f_info["sheets"].append({
                "sheet_name": sname,
                "columns": cols,
                "row_count": len(df),
                "header_row_index": h_idx,
                "header_row_display": h_idx + 1,
                "column_samples": col_samples,
                "preview": df.head(5).fillna("").to_dict(orient="records")
            })
        extracted_files.append(f_info)

    suggested = {}
    dummy_df = pd.DataFrame(columns=combined_cols)
    for target in TARGET_FIELDS:
        found_col = _find_matching_col(dummy_df, target["aliases"], target["key"]) or ""
        suggested[target["key"]] = found_col

    primary_header_display = 1
    if extracted_files and extracted_files[0].get("sheets"):
        primary_header_display = extracted_files[0]["sheets"][0].get("header_row_display", 1)

    return {
        "ok": True,
        "files": extracted_files,
        "all_columns": combined_cols,
        "column_samples": all_column_samples,
        "detected_header_row": primary_header_display,
        "target_fields": TARGET_FIELDS,
        "suggested_mapping": suggested
    }


def generate_reconciliation_audit(
    files: List[Dict[str, Any]],
    custom_mapping: Optional[Dict[str, str]] = None,
    sheet_headers: Optional[Dict[str, int]] = None,
    custom_rules: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """生成《数据校验验收单》：
    自动核对两表合计、计算账实差额，分类归纳：
    1. 统计口径说明
    2. 校验通过项（账实相符 X 笔）
    3. 差异/异常清单（差额 X 笔、缺失值 X 处）
    4. KPI 数据指标与标准化 Markdown 格式文本
    """
    table_files = [f for f in files if os.path.splitext(f.get("name", ""))[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]
    if not table_files:
        raise ValueError("请上传包含调拨表或对账单的表格文件")

    all_dfs = []
    for f in table_files:
        dfs = read_dataframes_from_file(f["path"], sheet_headers=sheet_headers)
        for sname, df in dfs.items():
            if not df.empty:
                df["__source_file__"] = f["name"]
                df["__sheet__"] = sname
                all_dfs.append(df)

    if not all_dfs:
        raise ValueError("上传的文件中未解析到有效表格数据")

    ALIAS_MAP = {
        "物资名称": ["物资名称", "物料名称", "名称", "品名", "材料名称", "项目名称", "物料品名"],
        "规格型号": ["规格型号", "规格", "型号", "材质/规格", "型号标号"],
        "单位": ["单位", "计量单位", "物理单位"],
        "数量": ["数量", "在用量", "库存量", "在册数量", "原数量", "实际数量", "金额", "发货数", "实收数量"],
        "调拨量": ["调拨量", "已退库量", "退库量", "调出量", "调出数量", "退库数量", "调拨数"],
        "调出方": ["调出方", "调出单位", "供方", "供方单位", "发料单位", "出库单位", "调出项目", "发货地"],
        "调入方": ["调入方", "调入单位", "需方", "需方单位", "收料单位", "入库单位", "调入项目", "目的地"],
        "日期": ["日期", "调拨日期", "业务日期", "出库日期", "变动日期", "发车时间"],
    }

    norm_mapping = {}
    if custom_mapping:
        for k, v in custom_mapping.items():
            if k in ALIAS_MAP:
                norm_mapping[k] = v
            elif v in ALIAS_MAP:
                norm_mapping[v] = k
            else:
                norm_mapping[k] = v

    # 规范化每张表
    normalized_records = []
    missing_value_count = 0

    for df_idx, df in enumerate(all_dfs):
        df.columns = [str(c).strip() for c in df.columns]
        role = _identify_table_role(df, df.get("__source_file__", ""), df.get("__sheet__", ""), df_idx, len(all_dfs))
        matched = {}
        for target, aliases in ALIAS_MAP.items():
            mapped_col = None
            if norm_mapping:
                mapped_col = norm_mapping.get(target)
                if target == "数量" and not mapped_col:
                    mapped_col = norm_mapping.get("调拨量")
                elif target == "调出方" and not mapped_col:
                    mapped_col = norm_mapping.get("调出单位")
                elif target == "调入方" and not mapped_col:
                    mapped_col = norm_mapping.get("调入单位")
                elif target == "日期" and not mapped_col:
                    mapped_col = norm_mapping.get("调拨日期")
            if mapped_col and mapped_col in df.columns:
                matched[target] = mapped_col
            else:
                found = _find_matching_col(df, aliases, target)
                if found:
                    matched[target] = found

        for idx, row in df.iterrows():
            rec = {
                "__file__": df["__source_file__"].iloc[0] if "__source_file__" in df else "",
                "name": "",
                "spec": "",
                "unit": "",
                "book_qty": None,
                "actual_qty": None,
                "supplier": "",
                "receiver": "",
                "date": ""
            }

            if matched.get("物资名称") and pd.notna(row[matched["物资名称"]]):
                rec["name"] = str(row[matched["物资名称"]]).strip()
            else:
                missing_value_count += 1

            if matched.get("规格型号") and pd.notna(row[matched["规格型号"]]):
                rec["spec"] = str(row[matched["规格型号"]]).strip()
            if matched.get("单位") and pd.notna(row[matched["单位"]]):
                rec["unit"] = str(row[matched["单位"]]).strip()
            if matched.get("调出方") and pd.notna(row[matched["调出方"]]):
                rec["supplier"] = str(row[matched["调出方"]]).strip()
            if matched.get("调入方") and pd.notna(row[matched["调入方"]]):
                rec["receiver"] = str(row[matched["调入方"]]).strip()
            if matched.get("日期") and pd.notna(row[matched["日期"]]):
                rec["date"] = str(row[matched["日期"]]).strip()

            # 解析数量 / 调拨量
            raw_qty = None
            if matched.get("数量") and pd.notna(row[matched["数量"]]):
                try:
                    cleaned_q = str(row[matched["数量"]]).replace(",", "").replace("￥", "").strip()
                    raw_qty = float(cleaned_q)
                except (ValueError, TypeError):
                    missing_value_count += 1

            raw_transfer = None
            if matched.get("调拨量") and pd.notna(row[matched["调拨量"]]):
                try:
                    cleaned_t = str(row[matched["调拨量"]]).replace(",", "").replace("￥", "").strip()
                    raw_transfer = float(cleaned_t)
                except (ValueError, TypeError):
                    pass

            if raw_qty is not None and raw_transfer is not None and matched.get("数量") != matched.get("调拨量"):
                rec["book_qty"] = raw_qty
                rec["actual_qty"] = raw_transfer
            elif raw_transfer is not None:
                rec["actual_qty"] = raw_transfer
            elif raw_qty is not None:
                if role == "actual" and len(all_dfs) >= 2:
                    rec["actual_qty"] = raw_qty
                else:
                    rec["book_qty"] = raw_qty

            rec["__raw_row__"] = {str(col).strip(): row[col] for col in df.columns if pd.notna(row[col])}
            rec["__df_role__"] = role
            rec["__df_idx__"] = df_idx

            if rec["name"]:
                normalized_records.append(rec)

    # 按照 (name, spec) 聚合多表记录
    grouped = {}
    for r in normalized_records:
        k = (r["name"], r["spec"])
        if k not in grouped:
            grouped[k] = {
                "name": r["name"],
                "spec": r["spec"],
                "unit": r["unit"] or "",
                "book_qty_list": [],
                "actual_qty_list": [],
                "suppliers": set(),
                "receivers": set(),
                "dates": set(),
                "files": set(),
                "records_a": [],
                "records_b": [],
            }
        g = grouped[k]
        if len(all_dfs) >= 2:
            if r.get("__df_idx__", 0) == 0:
                g["records_a"].append(r)
            else:
                g["records_b"].append(r)
        else:
            g["records_a"].append(r)
            g["records_b"].append(r)
        if r["unit"] and not g["unit"]:
            g["unit"] = r["unit"]
        if r["book_qty"] is not None:
            g["book_qty_list"].append(r["book_qty"])
        if r["actual_qty"] is not None:
            g["actual_qty_list"].append(r["actual_qty"])
        if r["supplier"]:
            g["suppliers"].add(r["supplier"])
        if r["receiver"]:
            g["receivers"].add(r["receiver"])
        if r["date"]:
            g["dates"].add(r["date"])
        if r["__file__"]:
            g["files"].add(r["__file__"])

    passed_items = []
    discrepancy_items = []
    missing_items = []

    for k, g in grouped.items():
        name, spec = k
        unit = g["unit"] or "件/吨"
        supplier_str = " / ".join(filter(None, g["suppliers"])) or "-"
        receiver_str = " / ".join(filter(None, g["receivers"])) or "-"
        date_str = " / ".join(filter(None, g["dates"])) or "-"

        # 计算账面数量与调拨量
        book_val = round(sum(g["book_qty_list"]), 2) if g["book_qty_list"] else 0.0
        actual_val = round(sum(g["actual_qty_list"]), 2) if g["actual_qty_list"] else 0.0

        diff = round(book_val - actual_val, 2)
        diff_str = f"+{diff:,.2f}" if diff > 0 else (f"{diff:,.2f}" if diff < 0 else "0.00")

        item_entry = {
            "name": name,
            "spec": spec or "-",
            "unit": unit,
            "book_qty": book_val,
            "actual_qty": actual_val,
            "diff": diff,
            "diff_str": diff_str,
            "supplier": supplier_str,
            "receiver": receiver_str,
            "date": date_str,
        }

        if book_val > 0 and actual_val > 0:
            if abs(diff) <= 0.001:
                item_entry["status"] = "账实相符"
                passed_items.append(item_entry)
            else:
                item_entry["status"] = "存在差额"
                item_entry["reason"] = f"账面数量比实际调拨量{'多' if diff > 0 else '少'} {abs(diff):,.2f} {unit}"
                discrepancy_items.append(item_entry)
        elif book_val > 0 and actual_val == 0.0:
            item_entry["status"] = "仅账面有记录"
            item_entry["reason"] = "对账清单已入账，但调拨单缺失对应调拨记录"
            discrepancy_items.append(item_entry)
            missing_items.append(item_entry)
        elif book_val == 0.0 and actual_val > 0:
            item_entry["status"] = "仅调拨有记录"
            item_entry["reason"] = "调拨单已发生调拨，但对账清单账面未建立存根"
            discrepancy_items.append(item_entry)
            missing_items.append(item_entry)
        else:
            item_entry["status"] = "数量为零/缺失"
            item_entry["reason"] = "两表数量均为 0 或无法提取数值"
            discrepancy_items.append(item_entry)
            missing_items.append(item_entry)

    custom_rule_summaries = []
    if custom_rules:
        for cr in custom_rules:
            if not isinstance(cr, dict):
                continue
            r_name = str(cr.get("name") or "自定义核对规则").strip()
            rule_type = cr.get("rule_type") or "text_exact"
            tolerance = float(cr.get("tolerance") or 0.0)
            col_a = cr.get("col_a")
            col_b = cr.get("col_b")
            has_cols = bool(col_a and col_b)

            rule_violated_count = 0
            for g_key, g_val in grouped.items():
                name, spec = g_key
                book_val = round(sum(g_val["book_qty_list"]), 2) if g_val["book_qty_list"] else 0.0
                actual_val = round(sum(g_val["actual_qty_list"]), 2) if g_val["actual_qty_list"] else 0.0
                violated = False
                fail_reason = ""

                # 提取特定列值（若用户指定了表A与表B字段）
                val_a = None
                val_b = None
                if has_cols:
                    recs_a = g_val.get("records_a", [])
                    recs_b = g_val.get("records_b", [])
                    for r in recs_a:
                        if col_a in r.get("__raw_row__", {}):
                            val_a = r["__raw_row__"][col_a]
                            break
                    for r in recs_b:
                        if col_b in r.get("__raw_row__", {}):
                            val_b = r["__raw_row__"][col_b]
                            break
                    if val_a is None:
                        for r in recs_b:
                            if col_a in r.get("__raw_row__", {}):
                                val_a = r["__raw_row__"][col_a]
                                break
                    if val_b is None:
                        for r in recs_a:
                            if col_b in r.get("__raw_row__", {}):
                                val_b = r["__raw_row__"][col_b]
                                break

                if has_cols and val_a is not None and val_b is not None:
                    str_a = str(val_a).strip()
                    str_b = str(val_b).strip()
                    if rule_type == "text_exact":
                        if str_a != str_b:
                            violated = True
                            fail_reason = f"【{col_a}】与【{col_b}】文本不一致：'{str_a}' vs '{str_b}'"
                    elif rule_type == "num_exact":
                        try:
                            num_a = float(str_a.replace(",", "").replace("￥", "").replace("¥", ""))
                            num_b = float(str_b.replace(",", "").replace("￥", "").replace("¥", ""))
                            if abs(num_a - num_b) > 0.001:
                                violated = True
                                fail_reason = f"【{col_a}】与【{col_b}】数值不相等：{num_a} vs {num_b}"
                        except Exception:
                            if str_a != str_b:
                                violated = True
                                fail_reason = f"【{col_a}】与【{col_b}】非数值无法比对或不相等：'{str_a}' vs '{str_b}'"
                    elif rule_type == "tolerance":
                        try:
                            num_a = float(str_a.replace(",", "").replace("￥", "").replace("¥", ""))
                            num_b = float(str_b.replace(",", "").replace("￥", "").replace("¥", ""))
                            diff_num = abs(num_a - num_b)
                            if diff_num > tolerance:
                                violated = True
                                fail_reason = f"【{col_a}】与【{col_b}】差额 {diff_num:,.2f} 超出允许误差 ±{tolerance}"
                        except Exception:
                            pass
                    elif rule_type == "qty_ge":
                        try:
                            num_a = float(str_a.replace(",", "").replace("￥", "").replace("¥", ""))
                            num_b = float(str_b.replace(",", "").replace("￥", "").replace("¥", ""))
                            if num_b < num_a:
                                violated = True
                                fail_reason = f"调出数量({num_b}) 小于 实收数量({num_a})"
                        except Exception:
                            if actual_val > 0 and book_val > 0 and actual_val < book_val:
                                violated = True
                                fail_reason = f"调出数量({actual_val}) 小于 实收账面数量({book_val})"
                    elif rule_type == "ratio_diff":
                        try:
                            num_a = float(str_a.replace(",", "").replace("￥", "").replace("¥", ""))
                            num_b = float(str_b.replace(",", "").replace("￥", "").replace("¥", ""))
                            if num_b > 0:
                                ratio = abs(num_a - num_b) / num_b
                                max_ratio = tolerance if tolerance > 0 else 0.05
                                if ratio > max_ratio:
                                    violated = True
                                    fail_reason = f"【{col_a}】与【{col_b}】差异比例 {ratio*100:.1f}% 超过允许上限 {max_ratio*100:.1f}%"
                        except Exception:
                            pass
                elif has_cols and (val_a is None or val_b is None):
                    violated = True
                    missing_col = col_a if val_a is None else col_b
                    fail_reason = f"条目缺失比对字段【{missing_col}】"
                else:
                    if rule_type == "text_exact":
                        if spec and spec != "-" and actual_val > 0 and book_val > 0:
                            pass
                    elif rule_type == "qty_ge":
                        if actual_val > 0 and book_val > 0 and (actual_val < book_val):
                            violated = True
                            fail_reason = f"调出数量({actual_val}) 小于 实收账面数量({book_val})"
                    elif rule_type == "tolerance":
                        diff_abs = abs(book_val - actual_val)
                        if diff_abs > tolerance:
                            violated = True
                            fail_reason = f"差额 {diff_abs:,.2f} 超出允许误差 ±{tolerance}"
                    elif rule_type == "ratio_diff":
                        if actual_val > 0:
                            ratio = abs(book_val - actual_val) / actual_val
                            max_ratio = tolerance if tolerance > 0 else 0.05
                            if ratio > max_ratio:
                                violated = True
                                fail_reason = f"差额比例 {ratio*100:.1f}% 超过允许偏离比例 {max_ratio*100:.1f}%"
                    elif rule_type == "num_exact":
                        if abs(book_val - actual_val) > 0.001:
                            violated = True
                            fail_reason = f"数值不相等：{book_val} vs {actual_val}"

                if violated:
                    rule_violated_count += 1
                    existing = next((d for d in discrepancy_items if d["name"] == name and d["spec"] == spec), None)
                    if existing:
                        existing["reason"] = f"{existing.get('reason', '')} | 规则预警：{fail_reason}"
                    else:
                        discrepancy_items.append({
                            "name": name,
                            "spec": spec or "-",
                            "unit": g_val["unit"] or "件/吨",
                            "book_qty": book_val,
                            "actual_qty": actual_val,
                            "diff": round(book_val - actual_val, 2),
                            "diff_str": f"{round(book_val - actual_val, 2):,.2f}",
                            "status": "规则校验不符",
                            "reason": f"自定义规则【{r_name}】未通过：{fail_reason}",
                            "is_custom_rule": True,
                        })
                    passed_items = [p for p in passed_items if not (p["name"] == name and p["spec"] == spec)]

            custom_rule_summaries.append({
                "name": r_name,
                "rule_type": rule_type,
                "violated_count": rule_violated_count,
                "status": f"已校验（检出 {rule_violated_count} 处异常）" if rule_violated_count > 0 else "完全符合规则"
            })

    total_rows = len(grouped)
    passed_count = len(passed_items)
    discrepancy_count = len(discrepancy_items)
    missing_count = len(missing_items) + missing_value_count

    total_book = sum(i["book_qty"] for i in passed_items + discrepancy_items)
    total_actual = sum(i["actual_qty"] for i in passed_items + discrepancy_items)
    net_diff = round(total_book - total_actual, 2)
    net_diff_str = f"+{net_diff:,.2f}" if net_diff > 0 else (f"{net_diff:,.2f}" if net_diff < 0 else "0.00")
    pass_rate = round(passed_count / total_rows * 100, 1) if total_rows > 0 else 0.0

    scope_description = (
        "【统计口径说明】本次核对由本地 Python 确定性计算引擎（pandas/numpy）自动化执行。"
        "核对基准：以「物资名称 + 规格型号」为主键进行跨表关联与去重对齐；"
        "核对计算公式：差额 = 账面数量 - 实际调拨量；"
        "判定标准：|差额| ≤ 0.001 判定为「✅ 账实相符」；|差额| > 0.001 判定为「⚠️ 存在差额」；"
        "单边记录缺失或必要字段空缺判定为「缺失值/未完全匹配」。"
    )

    # 构造 Markdown 格式的《数据校验验收单》
    md_lines = [
        "# 《数据校验验收单》（物资调拨与对账核验）",
        f"> **生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  **核对数据源**：{', '.join(f['name'] for f in table_files)}",
        "",
        f"### 一、统计口径说明",
        scope_description,
        "",
        "### 二、总体核验指标",
        f"- **总核对明细项**：{total_rows} 笔",
        f"- **✅ 校验通过项（账实相符）**：{passed_count} 笔（占比 {pass_rate}%）",
        f"- **⚠️ 差异/异常清单（差额/缺失）**：差额 {discrepancy_count} 笔、缺失值 {missing_count} 处",
        f"- **账面数量合计**：{total_book:,.2f}",
        f"- **实际调拨量合计**：{total_actual:,.2f}",
        f"- **净差额合计**：{net_diff_str}",
        "",
        f"### 三、✅ 校验通过项（账实相符 {passed_count} 笔）",
    ]

    if passed_items:
        md_lines.append("| 序号 | 物资名称 | 规格型号 | 单位 | 账面数量 | 实际调拨量 | 差额 | 核验状态 | 供方/调出方 | 需方/调入方 |")
        md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for p_idx, p in enumerate(passed_items, 1):
            md_lines.append(f"| {p_idx} | {p['name']} | {p['spec']} | {p['unit']} | {p['book_qty']:,.2f} | {p['actual_qty']:,.2f} | 0.00 | ✅ 账实相符 | {p['supplier']} | {p['receiver']} |")
    else:
        md_lines.append("（暂无完全账实相符项）")

    md_lines.append("")
    md_lines.append(f"### 四、⚠️ 差异/异常清单（差额 {discrepancy_count} 笔、缺失值 {missing_count} 处）")

    if discrepancy_items:
        md_lines.append("| 序号 | 物资名称 | 规格型号 | 单位 | 账面数量 | 实际调拨量 | 差额 | 预警状态 | 差异原因诊断 |")
        md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
        for d_idx, d in enumerate(discrepancy_items, 1):
            md_lines.append(f"| {d_idx} | {d['name']} | {d['spec']} | {d['unit']} | {d['book_qty']:,.2f} | {d['actual_qty']:,.2f} | **{d['diff_str']}** | ⚠️ {d['status']} | {d.get('reason', '-')} |")
    else:
        md_lines.append("（未发现任何差额或异常项）")

    markdown_report = "\n".join(md_lines)

    kpi_metrics = [
        {"label": "核查明细", "value": f"{total_rows} 笔", "icon": "📋", "status": "info"},
        {"label": "账实相符", "value": f"{passed_count} 笔", "icon": "✅", "status": "success"},
        {"label": "存在差额", "value": f"{discrepancy_count} 笔", "icon": "⚠️", "status": "warn" if discrepancy_count > 0 else "success", "alert": discrepancy_count > 0},
        {"label": "缺失值/异常", "value": f"{missing_count} 处", "icon": "🔍", "status": "warn" if missing_count > 0 else "info"},
        {"label": "净差额", "value": net_diff_str, "icon": "📊", "status": "warn" if abs(net_diff) > 0.001 else "success"}
    ]

    return {
        "ok": True,
        "title": "数据校验验收单",
        "scope_description": scope_description,
        "passed_count": passed_count,
        "discrepancy_count": discrepancy_count,
        "match_count": passed_count,
        "diff_count": discrepancy_count,
        "missing_count": missing_count,
        "total_count": total_rows,
        "total_qty": round(total_book, 2),
        "total_transfer": round(total_actual, 2),
        "actual_total": round(total_actual, 2),
        "book_total": round(total_book, 2),
        "diff_list": [f"{d['name']} {d['spec']}: 差额 {d['diff_str']} ({d.get('reason', '')})" for d in discrepancy_items],
        "net_diff": net_diff,
        "net_diff_str": net_diff_str,
        "pass_rate": pass_rate,
        "passed_items": passed_items,
        "discrepancy_items": discrepancy_items,
        "missing_items": missing_items,
        "kpi_metrics": kpi_metrics,
        "custom_rules_summary": custom_rule_summaries,
        "markdown": markdown_report
    }


def calculate_supplier_price_comparison(
    files: List[Dict[str, Any]],
    weights: Optional[Dict[str, float]] = None,
    tax_rate: float = 0.13,
    annual_interest_rate: float = 0.06,
    benchmark_tax_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """多供应商报价横向比选、确定性 TCO 计算与加权打分引擎。
    1. 统一税率基准换算含税与未税单价；
    2. 按年化利率（默认6%）折算账期资金占用利息收益与需方运费调整；
    3. 标记各材料最低价并计算差价率；
    4. 自动筛出漏填交期或运费的「待核实项」；
    5. 基于权重配置（默认价格40%、交期20%、账期20%、质量20%）计算综合加权评分矩阵，输出授标推荐与分供应商谈判要点。
    """
    if benchmark_tax_rate is not None:
        tax_rate = benchmark_tax_rate
    table_files = [f for f in files if os.path.splitext(f.get("name", ""))[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]
    if not table_files:
        raise ValueError("请上传包含报价清单的表格文件")

    # Default weights
    w = {
        "price": 0.40,
        "delivery": 0.20,
        "payment": 0.20,
        "quality": 0.20,
    }
    if weights and isinstance(weights, dict):
        total_w = sum(float(weights.get(k, 0)) for k in w)
        if total_w > 0:
            for k in w:
                if k in weights:
                    w[k] = float(weights[k]) / (total_w if total_w > 1.01 or total_w < 0.99 else 1.0)

    # Read dataframes
    all_dfs = []
    for f in table_files:
        f_dfs = read_dataframes_from_file(f["path"])
        fname = f.get("name", "")
        # Clean default vendor name from filename
        default_vendor = re.sub(r"^(?:报价单|报价明细|材料报价)[-_—]?", "", os.path.splitext(fname)[0])
        default_vendor = re.sub(r"[-_—]?(?:报价单|报价明细|报价)$", "", default_vendor).strip() or default_vendor

        for sname, df in f_dfs.items():
            if not df.empty and df.shape[0] > 0 and df.shape[1] > 0:
                df = df.copy()
                df["__file__"] = fname
                df["__default_vendor__"] = default_vendor
                all_dfs.append(df)

    if not all_dfs:
        raise ValueError("未能解析到有效报价数据")

    ALIAS_MAP = {
        "vendor": ["供应商", "供方", "供货商", "厂家", "报价单位", "单位名称", "品牌"],
        "name": ["材料名称", "物料名称", "物资名称", "品名", "名称", "物资品名", "项目名称"],
        "spec": ["规格型号", "规格", "型号", "材质/规格", "材质"],
        "unit": ["单位", "计量单位"],
        "price": ["含税单价", "未税单价", "单价", "报价", "价格", "单价(元)", "含税价", "金额"],
        "tax_type": ["税率", "是否含税", "税种", "发票类别", "税率(%)"],
        "delivery": ["交期(天)", "交期", "交货期", "到货天数", "供货周期", "交货周期", "工期"],
        "payment": ["账期与付款条件", "账期", "付款条件", "结算方式", "信用期", "付款方式"],
        "freight": ["运费承担", "运费", "运输方式", "送货方式", "运杂费", "配送方式"],
        "quality": ["质量", "质保期", "质量等级", "质量评级", "资质"],
    }

    raw_records = []
    for df in all_dfs:
        matched = {}
        for k, aliases in ALIAS_MAP.items():
            found = _find_matching_col(df, aliases, k)
            if found:
                matched[k] = found

        col_price_incl = _find_matching_col(df, ["含税单价", "含税价", "含税报价", "含税价格"])
        col_price_excl = _find_matching_col(df, ["未税单价", "未税价", "未税报价", "未税价格", "不含税单价", "不含税价"])
        col_price_gen = _find_matching_col(df, ["单价", "报价", "价格", "单价(元)", "金额"])
        col_price_type = _find_matching_col(df, ["报价类型", "价格类型", "计价方式", "是否含税", "含税类型", "计费类型"])
        col_tax_rate_col = _find_matching_col(df, ["税率", "税率(%)", "增值税率", "税点"])

        for idx, row in df.iterrows():
            # Vendor
            vendor = str(row.get(matched.get("vendor"), "")).strip() if matched.get("vendor") else ""
            if not vendor or vendor in ("nan", "None", "-"):
                vendor = df["__default_vendor__"].iloc[0]

            # Material name
            name = str(row.get(matched.get("name"), "")).strip() if matched.get("name") else ""
            if not name or name in ("nan", "None"):
                continue

            # Spec
            spec = str(row.get(matched.get("spec"), "")).strip() if matched.get("spec") else ""
            if spec in ("nan", "None"):
                spec = "-"

            # Unit
            unit = str(row.get(matched.get("unit"), "")).strip() if matched.get("unit") else "项"
            if unit in ("nan", "None"):
                unit = "项"

            # Price determination per row
            raw_p_val = None
            is_tax_excl = False

            price_type_val = str(row.get(col_price_type, "")).strip() if col_price_type else ""

            if col_price_incl:
                try:
                    cp = _clean_numeric_series(pd.Series([row[col_price_incl]])).iloc[0]
                    if pd.notna(cp) and float(cp) > 0:
                        raw_p_val = float(cp)
                        is_tax_excl = False
                except Exception:
                    pass

            if raw_p_val is None and col_price_excl:
                try:
                    cp = _clean_numeric_series(pd.Series([row[col_price_excl]])).iloc[0]
                    if pd.notna(cp) and float(cp) > 0:
                        raw_p_val = float(cp)
                        is_tax_excl = True
                except Exception:
                    pass

            if raw_p_val is None and col_price_gen:
                try:
                    cp = _clean_numeric_series(pd.Series([row[col_price_gen]])).iloc[0]
                    if pd.notna(cp) and float(cp) > 0:
                        raw_p_val = float(cp)
                        col_name = str(col_price_gen)
                        tax_val_str = str(row.get(matched.get("tax_type"), "")).strip() if matched.get("tax_type") else ""
                        is_tax_excl = any(k in col_name for k in ("未税", "不含税")) or any(k in tax_val_str for k in ("未税", "不含税")) or any(k in price_type_val for k in ("未税", "不含税", "去税"))
                except Exception:
                    pass

            if raw_p_val is None:
                continue

            # Tax rate
            tax_val_str = ""
            if col_tax_rate_col and pd.notna(row.get(col_tax_rate_col)):
                tax_val_str = str(row.get(col_tax_rate_col)).strip()
            elif matched.get("tax_type") and pd.notna(row.get(matched.get("tax_type"))):
                tax_val_str = str(row.get(matched.get("tax_type"))).strip()

            m_tax = re.search(r"(\d+(?:\.\d+)?)%", tax_val_str)
            item_tax_rate = float(m_tax.group(1)) / 100.0 if m_tax else tax_rate

            if is_tax_excl:
                price_excl = round(raw_p_val, 2)
                price_incl = round(raw_p_val * (1.0 + item_tax_rate), 2)
            else:
                price_incl = round(raw_p_val, 2)
                price_excl = round(raw_p_val / (1.0 + item_tax_rate), 2)

            # Delivery
            lead_time = None
            lead_time_str = ""
            if matched.get("delivery"):
                val_d = str(row[matched["delivery"]]).strip()
                m_days = re.search(r"(\d+)", val_d)
                if m_days:
                    lead_time = int(m_days.group(1))
                    lead_time_str = f"{lead_time} 天"
                elif "现货" in val_d or "即发" in val_d or "次日" in val_d:
                    lead_time = 1
                    lead_time_str = "现货 (1天)"

            # Payment terms
            payment_str = str(row.get(matched.get("payment"), "")).strip() if matched.get("payment") else ""
            payment_days = 0
            if payment_str and payment_str not in ("nan", "None", "-"):
                m_pdays = re.search(r"(\d+)\s*(?:天|日)", payment_str)
                if m_pdays:
                    payment_days = int(m_pdays.group(1))
                elif "月结" in payment_str:
                    payment_days = 30
                elif "现结" in payment_str or "款到发货" in payment_str or "即期" in payment_str:
                    payment_days = 0
                elif "预付" in payment_str:
                    payment_days = -15
            else:
                payment_str = "待核实"

            # Working capital interest benefit / cost
            capital_benefit = round(price_incl * annual_interest_rate * (payment_days / 365.0), 2)

            # Freight
            freight_str = str(row.get(matched.get("freight"), "")).strip() if matched.get("freight") else ""
            freight_cost = 0.0
            freight_is_buyer = False
            if freight_str and freight_str not in ("nan", "None", "-"):
                if any(w in freight_str for w in ("需方", "买方", "自提", "自理", "到付")):
                    freight_is_buyer = True
                    freight_cost = round(price_incl * 0.02, 2)
            else:
                freight_str = "待核实"

            # Net TCO price
            tco_price = round(price_incl - capital_benefit + freight_cost, 2)

            raw_records.append({
                "vendor": vendor,
                "name": name,
                "spec": spec,
                "unit": unit,
                "raw_price": raw_p_val,
                "is_tax_excl": is_tax_excl,
                "tax_rate_val": item_tax_rate,
                "tax_rate_str": f"{int(item_tax_rate * 100)}%",
                "price_excl": price_excl,
                "price_incl": price_incl,
                "lead_time": lead_time,
                "lead_time_str": lead_time_str or "待核实",
                "payment_terms": payment_str,
                "payment_days": payment_days,
                "capital_benefit": capital_benefit,
                "freight": freight_str,
                "freight_cost": freight_cost,
                "tco_price": tco_price,
            })

    if not raw_records:
        raise ValueError("未能提取到有效报价条目")

    # Group by material key (name + spec)
    groups = {}
    for r in raw_records:
        mat_key = f"{r['name']}|{r['spec']}"
        groups.setdefault(mat_key, []).append(r)

    comparison_matrix = []
    verification_items = []
    row_idx = 1

    for mat_key, items in groups.items():
        min_price = min(it["price_incl"] for it in items)
        min_tco = min(it["tco_price"] for it in items)

        for it in items:
            diff_rate = round(((it["price_incl"] - min_price) / min_price) * 100.0, 2) if min_price > 0 else 0.0
            tco_diff = round(it["tco_price"] - min_tco, 2)
            is_lowest = (abs(it["price_incl"] - min_price) < 0.001)

            # Verification screening
            missing_reasons = []
            if it["lead_time"] is None or it["lead_time_str"] == "待核实":
                missing_reasons.append("漏填交期")
                verification_items.append({
                    "material": it["name"],
                    "spec": it["spec"],
                    "vendor": it["vendor"],
                    "issue_type": "漏填交期",
                    "description": f"【{it['vendor']}】未明确标明供货周期或交货天数，存在延误交付与停工待料风险，需向供应商核实锁定期限。",
                })
            if it["freight"] in ("待核实", "待定", "待协商", "未约定", "-") or any(k in str(it["freight"]) for k in ("待协商", "待定", "待核实", "另议", "另计", "未注明", "不含")):
                missing_reasons.append("漏填运费")
                verification_items.append({
                    "material": it["name"],
                    "spec": it["spec"],
                    "vendor": it["vendor"],
                    "issue_type": "漏填运费",
                    "description": f"【{it['vendor']}】未明确运费承担方及到场杂费，可能产生到货隐性加价，需向供方确认是否送货上门包邮。",
                })
            if it["payment_terms"] == "待核实":
                missing_reasons.append("待核实账期")
                verification_items.append({
                    "material": it["name"],
                    "spec": it["spec"],
                    "vendor": it["vendor"],
                    "issue_type": "账期不明",
                    "description": f"【{it['vendor']}】未约定付款账期与结算方式，建议统一对齐月结60天以降低资金占用。",
                })

            verify_str = "、".join(missing_reasons) if missing_reasons else "合规完整"

            item_dict = {
                "id": row_idx,
                "material": it["name"],
                "spec": it["spec"],
                "unit": it["unit"],
                "vendor": it["vendor"],
                "raw_price": it["raw_price"],
                "tax_rate_str": it["tax_rate_str"],
                "price_excl": it["price_excl"],
                "price_incl": it["price_incl"],
                "lead_time": it["lead_time"],
                "lead_time_str": it["lead_time_str"],
                "payment_terms": it["payment_terms"],
                "payment_days": it["payment_days"],
                "capital_benefit": it["capital_benefit"],
                "interest_adj": it["capital_benefit"],
                "freight": it["freight"],
                "freight_cost": it.get("freight_cost", 0.0),
                "freight_adj": it.get("freight_cost", 0.0),
                "tco_price": it["tco_price"],
                "is_lowest": is_lowest,
                "diff_rate": diff_rate,
                "diff_rate_str": f"+{diff_rate:.1f}%" if diff_rate > 0 else "0.0% (最低)",
                "tco_diff": tco_diff,
                "verification_status": verify_str,
                "has_missing": bool(missing_reasons),
            }
            comparison_matrix.append(item_dict)
            row_idx += 1

    # Weighted scoring matrix per vendor
    vendor_records = {}
    for it in comparison_matrix:
        vendor_records.setdefault(it["vendor"], []).append(it)

    score_matrix = []
    for v_name, v_items in vendor_records.items():
        price_scores = []
        delivery_scores = []
        payment_scores = []
        quality_scores = []

        for it in v_items:
            mat_items = [x for x in comparison_matrix if x["material"] == it["material"] and x["spec"] == it["spec"]]
            m_tco = min(x["tco_price"] for x in mat_items)
            pscore = min(100.0, max(0.0, (m_tco / it["tco_price"]) * 100.0)) if it["tco_price"] > 0 else 50.0
            price_scores.append(pscore)

            valid_leads = [x["lead_time"] for x in mat_items if x["lead_time"] is not None and x["lead_time"] > 0]
            m_lead = min(valid_leads) if valid_leads else 7
            if it["lead_time"] and it["lead_time"] > 0:
                dscore = min(100.0, max(30.0, (m_lead / it["lead_time"]) * 100.0))
            else:
                dscore = 50.0
            delivery_scores.append(dscore)

            pdays = it["payment_days"]
            if pdays >= 90:
                pay_score = 100.0
            elif pdays >= 60:
                pay_score = 90.0
            elif pdays >= 30:
                pay_score = 80.0
            elif pdays > 0:
                pay_score = 70.0
            elif pdays == 0:
                pay_score = 60.0
            else:
                pay_score = 40.0
            payment_scores.append(pay_score)

            qscore = 90.0
            if it["has_missing"]:
                qscore -= 15.0
            quality_scores.append(max(30.0, qscore))

        avg_price_score = round(float(np.mean(price_scores)), 2)
        avg_deliv_score = round(float(np.mean(delivery_scores)), 2)
        avg_pay_score = round(float(np.mean(payment_scores)), 2)
        avg_qual_score = round(float(np.mean(quality_scores)), 2)

        total_weighted_score = round(
            avg_price_score * w["price"] +
            avg_deliv_score * w["delivery"] +
            avg_pay_score * w["payment"] +
            avg_qual_score * w["quality"],
            2
        )

        score_matrix.append({
            "vendor": v_name,
            "item_count": len(v_items),
            "price_score": avg_price_score,
            "delivery_score": avg_deliv_score,
            "payment_score": avg_pay_score,
            "quality_score": avg_qual_score,
            "total_score": total_weighted_score,
        })

    # Sort vendors by total score descending
    score_matrix.sort(key=lambda x: x["total_score"], reverse=True)
    for rank_idx, sm in enumerate(score_matrix, 1):
        sm["rank"] = rank_idx
        if rank_idx == 1:
            sm["recommendation"] = "首选授标（建议分配 70% 份额）"
            sm["badge"] = "primary"
        elif rank_idx == 2:
            sm["recommendation"] = "备选/谈判压价（建议分配 30% 份额或二轮竞价）"
            sm["badge"] = "secondary"
        else:
            sm["recommendation"] = "淘汰/备用货源"
            sm["badge"] = "eliminated"

    # Negotiation Points per vendor
    top_vendor = score_matrix[0] if score_matrix else None
    negotiation_points = []
    for sm in score_matrix:
        v_name = sm["vendor"]
        v_items = vendor_records[v_name]
        v_diffs = [x["diff_rate"] for x in v_items if not x["is_lowest"]]
        avg_diff = np.mean(v_diffs) if v_diffs else 0.0

        v_missing = [x for x in verification_items if x["vendor"] == v_name]
        missing_types = list({x["issue_type"] for x in v_missing})

        if sm["rank"] == 1:
            strategy = (
                f"【{v_name}】综合评分居榜首（{sm['total_score']}分），建议作为首选签约对象。"
                f"谈判要点：(1) 锁定当前具有竞争力的含税单价；"
                f"(2) 强化交期违约责任，明确延期按每日0.05%承担违约金；"
                f"(3) 补全合同发票条款，明确开具13%增值税专用发票；"
                f"若存在待核实项（如{('、'.join(missing_types)) if missing_types else '运费'}），要求在合同中明确由供方承担全部运杂费及送货上门。"
            )
        else:
            strategy = (
                f"【{v_name}】综合评分排名第{sm['rank']}（{sm['total_score']}分），含税价格平均偏高 {avg_diff:.1f}%。"
                f"谈判要点：(1) 定点压价：以此轮最低报价作为目标底价，要求针对差价品种下调 {avg_diff:.1f}% 报价；"
                f"(2) 条款对齐：要求其将账期拉长至 60 天以上，并对齐最快供货交期；"
                f"(3) 落实备选保供协议，若首选供应商产能受限时启动二货源按目标价调拨。"
            )

        negotiation_points.append({
            "vendor": v_name,
            "rank": sm["rank"],
            "total_score": sm["total_score"],
            "avg_diff_rate": round(float(avg_diff), 2),
            "strategy": strategy,
        })

    # KPI summary
    min_overall_price = min(x["price_incl"] for x in comparison_matrix)
    all_diffs = [x["diff_rate"] for x in comparison_matrix if x["diff_rate"] > 0]
    avg_diff_rate = round(float(np.mean(all_diffs)), 1) if all_diffs else 0.0
    unverified_count = len(verification_items)
    top_vendor_name = top_vendor["vendor"] if top_vendor else "无"

    kpis = [
        {"label": "最低报价供应商", "value": top_vendor_name, "icon": "🏆", "status": "success"},
        {"label": "平均溢价率", "value": f"+{avg_diff_rate}%", "icon": "📊", "status": "info"},
        {"label": "待核实项", "value": f"{unverified_count} 处", "icon": "⚠️", "status": "warn" if unverified_count > 0 else "success"},
        {"label": "比选材料总数", "value": f"{len(groups)} 项", "icon": "📦", "status": "info"},
    ]

    # Markdown acceptance report
    md_lines = [
        "# 《供应商比选/比价校验表》（确定性 TCO 与加权评估报告）",
        "",
        "### 一、统计口径与权重配置说明",
        f"- **税率基准**：按 **{int(tax_rate*100)}% 增值税** 统一换算含税与未税单价（未税 = 含税 / 1.{int(tax_rate*100)}）。",
        f"- **评分权重配置**：价格 **{int(w['price']*100)}%**、交期 **{int(w['delivery']*100)}%**、账期与付款条件 **{int(w['payment']*100)}%**、质量与风险 **{int(w['quality']*100)}%**。",
        f"- **TCO资金折算模型**：`综合 TCO 单价 = 含税单价 - 账期资金贴息收益 + 运费调整`（年化利率按 {int(annual_interest_rate*100)}% 折算）。",
        "",
        "### 二、核心比选指标看板",
        f"- 🏆 首选推荐供应商：**{top_vendor_name}**（综合得分：{top_vendor['total_score'] if top_vendor else 0} 分）",
        f"- 📊 供应商平均价差率：**+{avg_diff_rate}%**",
        f"- ⚠️ 待核实风险项：**{unverified_count} 处**（漏填交期或运费）",
        "",
        "### 三、比价校验表（横向价格与 TCO 测算明细）",
        "| 序号 | 材料名称 | 规格型号 | 供应商 | 未税单价 | 含税单价 | 税率 | 交期 | 账期条件 | 账期折算资金收益 | 运费承担 | 综合TCO单价 | 差价率 | 核对状态 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ]

    for item in comparison_matrix:
        lowest_tag = "✅ **最低价**" if item["is_lowest"] else f"+{item['diff_rate']}%"
        md_lines.append(
            f"| {item['id']} | {item['material']} | {item['spec']} | **{item['vendor']}** | "
            f"￥{item['price_excl']:,.2f} | ￥{item['price_incl']:,.2f} | {item['tax_rate_str']} | "
            f"{item['lead_time_str']} | {item['payment_terms']} | ￥{item['capital_benefit']:,.2f} | "
            f"{item['freight']} | ￥{item['tco_price']:,.2f} | {lowest_tag} | {item['verification_status']} |"
        )

    md_lines.extend([
        "",
        "### 四、加权得分矩阵与授标推荐结论",
        "| 排名 | 供应商名称 | 价格得分 (40%) | 交期得分 (20%) | 账期得分 (20%) | 质量风险 (20%) | 综合加权得分 | 授标推荐建议 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
    ])
    for sm in score_matrix:
        md_lines.append(
            f"| {sm['rank']} | **{sm['vendor']}** | {sm['price_score']} | {sm['delivery_score']} | "
            f"{sm['payment_score']} | {sm['quality_score']} | **{sm['total_score']}** | {sm['recommendation']} |"
        )

    md_lines.extend([
        "",
        "### 五、待核实项清单（漏填交期/运费）",
    ])
    if verification_items:
        md_lines.append("| 序号 | 材料名称 | 供应商 | 异常项类别 | 风险诊断与澄清要求 |")
        md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
        for v_idx, v_it in enumerate(verification_items, 1):
            md_lines.append(f"| {v_idx} | {v_it['material']} | {v_it['vendor']} | ⚠️ {v_it['issue_type']} | {v_it['description']} |")
    else:
        md_lines.append("✨ 所有供应商报价条款完备，未发现漏填交期或运费项。")

    md_lines.extend([
        "",
        "### 六、分供应商谈判压价要点",
    ])
    for np_item in negotiation_points:
        md_lines.append(f"- **{np_item['vendor']}（第{np_item['rank']}名 / {np_item['total_score']}分）**：{np_item['strategy']}")

    full_md = "\n".join(md_lines)

    return {
        "ok": True,
        "title": "供应商比选/比价校验表",
        "scope_description": f"统一税率基准：{int(tax_rate*100)}% | 评分权重：价格{int(w['price']*100)}%、交期{int(w['delivery']*100)}%、账期{int(w['payment']*100)}%、质量{int(w['quality']*100)}% | TCO=含税单价-账期贴息收益+运费",
        "tax_rate": tax_rate,
        "tax_rate_str": f"{int(tax_rate*100)}%",
        "weights": w,
        "kpi_metrics": kpis,
        "comparison_matrix": comparison_matrix,
        "verification_items": verification_items,
        "unverified_items": verification_items,
        "score_matrix": score_matrix,
        "rankings": score_matrix,
        "negotiation_points": negotiation_points,
        "markdown": full_md,
    }


def generate_price_tco_excel(calc_result: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """生成标准化材料比价与 TCO 成本分析表（.xlsx）"""
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = f"材料比价与TCO成本分析表-{ts}.xlsx"
    out_path = os.path.join(out_dir, out_filename)

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "材料明细比价校验表"
    ws1.views.sheetView[0].showGridLines = True

    # Title
    ws1.merge_cells("A1:P1")
    ws1["A1"] = "采购材料横向比选与 TCO 总成本测算校验表"
    ws1["A1"].font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    ws1["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws1.row_dimensions[1].height = 28

    ws1.merge_cells("A2:P2")
    ws1["A2"] = f"核算时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}  |  {calc_result.get('scope_description', '')}"
    ws1["A2"].font = Font(name="微软雅黑", size=9.5, color="555555")
    ws1["A2"].alignment = Alignment(horizontal="left", vertical="center")
    ws1.row_dimensions[2].height = 20

    headers1 = [
        "序号", "材料名称", "规格型号", "单位", "供应商",
        "未税单价(元)", "含税单价(元)", "税率", "交期", "账期条件",
        "资金贴息收益(元)", "运费承担", "综合TCO单价(元)", "最低价标识", "差价率", "待核实提示"
    ]

    header_fill = PatternFill("solid", fgColor="1F4E79")
    header_font = Font(name="微软雅黑", size=10, bold=True, color="FFFFFF")
    thin_border = Border(
        left=Side(style="thin", color="D1D5DB"),
        right=Side(style="thin", color="D1D5DB"),
        top=Side(style="thin", color="D1D5DB"),
        bottom=Side(style="thin", color="D1D5DB")
    )

    ws1.row_dimensions[3].height = 25
    for c_idx, h in enumerate(headers1, 1):
        c = ws1.cell(row=3, column=c_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border

    lowest_fill = PatternFill("solid", fgColor="E2F0D9")
    warn_fill = PatternFill("solid", fgColor="FFF2CC")
    zebra_fill = PatternFill("solid", fgColor="F9FAFB")

    matrix_data = calc_result.get("comparison_matrix", [])
    for r_idx, row in enumerate(matrix_data, 4):
        ws1.row_dimensions[r_idx].height = 20
        vals = [
            row["id"], row["material"], row["spec"], row["unit"], row["vendor"],
            row["price_excl"], row["price_incl"], row["tax_rate_str"], row["lead_time_str"], row["payment_terms"],
            row["capital_benefit"], row["freight"], row["tco_price"],
            "✅ 最低价" if row["is_lowest"] else "", row["diff_rate_str"], row["verification_status"]
        ]
        for c_idx, val in enumerate(vals, 1):
            cell = ws1.cell(row=r_idx, column=c_idx, value=val)
            cell.font = Font(name="微软雅黑", size=9.5)
            cell.border = thin_border

            if c_idx in (6, 7, 11, 13):
                cell.number_format = "#,##0.00"
                cell.alignment = Alignment(horizontal="right", vertical="center")
            elif c_idx in (1, 8, 9, 14, 15):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            if row["is_lowest"] and c_idx in (7, 13, 14):
                cell.fill = lowest_fill
                cell.font = Font(name="微软雅黑", size=9.5, bold=True, color="276A3C")
            elif row["has_missing"] and c_idx == 16:
                cell.fill = warn_fill
                cell.font = Font(name="微软雅黑", size=9.5, color="B25E00")
            elif (r_idx - 4) % 2 == 1:
                cell.fill = zebra_fill

    for c in range(1, len(headers1) + 1):
        ws1.column_dimensions[get_column_letter(c)].width = 16
    ws1.freeze_panes = "A4"

    # Sheet 2: 授标建议与谈判要点
    ws2 = wb.create_sheet(title="授标建议与谈判要点")
    ws2.views.sheetView[0].showGridLines = True

    ws2.merge_cells("A1:I1")
    ws2["A1"] = "供应商综合加权评分与分供应商谈判要点"
    ws2["A1"].font = Font(name="微软雅黑", size=14, bold=True, color="1F4E79")
    ws2["A1"].alignment = Alignment(horizontal="left", vertical="center")
    ws2.row_dimensions[1].height = 28

    headers2 = ["排名", "供应商名称", "比选条目数", "价格得分 (40%)", "交期得分 (20%)", "账期得分 (20%)", "质量风险 (20%)", "综合加权得分", "授标推荐建议"]
    ws2.row_dimensions[3].height = 25
    for c_idx, h in enumerate(headers2, 1):
        c = ws2.cell(row=3, column=c_idx, value=h)
        c.fill = header_fill
        c.font = header_font
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = thin_border

    score_data = calc_result.get("score_matrix", [])
    last_score_row = 3 + len(score_data)
    for r_idx, sm in enumerate(score_data, 4):
        ws2.row_dimensions[r_idx].height = 22
        vals2 = [
            sm["rank"], sm["vendor"], sm["item_count"],
            sm["price_score"], sm["delivery_score"], sm["payment_score"], sm["quality_score"],
            sm["total_score"], sm["recommendation"]
        ]
        for c_idx, val in enumerate(vals2, 1):
            cell = ws2.cell(row=r_idx, column=c_idx, value=val)
            cell.font = Font(name="微软雅黑", size=9.5)
            cell.border = thin_border
            if c_idx in (1, 3):
                cell.alignment = Alignment(horizontal="center", vertical="center")
            elif c_idx in (4, 5, 6, 7, 8):
                cell.alignment = Alignment(horizontal="right", vertical="center")
                cell.number_format = "#,##0.0"
            else:
                cell.alignment = Alignment(horizontal="left", vertical="center")

            if sm["rank"] == 1:
                cell.fill = lowest_fill
                if c_idx in (2, 8, 9):
                    cell.font = Font(name="微软雅黑", size=9.5, bold=True, color="276A3C")

    # 附：分供应商谈判要点
    nego_start_row = last_score_row + 2
    ws2.cell(row=nego_start_row, column=1, value="分供应商谈判压价要点与策略建议").font = Font(name="微软雅黑", size=12, bold=True, color="1F4E79")
    ws2.row_dimensions[nego_start_row].height = 24

    nego_items = calc_result.get("negotiation_points", [])
    for idx, np_item in enumerate(nego_items, 1):
        cur_row = nego_start_row + idx
        ws2.row_dimensions[cur_row].height = 28
        ws2.merge_cells(start_row=cur_row, start_column=1, end_row=cur_row, end_column=9)
        c_nego = ws2.cell(row=cur_row, column=1, value=f"{idx}. 【{np_item['vendor']}】（排名第{np_item['rank']}，得分{np_item['total_score']}分）：{np_item['strategy']}")
        c_nego.font = Font(name="微软雅黑", size=9.5)
        c_nego.alignment = Alignment(horizontal="left", vertical="center")

    for c in range(1, len(headers2) + 1):
        ws2.column_dimensions[get_column_letter(c)].width = 18
    ws2.column_dimensions["I"].width = 38
    ws2.freeze_panes = "A4"

    wb.save(out_path)
    fsize = os.path.getsize(out_path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"

    return {
        "ok": True,
        "filename": out_filename,
        "path": out_path,
        "filepath": out_path,
        "filesize": fsize_str,
        "filetype": "excel",
        "rows": len(matrix_data),
        "kpi_metrics": calc_result.get("kpi_metrics", []),
        "preview_data": {
            "columns": headers1,
            "rows": [[
                r["id"], r["material"], r["spec"], r["unit"], r["vendor"],
                r["price_excl"], r["price_incl"], r["tax_rate_str"], r["lead_time_str"], r["payment_terms"],
                r["capital_benefit"], r["freight"], r["tco_price"],
                "最低价" if r["is_lowest"] else "", r["diff_rate_str"], r["verification_status"]
            ] for r in matrix_data[:50]],
            "total_rows": len(matrix_data),
            "diff_indices": [i for i, r in enumerate(matrix_data[:50]) if not r["is_lowest"]],
        },
        "url": f"/files/{out_filename}",
    }


def generate_price_tco_ppt(calc_result: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """生成包含原生柱状图的供应商比选与 TCO 比价汇报幻灯片（.pptx）"""
    import pptx
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION

    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = f"供应商比选与TCO比价汇报-{ts}.pptx"
    out_path = os.path.join(out_dir, out_filename)

    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def _add_run_text(p, text, font_size=12, bold=False, color_rgb=None):
        r = p.add_run()
        r.text = str(text)
        r.font.name = "微软雅黑"
        r.font.size = Pt(font_size)
        r.font.bold = bold
        if color_rgb:
            r.font.color.rgb = color_rgb
        return r

    def _add_header(s, title_text, cat_tag="战略采购比选"):
        rect = s.shapes.add_shape(1, Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.8))
        rect.fill.solid()
        rect.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        rect.line.fill.background()

        tb = s.shapes.add_textbox(Inches(1.0), Inches(0.45), Inches(11.333), Inches(0.7))
        p = tb.text_frame.paragraphs[0]
        _add_run_text(p, f"【{cat_tag}】 ", 13, True, RGBColor(0xD9, 0xE1, 0xF2))
        _add_run_text(p, title_text, 18, True, RGBColor(0xFF, 0xFF, 0xFF))

    # Slide 1: Cover
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    bg1.line.fill.background()

    tb1 = s1.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.333), Inches(3.0))
    tf1 = tb1.text_frame
    p1 = tf1.paragraphs[0]
    _add_run_text(p1, "供应商比选与 TCO 比价分析报告", 36, True, RGBColor(0xFF, 0xFF, 0xFF))

    p1_sub = tf1.add_paragraph()
    p1_sub.space_before = Pt(16)
    _add_run_text(p1_sub, "基于确定性 TCO 模型换算、加权得分矩阵与分供应商谈判压价建议", 18, False, RGBColor(0xD9, 0xE1, 0xF2))

    p1_date = tf1.add_paragraph()
    p1_date.space_before = Pt(28)
    _add_run_text(p1_date, f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", 13, False, RGBColor(0xA6, 0xB8, 0xCE))

    # Slide 2: Dashboard KPIs
    s2 = prs.slides.add_slide(blank_layout)
    _add_header(s2, "比选核心指标看板与统计口径说明", "核心指标")

    kpis = calc_result.get("kpi_metrics", [])
    box_w = Inches(2.7)
    box_h = Inches(2.0)
    start_x = Inches(0.8)
    gap = Inches(0.3)
    y_pos = Inches(1.8)

    for i, k in enumerate(kpis[:4]):
        x = start_x + i * (box_w + gap)
        card = s2.shapes.add_shape(1, x, y_pos, box_w, box_h)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(0xF6, 0xF8, 0xFA)
        card.line.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        card.line.width = Pt(1.5)

        tb_k = s2.shapes.add_textbox(x, y_pos + Inches(0.2), box_w, box_h - Inches(0.4))
        tf_k = tb_k.text_frame
        p_k1 = tf_k.paragraphs[0]
        p_k1.alignment = PP_ALIGN.CENTER
        _add_run_text(p_k1, f"{k['icon']} {k['label']}", 15, True, RGBColor(0x1F, 0x4E, 0x79))

        p_k2 = tf_k.add_paragraph()
        p_k2.alignment = PP_ALIGN.CENTER
        p_k2.space_before = Pt(12)
        _add_run_text(p_k2, str(k['value']), 24, True, RGBColor(0x27, 0x6A, 0x3C) if "最低" in k['label'] or "首选" in k['label'] else RGBColor(0x33, 0x33, 0x33))

    # Scope box
    sc_box = s2.shapes.add_shape(1, Inches(0.8), Inches(4.3), Inches(11.733), Inches(2.3))
    sc_box.fill.solid()
    sc_box.fill.fore_color.rgb = RGBColor(0xF8, 0xF9, 0xFA)
    sc_box.line.color.rgb = RGBColor(0xDD, 0xE2, 0xE6)

    tb_sc = s2.shapes.add_textbox(Inches(1.1), Inches(4.5), Inches(11.133), Inches(1.9))
    tf_sc = tb_sc.text_frame
    p_sc = tf_sc.paragraphs[0]
    _add_run_text(p_sc, "📌 确定性测算规则与统计口径说明：", 15, True, RGBColor(0x1F, 0x4E, 0x79))

    bullets_sc = [
        f"1. 税率统一基准：统一采用 {calc_result.get('tax_rate_str', '13%')} 税率换算未税单价与含税单价，杜绝税制差异失真；",
        "2. 资金占用利息折现：按年化6%资金成本计算账期贴息收益，月结60天相较现结可直接节约资金占用利息；",
        "3. 待核实项自动排查：对漏填交货周期、漏约定运杂费承担方的条目自动标记预警，规避停工待料与到场隐性加价风险；",
        "4. 加权评分决策模型：价格(40%) + 交期(20%) + 账期(20%) + 质量与风险(20%) 综合加权输出客观决策矩阵。",
    ]
    for b in bullets_sc:
        p_b = tf_sc.add_paragraph()
        p_b.space_before = Pt(6)
        _add_run_text(p_b, b, 11, False, RGBColor(0x44, 0x44, 0x44))

    # Slide 3: Native Column Chart (柱状图)
    s3 = prs.slides.add_slide(blank_layout)
    _add_header(s3, "主要材料综合 TCO 单价对比（原生 Office 柱状图）", "图表对比")

    matrix_data = calc_result.get("comparison_matrix", [])
    mat_names = []
    seen = set()
    for row in matrix_data:
        m = row["material"]
        if m not in seen and len(mat_names) < 6:
            seen.add(m)
            mat_names.append(m)

    vendors = list({r["vendor"] for r in matrix_data})[:4]

    chart_data = CategoryChartData()
    chart_data.categories = mat_names

    for v in vendors:
        series_vals = []
        for m in mat_names:
            v_match = next((r for r in matrix_data if r["material"] == m and r["vendor"] == v), None)
            series_vals.append(v_match["tco_price"] if v_match else 0.0)
        chart_data.add_series(v, tuple(series_vals))

    x, y, cx, cy = Inches(0.8), Inches(1.5), Inches(11.733), Inches(5.2)
    chart = s3.shapes.add_chart(
        XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, cx, cy, chart_data
    ).chart

    chart.has_legend = True
    chart.legend.position = XL_LEGEND_POSITION.TOP
    chart.legend.include_in_layout = False
    chart.value_axis.has_major_gridlines = True
    chart.has_title = True
    chart.chart_title.text_frame.text = "主要物资综合 TCO 单价对比 (元)"

    # Slide 4: Score Matrix & Negotiation Points
    s4 = prs.slides.add_slide(blank_layout)
    _add_header(s4, "供应商综合评分矩阵与分供应商谈判要点", "授标建议")

    score_data = calc_result.get("score_matrix", [])
    if score_data:
        rows_cnt = len(score_data) + 1
        tbl_s = s4.shapes.add_table(rows_cnt, 5, Inches(0.8), Inches(1.5), Inches(11.733), Inches(2.2))
        tbl = tbl_s.table
        tbl.columns[0].width = Inches(1.2)
        tbl.columns[1].width = Inches(2.5)
        tbl.columns[2].width = Inches(2.2)
        tbl.columns[3].width = Inches(2.2)
        tbl.columns[4].width = Inches(3.633)

        headers = ["排名", "供应商名称", "价格得分(40%)", "综合得分", "授标推荐结论"]
        for c_idx, h in enumerate(headers):
            cell = tbl.cell(0, c_idx)
            cell.text = h
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.name = "微软雅黑"
                    r.font.size = Pt(11)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        for r_idx, sm in enumerate(score_data, 1):
            tbl.cell(r_idx, 0).text = str(sm["rank"])
            tbl.cell(r_idx, 1).text = str(sm["vendor"])
            tbl.cell(r_idx, 2).text = f"{sm['price_score']:.1f} 分"
            tbl.cell(r_idx, 3).text = f"{sm['total_score']:.1f} 分"
            tbl.cell(r_idx, 4).text = str(sm["recommendation"])

            for c_idx in range(5):
                c_cell = tbl.cell(r_idx, c_idx)
                if sm["rank"] == 1:
                    c_cell.fill.solid()
                    c_cell.fill.fore_color.rgb = RGBColor(0xEA, 0xFA, 0xEA)
                elif r_idx % 2 == 0:
                    c_cell.fill.solid()
                    c_cell.fill.fore_color.rgb = RGBColor(0xF9, 0xFA, 0xFB)
                for p in c_cell.text_frame.paragraphs:
                    if c_idx in (0, 2, 3):
                        p.alignment = PP_ALIGN.CENTER
                    for r in p.runs:
                        r.font.name = "微软雅黑"
                        r.font.size = Pt(10)
                        if sm["rank"] == 1:
                            r.font.bold = True
                            r.font.color.rgb = RGBColor(0x27, 0x6A, 0x3C)

    # Negotiation box
    neg_box = s4.shapes.add_shape(1, Inches(0.8), Inches(4.0), Inches(11.733), Inches(2.8))
    neg_box.fill.solid()
    neg_box.fill.fore_color.rgb = RGBColor(0xF8, 0xF9, 0xFA)
    neg_box.line.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    neg_box.line.width = Pt(1)

    tb_neg = s4.shapes.add_textbox(Inches(1.1), Inches(4.1), Inches(11.133), Inches(2.6))
    tf_neg = tb_neg.text_frame
    p_n1 = tf_neg.paragraphs[0]
    _add_run_text(p_n1, "🎯 分供应商谈判压价执行策略：", 14, True, RGBColor(0x1F, 0x4E, 0x79))

    for np_item in calc_result.get("negotiation_points", []):
        p_np = tf_neg.add_paragraph()
        p_np.space_before = Pt(6)
        _add_run_text(p_np, np_item["strategy"], 10.5, False, RGBColor(0x33, 0x33, 0x33))

    prs.save(out_path)
    fsize = os.path.getsize(out_path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
    return {
        "ok": True,
        "filename": out_filename,
        "path": out_path,
        "filepath": out_path,
        "filesize": fsize_str,
        "filetype": "ppt",
        "kpi_metrics": calc_result.get("kpi_metrics", []),
        "preview_data": {
            "type": "ppt",
            "title": "供应商比选与TCO比价汇报",
            "slides": [
                {"title": "比选核心指标看板与统计口径说明", "bullets": [f"{k['label']}：{k['value']}" for k in kpis]},
                {"title": "主要材料综合 TCO 单价对比（原生 Office 柱状图）", "bullets": ["柱状图支持原生编辑与数据透视"]},
            ]
        },
        "url": f"/files/{out_filename}",
    }


def generate_price_comparison_excel(files: List[Dict[str, Any]], out_dir: str) -> Dict[str, Any]:
    """材料价格对比自动生成标准化比价矩阵与 TCO 分析表（.xlsx，兼容旧版调用并自动调用最新测算引擎）"""
    calc_res = calculate_supplier_price_comparison(files)
    return generate_price_tco_excel(calc_res, out_dir)


def get_data_preview_artifact(files: List[Dict[str, Any]], out_dir: str = None) -> Optional[Dict[str, Any]]:
    """为「表格分析」模式提取当前表格的结构化成果舱预览"""
    table_files = [f for f in files if os.path.splitext(f.get("name", ""))[1].lower() in (".xlsx", ".xlsm", ".xls", ".csv")]
    if not table_files:
        return None

    target_f = table_files[0]
    path = target_f.get("path")
    if not path or not os.path.exists(path):
        return None

    dfs = read_dataframes_from_file(path)
    if not dfs:
        return None

    sname, df = next(iter(dfs.items()))
    fsize = os.path.getsize(path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"

    return {
        "filename": target_f.get("name", os.path.basename(path)),
        "path": path,
        "filepath": path,
        "filesize": fsize_str,
        "filetype": "excel" if path.lower().endswith((".xlsx", ".xls", ".xlsm")) else "csv",
        "rows": len(df),
        "kpi_metrics": [
            {"label": "数据总行数", "value": f"{len(df):,} 行", "icon": "📋"},
            {"label": "字段列数", "value": f"{len(df.columns)} 列", "icon": "🔢"},
            {"label": "当前工作表", "value": str(sname)[:14], "icon": "📑"},
            {"label": "预计算状态", "value": "核验就绪", "icon": "✓"},
        ],
        "preview_data": {
            "columns": [str(c) for c in df.columns],
            "rows": df.head(50).fillna("").values.tolist(),
            "total_rows": len(df),
            "diff_indices": [],
        },
    }


class RiskFatalCode(str):
    def __eq__(self, other):
        return other in ("fatal", "red") or super().__eq__(other)

    def __hash__(self):
        return hash("fatal")


CONTRACT_REVIEW_RULES = [
    {
        "id": "payment",
        "category": "付款节点与账期",
        "name": "付款节点与账期",
        "keywords": ["付款", "预付", "预付款", "进度款", "到货款", "质保金", "结算", "发票", "账期", "背靠背", "支付"],
        "fatal_patterns": [
            (r"(?:收到|待).*?(?:款项|回款|工程款|业主|上游|第三方).*?(?:再行|再|方可|才).*?(?:支付|结算)",
             "存在「背靠背付款」陷阱：付款前提绑定第三方或业主回款，将业主支付风险转嫁给本方，极易引发资金链断裂及催款被动。"),
            (r"(?:预付|预付款)\s*(?:比例|金额|款项)?\s*(?:超过|达到|为|：|:)?\s*([5-9][0-9]%|100%)",
             "预付款比例过高（超过50%）：在未见货前支付过大比例资金，且未约定见索即付银行保函，资金敞口风险极大。"),
            (r"(?:概不退|一经支付.*?不予退还|不退还预付款|定金不退)",
             "单方免除退款责任陷阱：即便供方严重违约亦不予退还已付款项，严重侵犯买方法定解除与追偿权。"),
        ],
        "flaw_patterns": [
            (r"(?:支付|支付.*?进度款)(?!.*?(?:验收合格|初验|终验|签收单))",
             "付款节点未明确以双方书面签署的验收合格报告为前提，存在标的物瑕疵仍被迫付款的商务风险。"),
            (r"发票(?!.*?(?:增值税专用发票|专票|13%|9%))",
             "未明确约定开具增值税专用发票种类及法定税率（如13%），缺乏税制变动价税分离联动调整机制。"),
            (r"(?:质保金|保证金)(?!.*?(?:工作日内|天内|退还期限|无息退还))",
             "质保金退还时限与逾期利息约定不明确，未写明质保期满后的具体清算返还天数。"),
        ],
        "compliance_patterns": [
            (r"(?:验收合格|验收报告|验收单).*?(?:支付|付清)",
             "明确以书面验收合格报告作为进度款/验收款支付的前置条件，履约控制严密。"),
            (r"(?:增值税专用发票|税率\s*13%|税率\s*9%)",
             "发票类型明确为增值税专用发票，税率约定清晰规范。"),
        ],
        "standard_clause": (
            "【标准修改条款】买方按如下节点分期支付货款：(1) 合同签订并收到供方等额预付款保函后3个工作日内支付20%预付款；"
            "(2) 货物运抵指定现场且双方共同签署《初步验收合格单》并收到等额13%增值税专用发票后支付50%；"
            "(3) 设备安装调试完毕并签署《最终竣工验收合格单》后支付25%；"
            "(4) 剩余5%作为质量保证金，在质保期（12个月）届满且无遗留质量争议后15个工作日内无息付清。"
        ),
        "missing_warning": "合同未约定增值税专用发票开具时限或未明确质保金退还具体时限，易产生结算争议。",
        "missing_addition": "【建议补充条款】供方应在买方支付每笔款项前5个工作日内开具符合国家税法规定的13%增值税专用发票。质保金（合同额5%）在质保期满1年且无质量异议后15个工作日内由买方无息退还。"
    },
    {
        "id": "penalty",
        "category": "延期交货违约金对等性",
        "name": "延期交货违约金对等性",
        "keywords": ["延期", "迟延", "逾期", "违约金", "滞纳金", "违约责任", "解约"],
        "fatal_patterns": [
            (r"(?:每日|每逾期|按日|每迟延)[^\n。；;，,]{0,15}(?:千分之[三四五六七八九十]|百分之[一二三四五]|(?<!\.)(?<![0-9])[1-9]%|[0-9]\.[3-9]%)",
             "违约金比例极端偏高（日超3‰）：日万分之五以上或日千分之几等过高滞纳金远超法定支持标准，买方承担畸高违约成本。"),
            (r"(?:单方解除.*?(?:不承担|免于承担|无需承担).*?(?:责任|赔偿)|单方随时解除)",
             "单方不可撤销免责解约权陷阱：赋予供方单方任意解约特权且免除一切违约赔偿责任，严重破坏合同法律约束力。"),
            (r"(?:甲方逾期.*?千分之.*?乙方.*?万分之|乙方延期.*?免责)",
             "双方违约责任严重不对等：对买方逾期付款设置惩罚性高额滞纳金，而对供方延期交货轻描淡写甚至免责。"),
        ],
        "flaw_patterns": [
            (r"(?:违约金|滞纳金)(?!.*?(?:上限|封顶|最高不超过|总额不超过))",
             "违约金计算未设定封顶上限（行业通用上限为合同总额的5%~10%），违约责任存在无限扩大隐患。"),
            (r"逾期交货(?!.*?(?:解除合同|单方解除|退货))",
             "未约定严重逾期交货（如超15日）时买方享有的合同解除权与退货索赔机制。"),
        ],
        "compliance_patterns": [
            (r"(?:双方|任何一方).*?(?:违约金|责任).*?(?:对等|相同|万分之五|0\.05%)",
             "违约责任遵循对等公平原则，违约金计算基准一致。"),
            (r"(?:违约金|赔偿).*?(?:上限|总额不超过.*?[5-9]%|10%)",
             "违约金总额明确设定了5%~10%的合理封顶上限。"),
        ],
        "standard_clause": (
            "【标准修改条款】双方违约责任严格遵循对等原则：供方逾期交货的，每逾期一日应按逾期交货总额的万分之五（0.05%）向买方支付违约金；"
            "逾期交货超过15日的，买方有权书面通知解除合同，供方应在3日内退还买方已付全部款项，并按合同总额的10%向买方支付惩罚性违约金。"
            "买方逾期付款的，按同期逾期应付款额每日万分之五承担逾期利息。任何一方违约金总额累计不超过合同总价款的5%。"
        ),
        "missing_warning": "合同完全缺少严重延期交货（超15天）时买方单方解约权及退还预付款并赔偿损失的惩治条款。",
        "missing_addition": "【建议补充条款】供方逾期交货超过15个工作日的，买方有权单方书面解除合同，供方须在接单后3日内退还全部款项，并承担由此产生的替代采购差价及停工窝工损失。"
    },
    {
        "id": "quality",
        "category": "质量验收标准与异议期",
        "name": "质量验收标准与异议期",
        "keywords": ["质量", "验收", "检验", "异议期", "质保期", "抽检", "规格", "标准", "缺陷", "不合格"],
        "fatal_patterns": [
            (r"(?:检验期|异议期|验收期).*?([1-3][日天]|24小时|48小时|72小时).*?(?:视为|视同).*?(?:合格|无异议)|未在.*?([1-3][日天]|48小时).*?视为合格",
             "验收异议期过短陷阱（少于72小时或3日即默认合格）：工业品及大宗建材必须经过现场复验或安装试车，超短异议期将剥夺买方对内在质量缺陷与隐蔽瑕疵的追偿权。"),
            (r"(?:放弃|排除).*?(?:质量异议|隐蔽瑕疵|追偿|索赔)",
             "非法排除隐蔽瑕疵追偿权：强行约定买方在初验后即放弃所有质量异议索赔权利。"),
        ],
        "flaw_patterns": [
            (r"质量.*?(?:合格|符合要求)(?!.*?(?:国家标准|GB|行业标准|技术协议|图纸))",
             "质量验收标准未明确具体国家标准编号（如GB/T）、行业规范或双方确认的技术协议版本，易因标准争议扯皮。"),
            (r"(?:复验|检验)(?!.*?(?:费用由.*?承担|责任方承担))",
             "未明确复检验收不合格时的第三方检测检验费用承担主体（应由供方承担）。"),
        ],
        "compliance_patterns": [
            (r"(?:国家标准|GB/T|行业标准|技术协议).*?(?:验收|检验)",
             "明确引用国家标准（GB/T）及具体技术规范作为法定验收依据。"),
            (r"(?:隐蔽瑕疵|质保期).*?(?:提出异议|负责保修|调换)",
             "清晰区分外观验收与内在隐蔽瑕疵，在质保期内持续享有质量担保追偿权。"),
        ],
        "standard_clause": (
            "【标准修改条款】标的物质量须严格符合国家标准（GB/T相关技术规范）及附件《技术协议书》要求。"
            "买方在货物送达指定地点后15个工作日内完成外观包装及数量初步验收；"
            "内在质量、性能及隐蔽缺陷以安装调试及运行检验为准，买方在12个月质量保证期内均享有提出书面质量异议并索赔的权利。"
            "供方在接到书面异议后应于24小时内响应、48小时内派员到场处理，免费负责返工、修理或调换，并赔偿买方因此遭受的直接与连带损失。"
        ),
        "missing_warning": "合同缺少关于内在隐蔽瑕疵的认定机制及不合格品退换货时效与响应责任约定。",
        "missing_addition": "【建议补充条款】标的物在12个月质保期内发生任何性能缺陷或内在质量问题的，供方须在收到买方通知后48小时内到场免费包修、包换；无法修复的买方有权退货并全额追索货款及损失。"
    },
    {
        "id": "ip",
        "category": "知识产权归属",
        "name": "知识产权归属",
        "keywords": ["知识产权", "专利", "著作权", "商标", "技术图纸", "版权", "侵权", "商业秘密", "技术成果"],
        "fatal_patterns": [
            (r"(?:买方|甲方).*?(?:知识产权|技术成果|图纸).*?(?:归乙方|归供方|无偿转让)",
             "固有知识产权失权漏洞：错误将买方提供的原始技术资料或合作定制开发成果之知识产权约定归供方所有。"),
            (r"(?:供方|乙方).*?(?:不承担.*?侵权|免于承担.*?侵权|免责)",
             "第三方知识产权侵权免责陷阱：供方交付的标的物若涉嫌侵犯第三方专利/版权，供方试图免除自身赔偿责任。"),
        ],
        "flaw_patterns": [
            (r"(?:知识产权|专利)(?!.*?(?:诉讼费|律师费|全额赔偿|应诉))",
             "未明确约定供方发生知识产权侵权争议时的独立应诉义务及诉讼费、律师费承担条款。"),
        ],
        "compliance_patterns": [
            (r"(?:图纸|成果|资料).*?(?:归买方|归甲方所有)",
             "明确买方提供的图纸、技术数据及定制开发成果知识产权独家归属于买方。"),
            (r"(?:保证.*?不侵犯.*?知识产权|侵犯第三方.*?承担.*?赔偿)",
             "供方作出了完备的第三方知识产权侵权担保（第三人权利瑕疵担保）。"),
        ],
        "standard_clause": (
            "【标准修改条款】合同履行过程中买方提供的一切技术资料、图纸及双方合作衍生的定制技术成果，其知识产权均独家归买方所有。"
            "供方明确保证其交付的产品、软件、设计及技术资料不侵犯任何第三方的专利权、商标权、著作权或商业秘密。"
            "如买方因使用供方标的物被第三方指控侵权，供方应独立出面应诉并承担全部诉讼费、保全费、律师费及生效判决或和解款项，并全额赔偿买方因此遭受的全部经济损失。"
        ),
        "missing_warning": "合同完全缺少知识产权归属及第三方侵权抗辩赔偿（第三人权利瑕疵担保）条款，面临连带侵权诉讼风险。",
        "missing_addition": "【建议补充条款】供方保证交付标的物不侵犯任何第三方知识产权；如因此引发纠纷，由供方独立承担全部应诉及赔偿责任，买方不承担任何连带费用。"
    },
    {
        "id": "confidentiality",
        "category": "保密义务",
        "name": "保密义务",
        "keywords": ["保密", "商业秘密", "保密期", "泄密", "披露", "保密协议", "秘密信息"],
        "fatal_patterns": [
            (r"(?:买方|甲方).*?(?:保密).*?(?:供方|乙方).*?(?:无需保密|除外|不负)",
             "单方保密不平等条款：仅单向约束买方的保密义务，供方对买方的采购底价、项目信息却不负保密责任。"),
        ],
        "flaw_patterns": [
            (r"保密期限.*?(?:至合同终止|至本合同期满|至合同解除)",
             "保密期限过短瑕疵：将保密义务截止于合同终止日，合同期满后技术与价格信息即可能遭泄露。商业秘密应自获知之日起至少持续有效3-5年或永久有效。"),
            (r"保密(?!.*?(?:违约金|赔偿损失|20%))",
             "未约定违反保密义务的具体惩罚性违约金及损失赔偿量化标准。"),
        ],
        "compliance_patterns": [
            (r"(?:双方|任何一方).*?(?:严格保密|保密义务).*?(?:不因合同终止而失效|持续\s*[3-5]\s*年)",
             "双向对等保密，且明确保密义务在合同解除或终止后依然长期有效。"),
        ],
        "standard_clause": (
            "【标准修改条款】双方对在洽谈、签订及履行本合同过程中知悉的对方商业秘密、采购价格、设计图纸及经营信息负有严格保密义务。"
            "未经对方事先书面同意，任何一方不得向任何第三方披露、许可或用于本合同以外之目的。"
            "该保密义务具有独立法律效力，不因本合同的解除、终止、撤销而失效，持续有效直至该信息进入公众所知领域之日止。"
            "违约泄露方应向守约方支付合同总额20%的惩罚性违约金，并赔偿全部损失。"
        ),
        "missing_warning": "合同未约定任何商业秘密与价格图纸保密条款，核心供应链商务信息存在外泄风险。",
        "missing_addition": "【建议补充条款】双方应对本合同商业价格、技术图纸及相关数据严格保密，该保密义务在合同终止后3年内持续有效。违约泄密方应支付合同总额20%的违约金。"
    },
    {
        "id": "dispute",
        "category": "争议解决与管辖法院",
        "name": "争议解决与管辖法院",
        "keywords": ["争议", "诉讼", "仲裁", "管辖", "法院", "仲裁委", "协商不成", "起诉"],
        "fatal_patterns": [
            (r"(?:供方|乙方|卖方|供货方).*?(?:所在地|住所地|注册地).*?(?:基层人民法院|人民法院|法院|仲裁)",
             "不利管辖地陷阱（约定供方所在地/住所地法院管辖）：若供方在外地或偏远省份，将导致买方在维权诉讼时面临巨大的异地差旅成本、诉讼阻力及地方保护主义壁垒。"),
            (r"(?:排除|不得).*?(?:买方|甲方).*?(?:诉讼|起诉|仲裁)",
             "单方剥夺买方合法司法救济诉讼权利。"),
        ],
        "flaw_patterns": [
            (r"(?:可向.*?法院提起诉讼.*?也可向.*?仲裁|诉讼或仲裁)",
             "管辖机构约定冲突瑕疵：既约定法院诉讼又约定仲裁委员会，根据《民事诉讼法》与《仲裁法》该约定无效，将导致管辖权异议争议延误维权时效。"),
            (r"(?:向当地法院|有关部门|所在地法院)(?!.*?(?:原告|买方|签订地))",
             "管辖法院约定不明确：仅写「当地法院」，司法实践中极易因管辖地约定不明被认定为无约定而按法定管辖。"),
        ],
        "compliance_patterns": [
            (r"(?:买方所在地|甲方所在地|原告所在地|合同签订地).*?(?:人民法院|仲裁委员会)",
             "明确由买方所在地（或原告所在地、合同签订地）法院管辖，诉讼维权便利。"),
        ],
        "standard_clause": (
            "【标准修改条款】因本合同的签订、履行、解释或与本合同有关的任何争议，双方应首先友好协商解决；"
            "协商不成的，任何一方均有权向买方所在地（即合同履行地）有管辖权的人民法院提起诉讼。"
            "在争议协商或诉讼审理期间，除争议事项外，双方应继续履行本合同其他各项条款。"
        ),
        "missing_warning": "合同完全缺少争议解决与司法管辖法院约定条款，发生违约争议时管辖权不明。",
        "missing_addition": "【建议补充条款】因本合同引起的争议，协商不成的，应向买方所在地人民法院提起诉讼，败诉方承担胜诉方支出的全部诉讼费、保全费及律师费。"
    },
]


def analyze_contract_full(
    text: str,
    custom_rules: Optional[List[Dict[str, Any]]] = None,
    enable_builtin: bool = True,
    enabled_builtin_indexes: Optional[List[int]] = None
) -> Dict[str, Any]:
    """合规性审查与风控排查引擎：
    1) 支持开关系统内置 6 大合规审查库，及逐条自定义审查标准；
    2) 强弱视觉对比呈现：重点不合规/偏离项高亮置顶，完全符合项紧凑弱化；
    3) 彻底去除红绿灯 Emoji，支持导出标准 Word/PPT 报告。
    """
    if not text or len(text.strip()) < 10:
        raise ValueError("请提供包含有效文本的合同文件或内容")

    clean_text = text.strip()
    sentences = re.split(r"[。\n；;]", clean_text)
    sentences = [s.strip() for s in sentences if len(s.strip()) >= 4]

    paragraphs = [p.strip() for p in clean_text.splitlines() if len(p.strip()) >= 4]

    fatal_items = []
    flaw_items = []
    missing_items = []
    compliant_items = []
    comparison_table = []
    missing_list = []

    # 1. 内置标准审查
    if enable_builtin:
        active_rules = CONTRACT_REVIEW_RULES
        if enabled_builtin_indexes is not None:
            active_rules = [CONTRACT_REVIEW_RULES[i] for i in enabled_builtin_indexes if 0 <= i < len(CONTRACT_REVIEW_RULES)]

        for rule in active_rules:
            cat = rule["category"]
            keywords = rule["keywords"]

            # Check clause presence in contract
            cat_paragraphs = [p for p in paragraphs if any(kw in p for kw in keywords)]
            cat_sentences = [s for s in sentences if any(kw in s for kw in keywords)]
            cat_text = "\n".join(cat_paragraphs) if cat_paragraphs else "\n".join(cat_sentences)

            if not cat_text:
                missing_item = {
                    "category": cat,
                    "missing_issue": rule["missing_warning"],
                    "recommended_addition": rule["missing_addition"]
                }
                missing_items.append(missing_item)
                missing_list.append(missing_item)
                continue

            cat_has_fatal = False
            cat_has_flaw = False
            cat_has_comp = False

            # 1. 重点不合规（致命风险）
            for pat, reason in rule["fatal_patterns"]:
                if re.search(pat, cat_text, re.IGNORECASE):
                    matched_s = ""
                    for s in cat_sentences:
                        if re.search(pat, s, re.IGNORECASE):
                            matched_s = s
                            break
                    if not matched_s:
                        m = re.search(pat, cat_text, re.IGNORECASE)
                        matched_s = m.group(0) if m else cat_text[:80]
                    item = {
                        "category": cat,
                        "quote": matched_s[:120],
                        "risk_level": "重点不合规",
                        "risk_level_code": RiskFatalCode("fatal"),
                        "risk_reason": reason,
                        "standard_clause": rule["standard_clause"],
                    }
                    fatal_items.append(item)
                    comparison_table.append(item)
                    cat_has_fatal = True
                    break

            # 2. 完全符合项
            if not cat_has_fatal:
                for pat, reason in rule["compliance_patterns"]:
                    if re.search(pat, cat_text, re.IGNORECASE):
                        matched_s = ""
                        for s in cat_sentences:
                            if re.search(pat, s, re.IGNORECASE):
                                matched_s = s
                                break
                        if not matched_s:
                            m = re.search(pat, cat_text, re.IGNORECASE)
                            matched_s = m.group(0) if m else cat_text[:80]
                        item = {
                            "category": cat,
                            "quote": matched_s[:120],
                            "risk_level": "完全符合",
                            "risk_level_code": "compliance",
                            "risk_reason": reason,
                            "standard_clause": "（该项符合企业风控规范，建议保持现有严密表述）",
                        }
                        compliant_items.append(item)
                        comparison_table.append(item)
                        cat_has_comp = True
                        break

            # 3. 偏离项（商务瑕疵）
            if not cat_has_fatal and not cat_has_comp:
                for pat, reason in rule["flaw_patterns"]:
                    if re.search(pat, cat_text, re.IGNORECASE):
                        matched_s = ""
                        for s in cat_sentences:
                            if re.search(pat, s, re.IGNORECASE):
                                matched_s = s
                                break
                        if not matched_s:
                            m = re.search(pat, cat_text, re.IGNORECASE)
                            matched_s = m.group(0) if m else cat_text[:80]
                        item = {
                            "category": cat,
                            "quote": matched_s[:120],
                            "risk_level": "偏离项",
                            "risk_level_code": "flaw",
                            "risk_reason": reason,
                            "standard_clause": rule["standard_clause"],
                        }
                        flaw_items.append(item)
                        comparison_table.append(item)
                        cat_has_flaw = True
                        break

            # 4. Present but missing key safeguards
            if not cat_has_fatal and not cat_has_flaw and not cat_has_comp:
                missing_item = {
                    "category": cat,
                    "missing_issue": rule["missing_warning"],
                    "recommended_addition": rule["missing_addition"]
                }
                missing_items.append(missing_item)
                missing_list.append(missing_item)

    # 2. 逐条自定义合规审查标准
    if custom_rules:
        for cr in custom_rules:
            if not isinstance(cr, dict):
                continue
            c_name = str(cr.get("name") or cr.get("category") or "").strip()
            c_req = str(cr.get("requirement") or cr.get("desc") or cr.get("standard") or "").strip()
            if not c_name and not c_req:
                continue
            c_name = c_name or "自定义标准"
            c_req_clean = c_req or c_name

            # 提取中英文关键词、缩写及专业词汇
            kw_candidates = set()
            std_tokens = re.findall(r"[A-Za-z0-9\-\+\./]{2,}", c_name + " " + c_req_clean)
            for t in std_tokens:
                kw_candidates.add(t)

            split_words = [w.strip() for w in re.split(r"[\s,，、;；：:()（）《》\"\'“”‘’]+", c_name + " " + c_req_clean) if len(w.strip()) >= 2]
            for w in split_words:
                kw_candidates.add(w)
                if len(w) >= 4 and not re.match(r"^[A-Za-z0-9\-]+$", w):
                    for sub_w in ("供应商", "准入", "资质", "认证", "体系", "账期", "付款", "发票", "专票", "违约", "质量", "检验", "验收", "质保", "保密", "争议", "管辖", "寻源", "报销", "招投标"):
                        if sub_w in w:
                            kw_candidates.add(sub_w)

            kw_list = [k for k in kw_candidates if len(k) >= 2]

            matched_paras = [p for p in paragraphs if any(k in p for k in kw_list)]
            matched_sents = [s for s in sentences if any(k in s for k in kw_list)]
            c_text = "\n".join(matched_paras) if matched_paras else "\n".join(matched_sents)

            if not c_text:
                missing_item = {
                    "category": c_name,
                    "missing_issue": f"未在审查文件中发现关于【{c_name}（{c_req_clean}）】的相关凭证或约定条款",
                    "recommended_addition": f"建议补充明确：{c_req_clean}"
                }
                missing_items.append(missing_item)
                missing_list.append(missing_item)
                continue

            matched_quote = (matched_sents[0] if matched_sents else c_text)[:120]

            # 1. 排查明确不合规/否定陷阱词
            has_neg = bool(re.search(r"(不具备|未能|未提供|无法提供|不提供|拒绝|免除|不承担|无资质|无认证|缺失|逾期|超期|严重滞后|不符|不满足|违背|违规|取消|不合格|暂停|未通过|瑕疵|缺陷|失权)", c_text))

            # 2. 排查必要认证/标准代号（如 ISO9001, CE 等）是否缺失
            missing_std_token = None
            for token in std_tokens:
                if not token.isdigit() and len(token) >= 3:
                    if token.lower() not in c_text.lower() and token.lower() not in clean_text.lower():
                        missing_std_token = token
                        break

            # 3. 排查数值约束（例如：账期不得短于 60 天 / 违约金不得超过 5%）
            num_violated = False
            num_reason = ""
            m_min = re.search(r"(?:不得短于|不得少于|不短于|不少于|不低于|不得低于|至少)\s*(\d+)\s*(?:天|日|月)?", c_req_clean)
            if m_min:
                min_val = float(m_min.group(1))
                m_found = re.findall(r"(\d+)\s*(?:天|日)", c_text)
                for fv in m_found:
                    if float(fv) < min_val:
                        num_violated = True
                        num_reason = f"约定周期（{fv}天）短于合规标准要求（不得短于 {int(min_val)}天）"
                        break

            m_max = re.search(r"(?:不得高于|不得超过|不超过|最高不超过)\s*(\d+(?:\.\d+)?)\s*%", c_req_clean)
            if m_max:
                max_val = float(m_max.group(1))
                m_found_p = re.findall(r"(\d+(?:\.\d+)?)\s*%", c_text)
                for fp in m_found_p:
                    if float(fp) > max_val:
                        num_violated = True
                        num_reason = f"约定比例（{fp}%）超过合规上限（不得超过 {max_val}%）"
                        break

            if has_neg or missing_std_token or num_violated:
                if has_neg:
                    reason = f"条文存在明确不合规表述，未满足标准要求：{c_req_clean}"
                elif missing_std_token:
                    reason = f"条文未包含必要认证或标准资质【{missing_std_token}】，未达到【{c_req_clean}】之合规基准"
                else:
                    reason = f"条文数值偏离合规要求：{num_reason}"

                item = {
                    "category": c_name,
                    "quote": matched_quote,
                    "risk_level": "重点不合规",
                    "risk_level_code": RiskFatalCode("fatal"),
                    "risk_reason": reason,
                    "standard_clause": f"应修正为：严格满足【{c_req_clean}】之合规要求。",
                }
                fatal_items.append(item)
                comparison_table.append(item)
            else:
                req_core_words = [w for w in split_words if len(w) >= 2 and w not in c_name]
                if req_core_words and not any(rw in c_text for rw in req_core_words):
                    item = {
                        "category": c_name,
                        "quote": matched_quote,
                        "risk_level": "偏离项",
                        "risk_level_code": "flaw",
                        "risk_reason": f"条文提及【{c_name}】，但未明确落实【{c_req_clean}】之具体要求细节",
                        "standard_clause": f"建议补充明确条款：严格按照【{c_req_clean}】规范执行。",
                    }
                    flaw_items.append(item)
                    comparison_table.append(item)
                else:
                    item = {
                        "category": c_name,
                        "quote": matched_quote,
                        "risk_level": "完全符合",
                        "risk_level_code": "compliance",
                        "risk_reason": f"经核验，条文符合【{c_req_clean}】要求",
                        "standard_clause": "（该项符合自定义合规要求，建议保持现有效力）",
                    }
                    compliant_items.append(item)
                    comparison_table.append(item)

    fatal_count = len(fatal_items)
    flaw_count = len(flaw_items)
    missing_count = len(missing_items)
    compliant_count = len(compliant_items)

    if fatal_count >= 2:
        rating = "高风险·建议重签或全盘重修订"
    elif fatal_count == 1 or flaw_count >= 2:
        rating = "中风险·建议发起实质商务谈判修订"
    else:
        rating = "低风险·条款相对完备合规"

    kpis = [
        {"icon": "", "label": "重点不合规", "value": f"{fatal_count} 项", "status": "danger" if fatal_count > 0 else "success", "alert": fatal_count > 0},
        {"icon": "", "label": "偏离项", "value": f"{flaw_count} 项", "status": "warn" if flaw_count > 0 else "success", "alert": flaw_count > 0},
        {"icon": "", "label": "待补充项", "value": f"{missing_count} 项", "status": "info" if missing_count > 0 else "success", "alert": missing_count > 0},
        {"icon": "", "label": "完全符合", "value": f"{compliant_count} 项", "status": "success"},
    ]

    md_lines = [
        "# 《合规性审查与风控评级报告》",
        "",
        "### 一、审查结论与强弱对比概览",
        f"- **综合合规评级**：**{rating}**",
        f"- **审查规则库**：内置合规标准（{'已启用' if enable_builtin else '已停用'}） + 自定义标准（{len(custom_rules or [])} 项）",
        f"- **排查统计**：重点不合规 {fatal_count} 项，偏离项 {flaw_count} 项，完全符合 {compliant_count} 项，待补充 {missing_count} 项",
        "",
        "### 二、重点不合规与偏离项清单（强视觉高亮）",
        "| 审查标准 | 文件原文摘录 | 不合规偏离点剖析 | 标准修正文本 |",
        "| :--- | :--- | :--- | :--- |",
    ]

    highlight_items = [r for r in comparison_table if r.get("risk_level_code") in ("red", "fatal", "flaw")]
    for row in highlight_items:
        md_lines.append(
            f"| **{row['category']}** | `{row['quote']}` | **{row['risk_level']}**：{row['risk_reason']} | {row['standard_clause']} |"
        )
    if not highlight_items:
        md_lines.append("| 核心标准 | 全文对照排查 | 未检测到明显不合规或偏离风险 | 建议保持现有约定 |")

    md_lines.extend([
        "",
        "### 三、完全符合项清单（弱视觉弱化）",
        "| 审查标准 | 文件原文摘录 | 合规结论 |",
        "| :--- | :--- | :--- |",
    ])
    for row in compliant_items:
        md_lines.append(
            f"| {row['category']} | `{row['quote']}` | {row['risk_reason']} |"
        )
    if not compliant_items:
        md_lines.append("| - | - | 暂无完全符合项 |")

    md_lines.extend([
        "",
        "### 四、缺失条款与待补充清单",
        "| 序号 | 缺失标准类别 | 缺失风险提示 | 建议补充标准条款 |",
        "| :--- | :--- | :--- | :--- |",
    ])

    if missing_list:
        for idx, m_row in enumerate(missing_list, 1):
            md_lines.append(f"| {idx} | **{m_row['category']}** | 提示：{m_row['missing_issue']} | {m_row['recommended_addition']} |")
    else:
        md_lines.append("未检测到关键条款缺失。")

    full_md = "\n".join(md_lines)

    summary_dict = {
        "fatal_count": fatal_count,
        "flaw_count": flaw_count,
        "missing_count": missing_count,
        "ok_count": compliant_count,
        "compliant_count": compliant_count,
        "overall_risk_rating": rating,
    }

    return {
        "ok": True,
        "title": "合规性审查与风控评级报告",
        "scope_description": "支持合同、采购寻源流程、招投标文件、报销与供应商准入合规审查",
        "rating": rating,
        "summary": summary_dict,
        "fatal_count": fatal_count,
        "flaw_count": flaw_count,
        "missing_count": missing_count,
        "compliant_count": compliant_count,
        "ok_count": compliant_count,
        "kpi_metrics": kpis,
        "fatal_items": fatal_items,
        "flaw_items": flaw_items,
        "missing_items": missing_items,
        "compliant_items": compliant_items,
        "comparison_table": comparison_table,
        "missing_list": missing_list,
        "missing_clauses": missing_list,
        "markdown": full_md,
    }


def analyze_contract_risks(text: str) -> Dict[str, Any]:
    """对合同文本进行确定性风控规则排查（兼顾兼容旧版数据接口与新版6大条款全量审查）"""
    if not text or len(text.strip()) < 10:
        return {
            "fatal_items": [],
            "flaw_items": [],
            "compliance_items": [],
            "kpi_metrics": [
                {"label": "致命风险", "value": "0 项", "icon": "🔴", "status": "success"},
                {"label": "商务瑕疵", "value": "0 项", "icon": "🟡", "status": "success"},
                {"label": "缺失条款", "value": "0 项", "icon": "⚪", "status": "info"},
                {"label": "合规完备", "value": "待排查", "icon": "🟢", "status": "info"},
            ],
            "rating": "待审查",
            "comparison_table": [],
            "missing_list": [],
        }

    full_res = analyze_contract_full(text)
    fatal_str_list = [f"{it['category']}: {it['risk_reason']}" for it in full_res.get("fatal_items", [])]
    flaw_str_list = [f"{it['category']}: {it['risk_reason']}" for it in full_res.get("flaw_items", [])]
    comp_str_list = [f"{it['category']}: {it['risk_reason']}" for it in full_res.get("compliant_items", [])]

    return {
        **full_res,
        "fatal_items": fatal_str_list,
        "flaw_items": flaw_str_list,
        "compliance_items": comp_str_list,
        "raw_fatal_items": full_res.get("fatal_items", []),
        "raw_flaw_items": full_res.get("flaw_items", []),
        "raw_compliance_items": full_res.get("compliant_items", []),
    }


def generate_contract_review_docx(review_data: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """生成标准化合规性审查与风控评级报告（Word .docx）"""
    import docx
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls, qn

    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = f"合规性审查与风控评级报告-{ts}.docx"
    out_path = os.path.join(out_dir, out_filename)

    doc = docx.Document()

    # 全局样式东亚中文字体深度绑定（彻底解决微软雅黑与 EastAsia 字体割裂）
    for s_name in ["Normal", "Heading 1", "Heading 2", "Heading 3", "Title", "Subtitle", "List Bullet"]:
        if s_name in doc.styles:
            st = doc.styles[s_name]
            st.font.name = "Microsoft YaHei"
            rPr = st._element.get_or_add_rPr()
            rFonts = getattr(rPr, "rFonts", None)
            if rFonts is None:
                rFonts = rPr.get_or_add_rFonts()
            rFonts.set(qn("w:eastAsia"), "微软雅黑")

    def apply_run_font(run, name="Microsoft YaHei", east_asia="微软雅黑", size=None, bold=None, color=None):
        run.font.name = name
        rPr = run._element.get_or_add_rPr()
        rFonts = getattr(rPr, "rFonts", None)
        if rFonts is None:
            rFonts = rPr.get_or_add_rFonts()
        rFonts.set(qn("w:eastAsia"), east_asia)
        if size is not None:
            run.font.size = size
        if bold is not None:
            run.font.bold = bold
        if color is not None:
            run.font.color.rgb = color

    def clean_docx_text(text: Any) -> str:
        if not text:
            return ""
        s = str(text)
        # 清除 markdown 表格分隔符 | --- | 或残留的竖线
        s = re.sub(r"\|[-:\s|]+\|", " ", s)
        s = re.sub(r"\|[-:]+", " ", s)
        s = re.sub(r"[-:]+\|", " ", s)
        s = s.replace("|", " ")
        # 清除反引号与加粗标记
        s = s.replace("`", "").replace("**", "").replace("__", "")
        # 清除所有 Emoji 图标
        s = re.sub(r"[🔴🟡🟢⚪⚠️✅📊📋🔍📑✓✕\U0001F300-\U0001F9FF\U0001FA00-\U0001FAFF\u2600-\u26FF\u2700-\u27BF]", "", s)
        s = s.replace("\r", "")
        # 规整多余空白
        s = re.sub(r"[ \t]+", " ", s)
        return s.strip()

    for s in doc.sections:
        s.top_margin = Inches(0.8)
        s.bottom_margin = Inches(0.8)
        s.left_margin = Inches(0.8)
        s.right_margin = Inches(0.8)

    title_clean = clean_docx_text(review_data.get("title") or "合规性审查与风控评级报告")
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_title = p_title.add_run(title_clean)
    apply_run_font(r_title, size=Pt(20), bold=True, color=RGBColor(0x1F, 0x4E, 0x79))
    p_title.paragraph_format.space_after = Pt(6)

    rating_clean = clean_docx_text(review_data.get("rating", "待定"))
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r_sub = p_sub.add_run(f"审查时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}  |  综合合规评级：{rating_clean}")
    apply_run_font(r_sub, size=Pt(10.5), color=RGBColor(0x55, 0x55, 0x55))
    p_sub.paragraph_format.space_after = Pt(14)

    p_kpi = doc.add_paragraph()
    p_kpi.paragraph_format.space_before = Pt(6)
    p_kpi.paragraph_format.space_after = Pt(12)
    kpis = review_data.get("kpi_metrics", [])
    kpi_text = "    ".join(f"[{clean_docx_text(k.get('label', ''))}：{clean_docx_text(k.get('value', ''))}]" for k in kpis)
    r_kpi = p_kpi.add_run(f"【审查排查概况】\n{kpi_text}")
    apply_run_font(r_kpi, size=Pt(11), bold=True, color=RGBColor(0x1F, 0x4E, 0x79))

    h1 = doc.add_paragraph()
    h1.paragraph_format.space_before = Pt(14)
    h1.paragraph_format.space_after = Pt(6)
    r_h1 = h1.add_run("一、逐项合规审查对照表（重点不合规置顶与强弱对比）")
    apply_run_font(r_h1, size=Pt(13), bold=True, color=RGBColor(0x1F, 0x4E, 0x79))

    table_data = list(review_data.get("comparison_table", []))
    if table_data:
        def _row_priority(r):
            code = str(r.get("risk_level_code", "")).lower()
            lvl = str(r.get("risk_level", ""))
            if code in ("red", "fatal") or "致命" in lvl or "重点不合规" in lvl or "红灯" in lvl:
                return 0
            if code in ("flaw", "warn", "yellow") or "偏离" in lvl or "瑕疵" in lvl or "黄灯" in lvl:
                return 1
            return 2

        sorted_table_data = sorted(table_data, key=_row_priority)

        tbl = doc.add_table(rows=len(sorted_table_data) + 1, cols=4)
        tbl.style = "Table Grid"
        headers = ["审查标准项", "文件原文摘录", "合规判定与偏离分析（强弱对比标示）", "建议修订条款"]

        hdr_row = tbl.rows[0]
        for c_idx, title in enumerate(headers):
            cell = hdr_row.cells[c_idx]
            cell.text = title
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                apply_run_font(run, size=Pt(9.5), bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
            shd = parse_xml(r'<w:shd {} w:fill="1F4E79"/>'.format(nsdecls('w')))
            cell._tc.get_or_add_tcPr().append(shd)

        for r_idx, row_info in enumerate(sorted_table_data, 1):
            row_cells = tbl.rows[r_idx].cells
            cat = clean_docx_text(row_info.get("category", ""))
            quote = clean_docx_text(row_info.get("quote", ""))
            lvl = clean_docx_text(row_info.get("risk_level", ""))
            rsn = clean_docx_text(row_info.get("risk_reason", ""))
            std = clean_docx_text(row_info.get("standard_clause", ""))

            code = str(row_info.get("risk_level_code", "")).lower()
            is_fatal = code in ("red", "fatal") or "致命" in lvl or "重点不合规" in lvl or "红灯" in lvl
            is_flaw = code in ("flaw", "warn", "yellow") or "偏离" in lvl or "瑕疵" in lvl or "黄灯" in lvl
            is_compliant = code in ("compliance", "pass", "green") or "符合" in lvl or "绿灯" in lvl

            risk_desc = f"【{lvl}】\n{rsn}" if lvl and rsn else (lvl or rsn)

            row_cells[0].text = cat
            row_cells[1].text = quote
            row_cells[2].text = risk_desc
            row_cells[3].text = std

            if is_fatal:
                fill_color = "FFF5F5"
                text_color = RGBColor(0x99, 0x1B, 0x1B)
            elif is_flaw:
                fill_color = "FFF9F2"
                text_color = RGBColor(0x92, 0x40, 0x0E)
            elif is_compliant:
                fill_color = "F9FAFB"
                text_color = RGBColor(0x86, 0x86, 0x8B)
            else:
                fill_color = "FFFFFF" if r_idx % 2 == 1 else "F9FAFB"
                text_color = RGBColor(0x33, 0x33, 0x33)

            for c_idx in range(4):
                cell = row_cells[c_idx]
                for p in cell.paragraphs:
                    for run in p.runs:
                        if is_fatal or is_flaw:
                            if c_idx in (0, 2):
                                apply_run_font(run, size=Pt(9.0), bold=True, color=text_color)
                            else:
                                apply_run_font(run, size=Pt(9.0), bold=True, color=RGBColor(0x2B, 0x36, 0x4B))
                        elif is_compliant:
                            apply_run_font(run, size=Pt(9.0), bold=False, color=RGBColor(0x86, 0x86, 0x8B))
                        else:
                            apply_run_font(run, size=Pt(9.0), bold=(c_idx == 0), color=text_color)

                shd = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), fill_color))
                cell._tc.get_or_add_tcPr().append(shd)

    h2 = doc.add_paragraph()
    h2.paragraph_format.space_before = Pt(16)
    h2.paragraph_format.space_after = Pt(6)
    r_h2 = h2.add_run("二、缺失条款补充清单（必备风控兜底条款）")
    apply_run_font(r_h2, size=Pt(13), bold=True, color=RGBColor(0x1F, 0x4E, 0x79))

    missing_data = review_data.get("missing_list", [])
    if missing_data:
        tbl_m = doc.add_table(rows=len(missing_data) + 1, cols=3)
        tbl_m.style = "Table Grid"
        m_headers = ["缺失条款类别", "缺失风险提示与说明", "建议补充标准条款"]
        hdr_row = tbl_m.rows[0]
        for c_idx, title in enumerate(m_headers):
            cell = hdr_row.cells[c_idx]
            cell.text = title
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
            for run in cell.paragraphs[0].runs:
                apply_run_font(run, size=Pt(9.5), bold=True, color=RGBColor(0xFF, 0xFF, 0xFF))
            shd = parse_xml(r'<w:shd {} w:fill="4B5563"/>'.format(nsdecls('w')))
            cell._tc.get_or_add_tcPr().append(shd)

        for r_idx, m_info in enumerate(missing_data, 1):
            row_cells = tbl_m.rows[r_idx].cells
            row_cells[0].text = clean_docx_text(m_info.get("category", ""))
            row_cells[1].text = clean_docx_text(m_info.get("missing_issue", ""))
            row_cells[2].text = clean_docx_text(m_info.get("recommended_addition", ""))

            for c_idx in range(3):
                cell = row_cells[c_idx]
                for p in cell.paragraphs:
                    for run in p.runs:
                        apply_run_font(run, size=Pt(9.0), bold=(c_idx == 0), color=RGBColor(0x33, 0x33, 0x33))
                fill_m = "FFFDF5" if r_idx % 2 == 1 else "F9FAFB"
                shd = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), fill_m))
                cell._tc.get_or_add_tcPr().append(shd)

    # 全文深度兜底：确保所有段落和表格中的 run 均已绑定西文与东亚中文字体
    for p in doc.paragraphs:
        for run in p.runs:
            apply_run_font(run)
    for tbl_obj in doc.tables:
        for r in tbl_obj.rows:
            for c in r.cells:
                for p in c.paragraphs:
                    for run in p.runs:
                        apply_run_font(run)

    doc.save(out_path)
    fsize = os.path.getsize(out_path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
    return {
        "ok": True,
        "filename": out_filename,
        "path": out_path,
        "filepath": out_path,
        "filesize": fsize_str,
        "filetype": "doc",
        "kpi_metrics": review_data.get("kpi_metrics", []),
        "preview_data": {
            "type": "doc",
            "title": "合规性审查与风控评级报告",
            "content": review_data.get("markdown", ""),
        },
        "url": f"/files/{out_filename}",
    }


def generate_contract_review_pptx(review_data: Dict[str, Any], out_dir: str) -> Dict[str, Any]:
    """生成标准化合规性审查与风控汇报幻灯片（PPT .pptx）"""
    import pptx
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN

    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_filename = f"合规性审查与风控汇报-{ts}.pptx"
    out_path = os.path.join(out_dir, out_filename)

    prs = pptx.Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    def _add_run_text(p, text, font_size=12, bold=False, color_rgb=None):
        r = p.add_run()
        r.text = str(text)
        r.font.name = "微软雅黑"
        r.font.size = Pt(font_size)
        r.font.bold = bold
        if color_rgb:
            r.font.color.rgb = color_rgb
        return r

    def _add_header(s, title_text, cat_tag="合规性审查"):
        rect = s.shapes.add_shape(1, Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.8))
        rect.fill.solid()
        rect.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
        rect.line.fill.background()

        tb = s.shapes.add_textbox(Inches(1.0), Inches(0.45), Inches(11.333), Inches(0.7))
        p = tb.text_frame.paragraphs[0]
        _add_run_text(p, f"【{cat_tag}】 ", 13, True, RGBColor(0xD9, 0xE1, 0xF2))
        _add_run_text(p, title_text, 18, True, RGBColor(0xFF, 0xFF, 0xFF))

    # Slide 1: Cover
    s1 = prs.slides.add_slide(blank_layout)
    bg1 = s1.shapes.add_shape(1, 0, 0, Inches(13.333), Inches(7.5))
    bg1.fill.solid()
    bg1.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    bg1.line.fill.background()

    tb1 = s1.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(10.333), Inches(3.0))
    tf1 = tb1.text_frame
    p1 = tf1.paragraphs[0]
    _add_run_text(p1, "合规性审查与风控评级报告", 36, True, RGBColor(0xFF, 0xFF, 0xFF))

    p1_sub = tf1.add_paragraph()
    p1_sub.space_before = Pt(16)
    _add_run_text(p1_sub, f"基于内置规则与自定义标准深度排查  |  风控评级：{review_data.get('rating', '待定')}", 18, False, RGBColor(0xD9, 0xE1, 0xF2))

    p1_date = tf1.add_paragraph()
    p1_date.space_before = Pt(28)
    _add_run_text(p1_date, f"报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", 13, False, RGBColor(0xA6, 0xB8, 0xCE))

    # Slide 2: Dashboard & KPIs
    s2 = prs.slides.add_slide(blank_layout)
    _add_header(s2, "合规审查结论与总体风控评级", "核心看板")

    kpis = review_data.get("kpi_metrics", [])
    box_w = Inches(2.7)
    box_h = Inches(2.2)
    start_x = Inches(0.8)
    gap = Inches(0.3)
    y_pos = Inches(1.8)

    bg_colors = [
        RGBColor(0xFD, 0xED, 0xEC),
        RGBColor(0xFE, 0xF9, 0xE7),
        RGBColor(0xF2, 0xF4, 0xF4),
        RGBColor(0xEA, 0xFA, 0xEA),
    ]
    border_colors = [
        RGBColor(0xE7, 0x4C, 0x3C),
        RGBColor(0xF3, 0x9C, 0x12),
        RGBColor(0x7F, 0x8C, 0x8D),
        RGBColor(0x27, 0xAE, 0x60),
    ]

    for i, k in enumerate(kpis[:4]):
        x = start_x + i * (box_w + gap)
        card = s2.shapes.add_shape(1, x, y_pos, box_w, box_h)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_colors[i]
        card.line.color.rgb = border_colors[i]
        card.line.width = Pt(1.5)

        tb_k = s2.shapes.add_textbox(x, y_pos + Inches(0.2), box_w, box_h - Inches(0.4))
        tf_k = tb_k.text_frame
        p_k1 = tf_k.paragraphs[0]
        p_k1.alignment = PP_ALIGN.CENTER
        _add_run_text(p_k1, f"{k['icon']} {k['label']}", 15, True, RGBColor(0x33, 0x33, 0x33))

        p_k2 = tf_k.add_paragraph()
        p_k2.alignment = PP_ALIGN.CENTER
        p_k2.space_before = Pt(14)
        _add_run_text(p_k2, str(k['value']), 28, True, border_colors[i])

    rat_box = s2.shapes.add_shape(1, Inches(0.8), Inches(4.4), Inches(11.733), Inches(2.2))
    rat_box.fill.solid()
    rat_box.fill.fore_color.rgb = RGBColor(0xF8, 0xF9, 0xFA)
    rat_box.line.color.rgb = RGBColor(0x1F, 0x4E, 0x79)
    rat_box.line.width = Pt(1)

    tb_rat = s2.shapes.add_textbox(Inches(1.1), Inches(4.6), Inches(11.133), Inches(1.8))
    tf_rat = tb_rat.text_frame
    p_r1 = tf_rat.paragraphs[0]
    _add_run_text(p_r1, f"【综合审查结论】：{review_data.get('rating', '待审查')}", 16, True, RGBColor(0x1F, 0x4E, 0x79))

    bullets = [
        "1. 针对【🔴 致命风险】项：直接涉及背靠背付款、极端违约金或不利管辖，属于实质性商务陷阱，严禁直接签署！",
        "2. 针对【🟡 商务瑕疵】项：付款未绑定验收报告、发票税率不明确等，须在签约前发出正式修改联络单予以补正；",
        "3. 针对【⚪ 缺失条款】项：合同缺乏知识产权与保密条款，须严格对照标准条款补充签署通用附件协议。",
    ]
    for b in bullets:
        p_b = tf_rat.add_paragraph()
        p_b.space_before = Pt(8)
        _add_run_text(p_b, b, 12, False, RGBColor(0x33, 0x33, 0x33))

    # Slide 3: 条款对照表
    s3 = prs.slides.add_slide(blank_layout)
    _add_header(s3, "关键风险条款摘录与修改建议", "条款审查")

    table_data = review_data.get("comparison_table", [])[:5]
    if table_data:
        rows_cnt = len(table_data) + 1
        tbl_shape = s3.shapes.add_table(rows_cnt, 4, Inches(0.8), Inches(1.5), Inches(11.733), Inches(5.2))
        tbl = tbl_shape.table
        tbl.columns[0].width = Inches(2.0)
        tbl.columns[1].width = Inches(3.2)
        tbl.columns[2].width = Inches(3.0)
        tbl.columns[3].width = Inches(3.533)

        headers = ["条款类别", "合同原句摘录", "风险等级与原因", "建议修改后标准条款"]
        for c_idx, h in enumerate(headers):
            cell = tbl.cell(0, c_idx)
            cell.text = h
            cell.fill.solid()
            cell.fill.fore_color.rgb = RGBColor(0x1F, 0x4E, 0x79)
            for p in cell.text_frame.paragraphs:
                p.alignment = PP_ALIGN.CENTER
                for r in p.runs:
                    r.font.name = "微软雅黑"
                    r.font.size = Pt(12)
                    r.font.bold = True
                    r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

        for r_idx, row_info in enumerate(table_data, 1):
            cell_0 = tbl.cell(r_idx, 0)
            cell_0.text = row_info.get("category", "")
            cell_1 = tbl.cell(r_idx, 1)
            cell_1.text = row_info.get("quote", "")[:70]
            cell_2 = tbl.cell(r_idx, 2)
            cell_2.text = f"{row_info.get('risk_level', '')}\n{row_info.get('risk_reason', '')[:60]}"
            cell_3 = tbl.cell(r_idx, 3)
            cell_3.text = row_info.get("standard_clause", "")[:90]

            for c_idx in range(4):
                c_cell = tbl.cell(r_idx, c_idx)
                if r_idx % 2 == 0:
                    c_cell.fill.solid()
                    c_cell.fill.fore_color.rgb = RGBColor(0xF9, 0xFA, 0xFB)
                for p in c_cell.text_frame.paragraphs:
                    for r in p.runs:
                        r.font.name = "微软雅黑"
                        r.font.size = Pt(9.5)
                        r.font.color.rgb = RGBColor(0x22, 0x22, 0x22)

    prs.save(out_path)
    fsize = os.path.getsize(out_path)
    fsize_str = f"{fsize / 1024:.1f} KB" if fsize < 1024 * 1024 else f"{fsize / (1024 * 1024):.2f} MB"
    return {
        "ok": True,
        "filename": out_filename,
        "path": out_path,
        "filepath": out_path,
        "filesize": fsize_str,
        "filetype": "ppt",
        "kpi_metrics": review_data.get("kpi_metrics", []),
        "preview_data": {
            "type": "ppt",
            "title": "合规性审查与风控汇报",
            "slides": [
                {"title": "合规审查结论与总体风控评级", "bullets": [f"{k['label']}：{k['value']}" for k in kpis]},
                {"title": "重点不合规与偏离项摘录与修改建议", "bullets": [f"[{r.get('category')}] {r.get('risk_level')}：{r.get('risk_reason')[:40]}" for r in table_data]},
            ]
        },
        "url": f"/files/{out_filename}",
    }


def _clean_numeric_series(series: pd.Series) -> pd.Series:
    """清洗表格数值列中的逗号、货币符号、百分号及各类中英文工程/统计单位后缀。"""
    s = series.astype(str).str.strip()

    # 替换常见空值占位符为 NaN
    placeholders = {"", "-", "--", "—", "——", "N/A", "n/a", "null", "None", "/", "无", "待核实", "暂无", "缺货", "nan"}
    s = s.replace(list(placeholders), np.nan)

    # 去除逗号与货币前缀
    s = s.str.replace(",", "", regex=False)
    s = s.str.replace("￥", "", regex=False)
    s = s.str.replace("¥", "", regex=False)
    s = s.str.replace("$", "", regex=False)
    s = s.str.replace("€", "", regex=False)
    s = s.str.replace(r"(?i)\brmb\b", "", regex=True)

    # 去除百分号
    s = s.str.replace("%", "", regex=False)

    # 去除常见中英文单位后缀
    unit_pattern = r"(吨|万元|千元|亿元|元|件|套|个|kg|KG|m³|m2|m3|立方米|平方米|米|台|箱|包|张|只|把|卷|桶|次|项)$"
    s = s.str.replace(unit_pattern, "", regex=True).str.strip()

    return pd.to_numeric(s, errors="coerce")


def extract_chart_series(files: Any) -> List[Dict[str, Any]]:
    """从上传的 Excel/CSV 文件中提取 Top 8 分组数值序列（用于 Office 原生图表渲染）。
    
    返回格式：
    [
        {
            "chart_title": str,
            "category_name": str,
            "categories": list[str],      # 最多 8 项
            "series": [
                {"name": str, "values": list[float]}
            ],
            "suggested_type": str        # "column" | "line" | "pie"
        }
    ]
    """
    file_list = []
    if isinstance(files, (str, dict)):
        files = [files]
    for f in files or []:
        if isinstance(f, str):
            file_list.append({"name": os.path.basename(f), "path": f})
        elif isinstance(f, dict):
            path = f.get("path") or f.get("filepath") or ""
            name = f.get("name") or f.get("filename") or os.path.basename(path)
            file_list.append({"name": name, "path": path})

    results = []
    loaded_tables = []
    for item in file_list:
        fpath = item.get("path", "")
        fname = item.get("name", "")
        if not fpath or not os.path.isfile(fpath):
            continue
        dfs = read_dataframes_from_file(fpath)
        for sname, df in dfs.items():
            if df is not None and not df.empty and df.shape[0] > 0 and df.shape[1] > 0:
                df = df.copy()
                df.columns = [str(c).strip() for c in df.columns]
                loaded_tables.append((fname, sname, df))

    # 多表对比 / 对账图表提取
    if len(loaded_tables) >= 2:
        t1_name, t1_sheet, df1 = loaded_tables[0]
        t2_name, t2_sheet, df2 = loaded_tables[1]
        
        # 优先使用同名或同语义别名匹配键
        alias_groups = [
            ["物资名称", "物料名称", "材料名称", "名称", "品名"],
            ["规格型号", "规格", "型号"],
            ["供应商", "供方", "单位名称"],
            ["编码", "物料编码", "物资编码", "编号"]
        ]
        k1, k2 = None, None
        for group in alias_groups:
            cand1 = _find_matching_col(df1, group)
            cand2 = _find_matching_col(df2, group)
            if cand1 and cand2:
                k1, k2 = cand1, cand2
                break

        if not k1 or not k2:
            for c1 in df1.columns:
                for c2 in df2.columns:
                    if c1 == c2 and not np.issubdtype(df1[c1].dtype, np.number):
                        k1, k2 = c1, c2
                        break

        if k1 and k2:
            jk = "物资名称" if "物" in k1 or "物" in k2 else k1
            
            def _find_numeric_col(df):
                cand = []
                for c in df.columns:
                    if any(w in c for w in ("单位", "规格", "型号", "编码", "日期", "供方", "需方")):
                        continue
                    ser = _clean_numeric_series(df[c])
                    if ser.notna().sum() >= max(1, len(df) * 0.3):
                        score = 0 if any(w in c for w in ("量", "额", "数", "总", "价")) else 1
                        cand.append((score, c, ser))
                cand.sort(key=lambda x: x[0])
                return cand[0][1:] if cand else (None, None)

            q1, ser1 = _find_numeric_col(df1)
            q2, ser2 = _find_numeric_col(df2)

            if q1 and q2:
                df1_clean = pd.DataFrame({jk: df1[k1].astype(str), q1: ser1.fillna(0.0)})
                df2_clean = pd.DataFrame({jk: df2[k2].astype(str), q2: ser2.fillna(0.0)})

                grp1 = df1_clean.groupby(jk)[q1].sum()
                grp2 = df2_clean.groupby(jk)[q2].sum()
                common_keys = [k for k in grp1.index if k in grp2.index]
                if common_keys:
                    sorted_keys = sorted(common_keys, key=lambda k: grp1.get(k, 0.0), reverse=True)[:8]
                    results.append({
                        "chart_title": f"{jk}调拨与数量对比分析",
                        "category_name": jk,
                        "categories": [str(k) for k in sorted_keys],
                        "series": [
                            {"name": q1, "values": [float(round(grp1.get(k, 0.0), 2)) for k in sorted_keys]},
                            {"name": q2, "values": [float(round(grp2.get(k, 0.0), 2)) for k in sorted_keys]},
                        ],
                        "suggested_type": "column"
                    })

    # 单表 Top 8 分组统计序列提取
    for fname, sname, df in loaded_tables:
        numeric_cols = []
        for col in df.columns:
            ser = _clean_numeric_series(df[col])
            if ser.notna().sum() >= max(1, len(df) * 0.3):
                numeric_cols.append((col, ser))

        if not numeric_cols:
            continue

        num_col_names = {nc[0] for nc in numeric_cols}
        cat_candidates = [c for c in df.columns if c not in num_col_names]
        key_cat_cols = [c for c in cat_candidates if any(k in c for k in ("供应商", "类别", "类型", "部门", "名称", "状态", "物料", "物资", "产品", "月份", "日期", "季度"))]
        primary_cat = key_cat_cols[0] if key_cat_cols else (cat_candidates[0] if cat_candidates else df.columns[0])

        # 按度量重要性排序数值列
        def _num_score(cname):
            if any(k in cname for k in ("额", "总", "量", "数")):
                return 0
            if any(k in cname for k in ("价", "率", "比")):
                return 1
            return 2

        numeric_cols.sort(key=lambda x: _num_score(x[0]))
        primary_num, primary_ser = numeric_cols[0]

        temp_df = pd.DataFrame({primary_cat: df[primary_cat].astype(str), primary_num: primary_ser.fillna(0.0)})
        grp = temp_df.groupby(primary_cat)[primary_num].sum().sort_values(ascending=False).head(8)
        if not grp.empty:
            categories = [str(c) for c in grp.index]
            series_list = [{"name": primary_num, "values": [float(round(v, 2)) for v in grp.values]}]

            # 若存在第二个数值指标，追加该指标的对应对比数据
            if len(numeric_cols) > 1:
                sec_num, sec_ser = numeric_cols[1]
                temp_sec = pd.DataFrame({primary_cat: df[primary_cat].astype(str), sec_num: sec_ser.fillna(0.0)})
                grp_sec = temp_sec.groupby(primary_cat)[sec_num].sum()
                sec_vals = [float(round(grp_sec.get(c, 0.0), 2)) for c in categories]
                series_list.append({"name": sec_num, "values": sec_vals})

            # 判断推荐图表类型
            time_keywords = ("月", "年", "季度", "Q1", "Q2", "Q3", "Q4", "202", "日", "周")
            is_time = len(categories) >= 3 and any(any(k in str(c) for k in time_keywords) for c in categories)
            prop_keywords = ("占比", "比例", "份额", "结构", "分布", "%", "比重")
            is_prop = len(series_list) == 1 and (
                any(k in primary_num for k in prop_keywords) or
                (
                    all(v is not None and isinstance(v, (int, float)) and v >= 0 for v in series_list[0]["values"])
                    and 90.0 <= sum(v for v in series_list[0]["values"] if v is not None and isinstance(v, (int, float))) <= 105.0
                )
            )
            if is_prop:
                suggested_type = "pie"
            elif is_time:
                suggested_type = "line"
            else:
                suggested_type = "column"

            chart_title = f"{primary_cat}与{primary_num}汇总分析"
            results.append({
                "chart_title": chart_title,
                "category_name": primary_cat,
                "categories": categories,
                "series": series_list,
                "suggested_type": suggested_type
            })

    return results



