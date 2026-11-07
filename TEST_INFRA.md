# Enterprise PPT Generation Engine — E2E Testing Track Infrastructure (TEST_INFRA.md)

## 1. Quality Engineering Strategy & Architecture

The testing strategy follows a 4-tier verification hierarchy combining **Category-Partition Testing**, **Boundary Value Analysis (BVA)**, **Pairwise Combinatorial Testing**, and **Real-World Workload Stress Testing**.

```
+-----------------------------------------------------------------------------------+
| Tier 4: Real-World Application Workloads (End-to-End Enterprise Scenarios)        |
+-----------------------------------------------------------------------------------+
| Tier 3: Cross-Feature Combinations (Pairwise Integration & Interface Contracts)   |
+-----------------------------------------------------------------------------------+
| Tier 2: Boundary Value & Adversarial Edge Cases (Min/Max/Overflow/Corrupt/Empty)  |
+-----------------------------------------------------------------------------------+
| Tier 1: Feature Functional Coverage (>= 5 Tests per Feature across 15 Features)    |
+-----------------------------------------------------------------------------------+
```

### Verification Execution Environment
- **Python Runtime**: `D:\AI\runtime\python\python.exe`
- **Primary Test Runner**: `D:\AI\test_suite.py`
- **Output Artifacts**: `D:\AI\output\`
- **Interface Contract Authority**: `D:\AI\.agents\teamwork\PROJECT.md` & `ORIGINAL_REQUEST.md`

---

## 2. Feature Inventory Mapping (15 Features)

| Feature ID | Feature Name | Core Module | Milestone | Acceptance Criteria Key |
|---|---|---|---|---|
| **F01** | 7 Standard Master Slide Layouts | `app/core.py` | M1 | R1: Cover, Catalog, Transition, Conclusion, Chart, Table, Ending |
| **F02** | Unified Footer & Page Numbering | `app/core.py` | M1 | R1: Left source, right "第 X 页", cover/ending unnumbered |
| **F03** | Speaker Notes Automation | `app/core.py` | M1 | R1: Expanded details and overflow to `slide.notes_slide` |
| **F04** | Bullet Simplification & Auto-Fit | `app/core.py` | M1 | R3: Max 4-5 points, strictly <= 30 chars, dynamic font scaling |
| **F05** | Pre-Export Validation (`validate_ppt_before_save`) | `app/core.py` | M1 | R3: Remove blank slides, detect missing charts, 0-overflow report string |
| **F06** | Repetition Breaker Fix | `app/core.py` | M1 | R4: Markdown tables and divider rules (`|-:+=_`) not misfired |
| **F07** | Excel Structured Series Extraction | `app/calc_engine.py` | M1 | R2: `extract_chart_series` produces categories and numeric series |
| **F08** | Markdown Table Series Extraction | `app/core.py` | M1 | R2: `extract_series_from_table` extracts categories and series |
| **F09** | Native Office Charts Generation | `app/core.py` | M1 | R2: `CategoryChartData`, `add_chart`, column/line/pie, editable |
| **F10** | Chart Type Selection Mechanism | `app/core.py` | M1 | R2: Directives priority over time/proportion/comparison heuristics |
| **F11** | Native Chart Slide Integration | `app/core.py` | M1 | R1, R2: 16:9 canvas, Left Chart (6.8"x4.85"), Right Conclusion (4.68"x4.85") |
| **F12** | Backend File & Directory Open API | `app/webapp.py` | M2 | R4: `/api/file/open` opens files and directories with `os.startfile` |
| **F13** | Frontend File Delivery Card | `app/web/app.js` | M2 | R4: White rounded card under bubble, size, validation badge, open/reveal |
| **F14** | Eliminate `127.0.0.1:7860` Popups | `app/web/app.js` | M2 | R4: No native `alert/confirm` exposing port 7860 |
| **F15** | Automated Test Suite Expansion & 100% Pass | `test_suite.py` | M3 | Verification: 100% pass under `python.exe test_suite.py` |

---

## 3. Tier 1: Functional Feature Coverage (>= 5 Tests per Feature)

### Feature 1: 7 Standard Master Slide Layouts
- **T1.F01.01 (Cover Slide Layout)**: Verify Cover layout generates full-bleed dark background (`#12182A`), gold vertical bar (`#E7C27D`), main title, subtitle, and date metadata.
- **T1.F01.02 (Catalog Slide Layout)**: Verify Catalog layout renders top brand bar, section grid/cards with sequential index badges ("01", "02").
- **T1.F01.03 (Section Transition Slide Layout)**: Verify Transition layout renders full-bleed dark canvas with `PART XX` heading and topic focus subtitle.
- **T1.F01.04 (Conclusion Dual-Column Slide Layout)**: Verify Conclusion layout produces dual cards (Diagnosis vs Plan or Status vs Goal) within content bounds.
- **T1.F01.05 (Standard Table & Ending Slide Layout)**: Verify Table layout creates native PPTX table with styled headers, and Ending slide creates closing greeting without page number.

### Feature 2: Unified Footer & Page Numbering
- **T1.F02.01 (Cover Slide Omission)**: Verify slide 0 (cover) contains zero footer shapes or page number text.
- **T1.F02.02 (Ending Slide Omission)**: Verify last slide (ending) contains zero footer shapes or page number text.
- **T1.F02.03 (Left Source Attribution)**: Verify content slide footers contain specified data source string (e.g. `数据来源：ERP采购对账清单`).
- **T1.F02.04 (Right Sequential Page Numbering)**: Verify content slides display sequential format `第 X 页` matching slide sequence index.
- **T1.F02.05 (Footer Coordinate Stability)**: Verify footer Y-coordinate is positioned at `Top=6.85"` across all content slide types.

### Feature 3: Speaker Notes Automation
- **T1.F03.01 (Direct Notes Ingestion)**: Verify explicit notes in slide payload (`notes="详细统计背景说明"`) are written to `slide.notes_slide.notes_text_frame.text`.
- **T1.F03.02 (Markdown Blockquote Ingestion)**: Verify markdown text containing `> 演讲备注：...` correctly routes text into speaker notes.
- **T1.F03.03 (Multi-Paragraph Notes)**: Verify multi-line speaker notes preserve newline formatting in PowerPoint notes pane.
- **T1.F03.04 (Table Data Stash in Notes)**: Verify raw underlying tabular data is recorded in chart slide speaker notes for presenter reference.
- **T1.F03.05 (Non-Destructive Notes Creation)**: Verify accessing `slide.notes_slide` creates a valid notes slide without altering slide shape hierarchy.

### Feature 4: Bullet Simplification & Auto-Fit
- **T1.F04.01 (Bullet Count Cap <= 5)**: Input slide with 8 bullets; verify only top 5 bullets appear on slide canvas.
- **T1.F04.02 (Bullet Overflow Spillage to Notes)**: Input slide with 8 bullets; verify bullets 6-8 are automatically moved into speaker notes.
- **T1.F04.03 (Bullet Length Enforcement <= 30 chars)**: Input bullet with 45 characters; verify slide canvas text is strictly truncated/formatted to <= 30 chars.
- **T1.F04.04 (Original Sentence Backup)**: Input long bullet (>30 chars); verify original full text is preserved in speaker notes under `【要点补充阐述】`.
- **T1.F04.05 (Dynamic Title Font Scaling)**: Input short title (10 chars -> 26pt), medium title (18 chars -> 22pt), long title (26 chars -> 18pt); verify font sizes match scaling matrix.

### Feature 5: Pre-Export Validation (`validate_ppt_before_save`)
- **T1.F05.01 (Total Slides Count Check)**: Verify `validate_ppt_before_save` returns accurate `total_slides` count matching non-blank slides.
- **T1.F05.02 (Blank Slide Elimination)**: Feed presentation containing 1 blank slide; verify blank slide is physically purged (`removed_blank_slides == 1`).
- **T1.F05.03 (Chart Shape Verification)**: Verify `chart_count` accurately counts all native `shape.has_chart == True` elements.
- **T1.F05.04 (Residual Overflow Detection)**: Verify `overflow_count` returns 0 when all bullets adhere to <= 30 chars.
- **T1.F05.05 (Standardized Report String)**: Verify `report_text` strictly matches regex `^《PPT 导出自检报告（共 \d+ 页，含 \d+ 张原生图表，0 处溢出）》$`.

### Feature 6: Repetition Breaker Fix
- **T1.F06.01 (Markdown Table Divider Immunity)**: Test `_detect_repetition("|---|---|---|---|---|---|---|---|---|")` returns `False`.
- **T1.F06.02 (ASCII Table Divider Immunity)**: Test `_detect_repetition("+---+---+---+---+---+---+")` returns `False`.
- **T1.F06.03 (Long Horizontal Dash Rule Immunity)**: Test `_detect_repetition("-" * 160)` returns `False`.
- **T1.F06.04 (Genuine Repetitive Character Circuit Break)**: Test `_detect_repetition("a" * 150)` returns `True`.
- **T1.F06.05 (Genuine Sentence Loop Circuit Break)**: Test `_detect_repetition("关于推进项目采购降本增效专项任务的执行要求" * 4)` returns `True`.

### Feature 7: Excel Structured Series Extraction
- **T1.F07.01 (Single Numeric Metric Extraction)**: Parse Excel with material name and quantity; verify categories and series values match Excel data.
- **T1.F07.02 (Dual Metric Reconciliation Extraction)**: Parse reconciliation Excel (Plan vs Actual); verify 2 series objects are returned.
- **T1.F07.03 (Top 8 Aggregation Cap)**: Parse Excel with 20 categories; verify returned `categories` list length is capped at <= 8.
- **T1.F07.04 (Numeric String Cleaning)**: Parse Excel containing formatted strings like `"￥3,850.00"`; verify extracted value is float `3850.0`.
- **T1.F07.05 (Chart Type Suggestion)**: Verify returned dictionary contains valid `suggested_type` in `["column", "line", "pie"]`.

### Feature 8: Markdown Table Series Extraction
- **T1.F08.01 (Standard Markdown Table Parsing)**: Extract from 2-column Markdown table; verify category list and single numerical series.
- **T1.F08.02 (Multi-Series Comparison Table)**: Extract from 3-column table (Category, 2025, 2026); verify 2 distinct series objects.
- **T1.F08.03 (Unit Suffix Stripping)**: Extract columns with unit strings (e.g. `120.5吨`, `98.5%`); verify extracted numbers are clean floats.
- **T1.F08.04 (Missing Value Coercion)**: Extract rows containing `-` or `N/A`; verify coerced to `0.0` or handled without throwing.
- **T1.F08.05 (Directive Tag Extraction)**: Extract table with preceding `[图表: 折线图]`; verify `suggested_type == "line"`.

### Feature 9: Native Office Charts Generation
- **T1.F09.01 (Editable Column Chart)**: Verify `slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, ...)` generates native chart with `shape.has_chart is True`.
- **T1.F09.02 (Editable Line Chart)**: Verify `XL_CHART_TYPE.LINE_MARKERS` generates line chart with markers.
- **T1.F09.03 (Editable Pie Chart)**: Verify `XL_CHART_TYPE.PIE` generates native pie chart without axis error.
- **T1.F09.04 (Enterprise Palette Formatting)**: Verify chart series colors use enterprise blue (`#1F4E79`) and gold (`#E7C27D`).
- **T1.F09.05 (Legend & Data Labels Placement)**: Verify legend placed at top (`XL_LEGEND_POSITION.TOP`) and data labels enabled.

### Feature 10: Chart Type Selection Mechanism
- **T1.F10.01 (Explicit Directive Priority - Pie)**: Input data with `[图表: 饼图]`; verify selector outputs `pie` regardless of category count.
- **T1.F10.02 (Explicit Directive Priority - Line)**: Input comparison data with `[图表: 折线图]`; verify selector outputs `line`.
- **T1.F10.03 (Time Series Heuristic)**: Input categories containing `["1月", "2月", "3月"]`; verify selector infers `line`.
- **T1.F10.04 (Proportion Heuristic)**: Input single series summing to ~100 with keyword "占比"; verify selector infers `pie`.
- **T1.F10.05 (General Comparison Default)**: Input general non-temporal entity comparison; verify selector defaults to `column`.

### Feature 11: Native Chart Slide Integration
- **T1.F11.01 (16:9 Left/Right Geometry)**: Verify left chart geometry (`Left=0.8"`, `Width=6.8"`, `Height=4.85"`) and right card (`Left=7.85"`, `Width=4.68"`).
- **T1.F11.02 (Right Conclusion Card Heading)**: Verify right card includes title `💡 核心数据分析结论` in bold blue.
- **T1.F11.03 (Right Card Bullet Constraints)**: Verify right card contains 3-4 bullets each <= 30 chars.
- **T1.F11.04 (KPI Callout Badge)**: Verify bottom of right card contains prominent KPI figure when specified.
- **T1.F11.05 (Chart Missing Graceful Fallback)**: Provide invalid chart data; verify slide converts cleanly to structured conclusion card rather than crashing.

### Feature 12: Backend File & Directory Open API
- **T1.F12.01 (Direct Output File Opening)**: POST `/api/file/open` with `{"path": "D:\\AI\\output\\report.pptx"}`; verify `os.startfile` called with file path.
- **T1.F12.02 (Directory Opening Mode)**: POST `/api/file/open` with `{"path": "D:\\AI\\output", "is_dir": true}`; verify `os.startfile` called with directory path.
- **T1.F12.03 (Path Safety Whitelist)**: POST `/api/file/open` with unauthorized path `C:\Windows\System32\cmd.exe`; verify HTTP 403/404 rejection.
- **T1.F12.04 (Default Output Directory Fallback)**: POST `/api/file/open` with empty payload; verify defaults to opening `core.OUT_DIR`.
- **T1.F12.05 (Non-Existent File Handling)**: POST `/api/file/open` with non-existent filename; verify HTTP 404 response with descriptive JSON.

### Feature 13: Frontend File Delivery Card
- **T1.F13.01 (Card Mounting Below Reply Bubble)**: Verify DOM structure places `.artifact-card` immediately adjacent to `.md` reply bubble.
- **T1.F13.02 (Filename & Extension Badge)**: Verify card displays correct file name (e.g. `report.pptx`) and file icon (`📑`).
- **T1.F13.03 (File Size Display)**: Verify formatted file size (e.g. `128 KB`) is visible on card header.
- **T1.F13.04 (Self-Check Badge)**: Verify card displays validation badge `✓ 自检通过 · 0处溢出`.
- **T1.F13.05 (Action Button Pair)**: Verify presence of both buttons `[📂 直接用本机软件打开]` and `[📁 打开所在目录]`.

### Feature 14: Eliminate `127.0.0.1:7860` Popups
- **T1.F14.01 (Zero Native Alert Calls)**: Static analysis of `app.js` confirms zero raw `window.alert(` or un-intercepted `alert(`.
- **T1.F14.02 (Zero Native Confirm Calls)**: Static analysis confirms zero raw un-intercepted `confirm(`.
- **T1.F14.03 (Global Alert Monkeypatch)**: Verify `window.alert` is overridden to forward to custom toast/modal.
- **T1.F14.04 (Global Confirm Monkeypatch)**: Verify `window.confirm` is overridden to non-blocking modal.
- **T1.F14.05 (Custom Confirm Modal Operation)**: Verify `showConfirm` renders in-DOM iOS-style dialog without browser host disclosure.

### Feature 15: Automated Test Suite Expansion & 100% Pass
- **T1.F15.01 (Suite Execution Return Code)**: Run `D:\AI\runtime\python\python.exe D:\AI\test_suite.py`; verify exit code == 0.
- **T1.F15.02 (Regression Test Continuity)**: Verify original 10 test chapters remain intact and pass.
- **T1.F15.03 (New Test Chapters Verification)**: Verify new chapters covering R1, R2, R3, R4 execute without errors.
- **T1.F15.04 (Execution Performance)**: Verify full suite completes within acceptable timeout (< 30 seconds).
- **T1.F15.05 (Test Independence)**: Verify test runner cleans up all temporary PPTX/XLSX test artifacts.

---

## 4. Tier 2: Boundary & Corner Cases (>= 5 Tests per Feature)

### Feature 1: 7 Standard Master Slide Layouts (Corner Cases)
- **T2.F01.01 (Empty Presentation)**: Pass `slides: []` to `build_pptx`; verify cover slide is created and validation reports minimum slide threshold.
- **T2.F01.02 (Extreme Slide Count)**: Generate 50 consecutive slides; verify coordinate alignment and formatting remain consistent.
- **T2.F01.03 (Empty Section Title in Transition)**: Pass transition slide with empty title; verify fallback placeholder `章节过渡`.
- **T2.F01.04 (Special Characters in Slide Title)**: Pass titles with XML entities (`<>&"'\r\n`); verify proper escaping in PPTX DOM.
- **T2.F01.05 (Table Slide with 1x1 Cell)**: Pass table with single row and column; verify table layout does not crash.

### Feature 2: Unified Footer & Page Numbering (Corner Cases)
- **T2.F02.01 (Single Slide Deck)**: Deck with only 1 cover slide; verify 0 footers and no division-by-zero errors.
- **T2.F02.02 (Source String Exceeding 100 Chars)**: Provide extremely long source note; verify text auto-wraps without overlapping right page number.
- **T2.F02.03 (None / Empty Source String)**: Provide `source: ""` or `None`; verify left footer safely renders empty string without `None` literal.
- **T2.F02.04 (All Transition Slides Deck)**: Presentation composed solely of transition slides; verify page numbering remains monotonic.
- **T2.F02.05 (Repeated Layout Swapping)**: Alternating cover-like and content layouts; verify page numbers only increment on content slides.

### Feature 3: Speaker Notes Automation (Corner Cases)
- **T2.F03.01 (Extreme Notes Length - 5000 Chars)**: Inject 5,000 characters of LLM chain-of-thought into notes; verify PowerPoint notes frame accepts full text without truncation.
- **T2.F03.02 (Emoji and Unicode Multilingual Notes)**: Inject Chinese, Japanese, Emoji (`📊💡🚀`), and math symbols into notes; verify proper UTF-8 serialization.
- **T2.F03.03 (None / Null Notes Value)**: Payload has `"notes": None`; verify handled as empty string without `TypeError`.
- **T2.F03.04 (Multiple Calls to Notes)**: Multiple appended overflow items; verify string concatenation uses clean newlines.
- **T2.F03.05 (Notes on Cover & Ending Slides)**: Add notes to cover and ending slides; verify notes slide is created and populated properly.

### Feature 4: Bullet Simplification & Auto-Fit (Corner Cases)
- **T2.F04.01 (Exact 30-Char Boundary)**: Bullet with exactly 30 Chinese characters; verify it remains on slide without truncation or spillage.
- **T2.F04.02 (31-Char Off-By-One)**: Bullet with 31 characters; verify first 28 chars + `...` on canvas and full text moved to notes.
- **T2.F04.03 (Zero Bullets on Content Slide)**: Content slide with `bullets: []`; verify card renders cleanly without empty bullet symbols (`■`).
- **T2.F04.04 (All Bullets Exceeding 100 Chars)**: All 5 bullets > 100 chars; verify canvas stays clean with 5 short summaries and notes hold all 5 original paragraphs.
- **T2.F04.05 (Whitespace & Punctuation Edge Case)**: Bullet consisting of whitespace, tabs, and punctuation; verify sanitized cleanly.

### Feature 5: Pre-Export Validation (`validate_ppt_before_save`) (Corner Cases)
- **T2.F05.01 (All-Blank Presentation)**: Presentation where every content slide is blank; verify blank slides are removed and minimum slide policy maintained.
- **T2.F05.02 (Slide with Invisible Empty Textbox)**: Textbox containing only whitespace `\t\n `; verify detected as blank and cleaned.
- **T2.F05.03 (Corrupted Chart Shape Detection)**: Slide flagged as chart layout but chart shape missing; verify detector flags missing chart and reports issue.
- **T2.F05.04 (Zero-Overflow Perfect Score)**: High quality presentation with all bullets <= 30 chars; verify report string strictly states `0 处溢出`.
- **T2.F05.05 (Idempotent Validation)**: Run `validate_ppt_before_save(prs)` twice in succession; verify second run produces identical results and zero slide deletions.

### Feature 6: Repetition Breaker Fix (Corner Cases)
- **T2.F06.01 (Mixed Table Delimiter Line)**: Test `| :---: | ---- | :===: | +---+`; verify not blocked.
- **T2.F06.02 (Empty Table Row)**: Test `| | | | | | | | | | |`; verify not blocked.
- **T2.F06.03 (Hyphen Bullet List with 50 Lines)**: List of 50 short `- item` lines; verify not misfired.
- **T2.F06.04 (149 Same Characters Boundary)**: Test 149 repeated `x` characters; verify returns `False`.
- **T2.F06.05 (150 Same Characters Boundary)**: Test 150 repeated `x` characters; verify returns `True`.

### Feature 7: Excel Structured Series Extraction (Corner Cases)
- **T2.F07.01 (Excel with Empty Rows / Headers in Row 3)**: Header offset by empty rows; verify engine handles or recovers table structure.
- **T2.F07.02 (Non-Numeric Text Columns)**: Excel with all text columns (Remarks, Status); verify does not throw and skips non-numeric series.
- **T2.F07.03 (Negative Numbers in Quantity / Price)**: Negative values (e.g. `-120.5`); verify parsed as negative floats.
- **T2.F07.04 (Mixed Types in Value Column)**: Column containing `[100, "待核", 200, None]`; verify numeric values extracted and non-numeric handled gracefully.
- **T2.F07.05 (Non-Existent File Path)**: Pass non-existent path to `extract_chart_series`; verify returns empty list without unhandled exception.

### Feature 8: Markdown Table Series Extraction (Corner Cases)
- **T2.F08.01 (Table with Trailing / Leading Spaces)**: Columns with erratic spacing; verify cells trimmed and parsed cleanly.
- **T2.F08.02 (Single Data Row Table)**: Table with header and only 1 row; verify extracted as 1 category.
- **T2.F08.03 (Table with Chinese Full-Width Numbers)**: Table with `１２３．５`; verify normalized and converted.
- **T2.F08.04 (Table with Percentage Signs)**: Values like `98.5%`; verify converted to `98.5` float.
- **T2.F08.05 (Malformed Markdown Divider)**: Divider lacking pipes `--- --- ---`; verify parser recovers or skips without crash.

### Feature 9: Native Office Charts Generation (Corner Cases)
- **T2.F09.01 (Pie Chart with Negative Value Guard)**: Pass negative value to pie chart; verify auto-downgraded to column chart to prevent Office repair error.
- **T2.F09.02 (Pie Chart with Multi-Series Guard)**: Pass 2 series to pie chart; verify auto-downgraded to column chart.
- **T2.F09.03 (Zero Values in Series)**: Pass `[0.0, 0.0, 0.0]`; verify chart generated without division by zero.
- **T2.F09.04 (Single Category in Series)**: Pass 1 category and 1 value; verify chart generates valid shape.
- **T2.F09.05 (Very Long Category Names)**: Category names with > 15 chars; verify labels do not crash chart builder.

### Feature 10: Chart Type Selection Mechanism (Corner Cases)
- **T2.F10.01 (Contradictory Directives)**: Text contains both `[图表: 柱状图]` and `[图表: 折线图]`; verify first directive takes precedence.
- **T2.F10.02 (Case Insensitive Directives)**: Directives in English `[chart: line]`, `[CHART: PIE]`; verify recognized properly.
- **T2.F10.03 (Non-Temporal Numbered Categories)**: Categories `["序号1", "序号2", "序号3"]`; verify not misclassified as time-series line.
- **T2.F10.04 (Proportion Sum Edge - 94% vs 95%)**: Series summing to 94%; verify boundary check prevents false pie selection.
- **T2.F10.05 (Category Count > 8 with Pie Directive)**: Directive requests pie but 12 categories exist; verify grouped to top 7 + "其他".

### Feature 11: Native Chart Slide Integration (Corner Cases)
- **T2.F11.01 (Chart Data Missing in Chart Layout)**: Slide marked type `chart` with `chart_data: None`; verify fallback to conclusion card without crash.
- **T2.F11.02 (Right Conclusion Bullets Empty)**: Chart slide with `bullets: []`; verify right card displays default summary from series metadata.
- **T2.F11.03 (Excessive Bullets on Chart Slide)**: 8 bullets supplied for right card; verify capped to <= 4 and rest sent to notes.
- **T2.F11.04 (Zero Series Values in Chart Data)**: Series with empty values `[]`; verify fallback gracefully handled.
- **T2.F11.05 (Double Call to Chart Generation on Same Slide)**: Verify idempotent shape generation without coordinate collision.

### Feature 12: Backend File & Directory Open API (Corner Cases)
- **T2.F12.01 (Directory Path with Trailing Backslash)**: Path `D:\AI\output\`; verify `os.startfile` called with normalized path.
- **T2.F12.02 (Directory Traversal Attack Attempt)**: Path `D:\AI\output\..\..\Windows\System32`; verify blocked by whitelist check.
- **T2.F12.03 (Opening File as Directory `is_dir=True`)**: Pass file path with `is_dir=True`; verify `os.path.dirname` opened.
- **T2.F12.04 (Non-ASCII File Path with Spaces & Chinese)**: Path with `专项汇报 2026-10-31 (最终版).pptx`; verify handled cleanly.
- **T2.F12.05 (File In Use / Locked by PowerPoint)**: Open already opened file; verify `os.startfile` launches or brings window to focus without error.

### Feature 13: Frontend File Delivery Card (Corner Cases)
- **T2.F13.01 (Missing Filesize Metadata)**: Card metadata has `filesize: ""`; verify card renders with placeholder or calculates size.
- **T2.F13.02 (Extremely Long Filename)**: Filename with 80 Chinese characters; verify ellipsis truncation (`text-overflow: ellipsis`).
- **T2.F13.03 (Failed Validation Report Badge)**: Status indicates warnings; verify badge displays warning style instead of success green.
- **T2.F13.04 (Rapid Successive Click on Open)**: User clicks open button rapidly; verify debounce prevents spawning multiple duplicate processes.
- **T2.F13.05 (Unsupported File Extension Badge)**: Pass file with `.pdf`; verify default file icon fallback.

### Feature 14: Eliminate `127.0.0.1:7860` Popups (Corner Cases)
- **T2.F14.01 (Alert with Empty / Null String)**: Call `window.alert()`; verify custom dialog handles empty message gracefully.
- **T2.F14.02 (Confirm Triggered in Event Listener)**: Call `window.confirm()` inside async fetch error; verify non-blocking behavior.
- **T2.F14.03 (Prompt Call Interception)**: Call `window.prompt()`; verify returns `null` and logs warning without native popup.
- **T2.F14.04 (Nested Dialog Requests)**: Trigger alert while confirm modal is visible; verify queuing or toast stack.
- **T2.F14.05 (Cross-Origin Iframe Alert Shielding)**: Verify host window alerts cannot bleed port 7860 to parent frames.

### Feature 15: Automated Test Suite Expansion & 100% Pass (Corner Cases)
- **T2.F15.01 (Temporary Output Directory Missing)**: Run suite when `D:\AI\output` does not exist; verify auto-created.
- **T2.F15.02 (Permission Denied / Read-Only File Protection)**: Handle read-only test fixture without crashing suite.
- **T2.F15.03 (Assertion Failure Granularity)**: Verify failed assertion prints informative diagnostic message with variable values.
- **T2.F15.04 (Subprocess Test Isolation)**: Ensure test suite does not leave lingering background python processes.
- **T2.F15.05 (Zero Dependency on External Network)**: Run entire suite offline; verify zero network calls or hangs.

---

## 5. Tier 3: Cross-Feature Combinations (Pairwise Interactions)

| Test ID | Feature Pair | Interaction Scenario | Verification Criteria |
|---|---|---|---|
| **T3.01** | F07 (Excel) + F10 (Selector) + F09 (Charts) | End-to-end data pipeline from Excel upload through series extraction, automatic type inference (Column vs Line), to native chart generation. | Native chart has matching series values, correct chart type, and `shape.has_chart == True`. |
| **T3.02** | F08 (MD Table) + F04 (Auto-fit) + F03 (Notes) | LLM outputs markdown comparison table with long explanatory analysis (>30 chars). | Table converted to chart/table slide; analysis truncated to <=30 chars on slide; full text stashed in speaker notes. |
| **T3.03** | F01 (7 Layouts) + F02 (Footer) + F05 (Validation) | Build complete deck with all 7 layouts; execute `validate_ppt_before_save`. | Page count is 7; cover and ending lack footers; content slides have `第 X 页`; report text returns 0 overflow. |
| **T3.04** | F05 (Validation) + F12 (Open API) + F13 (Card) | Engine completes PPT generation and pre-export validation; outputs artifact payload to frontend; user clicks Open. | Card displays validation summary string; `/api/file/open` receives path and successfully triggers `os.startfile`. |
| **T3.05** | F06 (Repetition) + F08 (MD Table) + F11 (Chart Slide) | LLM streams wide markdown table with complex divider syntax (`|---|---|`); streams into chart generator. | Stream adapter does NOT abort stream early; table parses cleanly; chart slide generated. |
| **T3.06** | F12 (Open API) + F13 (Card) | User clicks `[📁 打开所在目录]` on frontend delivery card. | Request passes `is_dir=True`; backend invokes `os.startfile` on folder path; Explorer opens folder. |
| **T3.07** | F09 (Charts) + F10 (Selector) + F03 (Notes) | User specifies `[图表: 饼图]` with 10 categories. | Selector forces pie type, groups top 7 + "其他", stores full 10-item data table in speaker notes. |
| **T3.08** | F04 (Auto-fit) + F05 (Validation) + F01 (Layouts) | Input slide contains 8 bullets with extreme lengths (40-60 chars). | Canvas displays top 5 bullets <=30 chars; bullets 6-8 and long tails moved to notes; `validate_ppt_before_save` reports 0 overflow. |
| **T3.09** | F05 (Validation) + F01 (Layouts) | Input deck contains an accidental blank slide between Catalog and Section Transition. | `validate_ppt_before_save` detects blank slide; removes it via `drop_rel` and `_sldIdLst` deletion; total slide count reduced by 1. |
| **T3.10** | F14 (No Popups) + F12 (Open API) | User attempts to open a non-existent or corrupted file; API returns HTTP 404. | Frontend captures error and renders in-app toast/modal; NO native browser alert popup exposing `127.0.0.1:7860`. |
| **T3.11** | F07 (Excel) + F01 (Layouts) + F02 (Footer) | Excel file contains multiple sheets (Reconciliation, Transfers, Price List). | Engine builds multi-slide deck with Chart slide and Table slide; footers reference respective sheet sources. |
| **T3.12** | F08 (MD Table) + F09 (Charts) + F05 (Validation) | Markdown table contains invalid data (all zeros or non-numeric strings). | Chart builder detects invalid data; falls back to Table slide; validation passes without crashing on missing chart shape. |

---

## 6. Tier 4: Real-World Enterprise Application Scenarios

### Scenario 1: Material Procurement Reconciliation to High-Level PPT Report
- **Workflow**:
  1. Upload `对账清单.xlsx` and `调拨汇总样表.xlsx` to workspace.
  2. `calc_engine.py` executes precomputation, calculating total procurement quantity, transfer quantity, and variances.
  3. `extract_chart_series` extracts Top 8 materials by volume and creates 2-series comparison object.
  4. Core engine constructs 7-slide presentation:
     - Slide 1: Cover ("物资调拨与采购对账专项分析汇报")
     - Slide 2: Agenda
     - Slide 3: Transition ("第一部分：采购与调拨执行对比")
     - Slide 4: Native Chart Slide (Left Column Chart: Plan vs Transfer; Right Card: 3 key quantitative findings)
     - Slide 5: Standard Table Slide (Detailed Material Variance Matrix)
     - Slide 6: Conclusion (Dual-column: Root Causes vs Strategic Actions)
     - Slide 7: Ending (Q&A)
  5. Pre-export validation verifies 7 pages, 1 native chart, 0 overflow.
  6. Frontend mounts delivery card with self-check summary; clicking `[📂 直接用本机软件打开]` triggers PowerPoint.

### Scenario 2: Quarterly TCO Supplier Comparison & Trend Briefing
- **Workflow**:
  1. User asks model in `procure` mode to analyze 4 suppliers across Q1-Q4.
  2. Model outputs Markdown comparison table with time columns (`Q1 2026`, `Q2 2026`, `Q3 2026`, `Q4 2026`).
  3. `extract_series_from_table` automatically identifies temporal categories and chooses `line` chart.
  4. Presentation generated with Native Line Chart with markers, top legend, and formatted data labels.
  5. Speaker notes populated with TCO model calculation formula and supplier background context.
  6. Validation verifies line chart integrity and generates standardized export report.

### Scenario 3: Emergency Supply Chain Disruption & Risk Action Plan
- **Workflow**:
  1. Model generates rapid response brief containing dense text: 7 long bullet points per section with complex justifications (>50 chars).
  2. Engine applies strict bullet simplification: top 4 bullets formatted to "核心结论 + 关键数字" (<=30 chars); remaining 3 bullets and verbose text routed into speaker notes.
  3. Title font dynamically scaled from 26pt down to 18pt to avoid line wrapping.
  4. Blank placeholder slides purged.
  5. Validation passes with 0 overflow count.

### Scenario 4: Category Expenditure Structure & Budget Distribution Analysis
- **Workflow**:
  1. User submits expenditure table by department (Steel, Cement, Aggregates, Equipment, Labor).
  2. Prompt directive specifies `[图表: 饼图]`.
  3. Engine builds Native Pie Chart using enterprise color palette, ensuring no value axis exception is raised.
  4. Percentage data labels rendered inside slices.
  5. Right conclusion card highlights top category expenditure and proportion.
  6. Delivery card rendered under chat bubble.

### Scenario 5: Full 7-Layout Executive Annual Summary Generation & Folder Reveal
- **Workflow**:
  1. System generates comprehensive 7-layout annual review deck.
  2. Footer correctly configured on slides 2-6 (left: source, right: `第 X 页`); omitted on slides 1 and 7.
  3. Validation confirms all 7 layouts render correctly.
  4. User clicks `[📁 打开所在目录]` on file card.
  5. `/api/file/open` receives `{is_dir: true, path: "D:\\AI\\output\\..."}` and invokes `os.startfile("D:\\AI\\output")` opening Windows Explorer.

---

## 7. Test Execution & Pass/Fail Criteria

### Commands
```powershell
# Execute full test suite
D:\AI\runtime\python\python.exe D:\AI\test_suite.py
```

### Exit Criteria (100% Pass)
1. Process exit code must be `0`.
2. All 15 Feature Verification Chapters must pass without assertion failures.
3. Zero unhandled exceptions.
4. Output report string format strictly conforms to:
   `《PPT 导出自检报告（共 X 页，含 X 张原生图表，0 处溢出）》`
