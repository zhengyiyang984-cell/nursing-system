from io import BytesIO
import pandas as pd
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
from openpyxl.utils import get_column_letter
from config import PERMISSION_CELL_COLOR, PROBLEM_CELL_COLOR, PROBLEM_FONT_COLOR


def export_workbook(
    schedule_df,
    manpower_df,
    person_df,
    issues_df,
    leave_df=None,
    leave_summary_df=None,
    problem_cells=None,
    problem_names=None,
):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, sheet_name="班表", index=False)
        manpower_df.to_excel(writer, sheet_name="每日人力", index=False)
        person_df.to_excel(writer, sheet_name="個人統計", index=False)

        # 獨立的休假天數彙整工作表，方便主管/護理長直接查看。
        if leave_summary_df is not None and not leave_summary_df.empty:
            leave_summary_df.to_excel(
                writer,
                sheet_name="休假天數彙整",
                index=False
            )

        issues_df.to_excel(writer, sheet_name="違規檢查", index=False)

        if leave_df is not None and not leave_df.empty:
            leave_df.to_excel(writer, sheet_name="請假紀錄", index=False)

        wb = writer.book
        for ws in wb.worksheets:
            style_sheet(ws)
        color_schedule_sheet(
            wb["班表"],
            problem_cells=problem_cells,
            problem_names=problem_names,
        )
    output.seek(0)
    return output.getvalue()


def style_sheet(ws):
    thin = Side(style="thin", color="D9D9D9")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border
            if cell.row == 1:
                cell.font = Font(bold=True)
                cell.fill = PatternFill("solid", fgColor="D9EAF7")
    ws.freeze_panes = "B2"
    for col in ws.columns:
        max_len = 8
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            value = "" if cell.value is None else str(cell.value)
            max_len = max(max_len, min(len(value) + 2, 24))
        ws.column_dimensions[col_letter].width = max_len


def color_schedule_sheet(ws, problem_cells=None, problem_names=None):
    """
    最終班表配色：
    - D/E/N/M/R/off/請假：正常狀況全部白底。
    - 班別權限：統一淺藍底。
    - 每日 D/E/N 人力實際值 != 最低需求：該人力統計格標紅。
    - Validator 指定的人員/日期問題：該班表格標紅。
    - 全月型人員問題：該人姓名格標紅。
    """
    problem_cells = set(problem_cells or [])
    problem_names = set(problem_names or [])

    no_fill = PatternFill(fill_type=None)
    permission_fill = PatternFill("solid", fgColor=PERMISSION_CELL_COLOR)
    problem_fill = PatternFill("solid", fgColor=PROBLEM_CELL_COLOR)

    # Pandas to_excel 預設會多輸出 index，所以用標題文字尋找真正欄位。
    headers = {}
    for cell in ws[1]:
        header = "" if cell.value is None else str(cell.value).strip()
        if header:
            headers[header] = cell.column

    name_col = headers.get("姓名")
    permission_col = headers.get("班別權限")

    # 清除資料區所有舊班別底色。
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.fill = no_fill
            cell.font = Font(
                name=cell.font.name,
                size=cell.font.size,
                bold=False,
                italic=cell.font.italic,
                color="000000",
            )

    # 建立「姓名 -> Excel 列號」索引。
    row_by_name = {}
    if name_col:
        for row_idx in range(2, ws.max_row + 1):
            name = "" if ws.cell(row_idx, name_col).value is None else str(
                ws.cell(row_idx, name_col).value
            ).strip()
            if name:
                row_by_name[name] = row_idx

    # 權限欄統一淺藍。
    if permission_col:
        for row_idx in range(2, ws.max_row + 1):
            cell = ws.cell(row=row_idx, column=permission_col)
            value = "" if cell.value is None else str(cell.value).strip()
            if value:
                cell.fill = permission_fill
                cell.font = Font(bold=True, color="000000")

    # -------------------------------------------------
    # 人力多/少：D人力/E人力/N人力的「實際/最低」若不同就標紅
    # -------------------------------------------------
    for row_name in ["D人力", "E人力", "N人力"]:
        row_idx = row_by_name.get(row_name)
        if not row_idx:
            continue

        for header, col_idx in headers.items():
            if header in ["姓名", "班別權限"]:
                continue

            value = ws.cell(row_idx, col_idx).value
            if value is None:
                continue

            text = str(value).strip()
            if "/" not in text:
                continue

            try:
                actual_text, required_text = text.split("/", 1)
                actual = int(actual_text.strip())
                required = int(required_text.strip())
            except Exception:
                continue

            if actual != required:
                cell = ws.cell(row_idx, col_idx)
                cell.fill = problem_fill
                cell.font = Font(bold=True, color=PROBLEM_FONT_COLOR)

    # -------------------------------------------------
    # Validator 的指定人員 + 日期問題
    # -------------------------------------------------
    for nurse, date_header in problem_cells:
        row_idx = row_by_name.get(str(nurse).strip())
        col_idx = headers.get(str(date_header).strip())

        if row_idx and col_idx:
            cell = ws.cell(row_idx, col_idx)
            cell.fill = problem_fill
            cell.font = Font(bold=True, color=PROBLEM_FONT_COLOR)

    # 全月型問題：沒有單一日期可標時，標紅姓名。
    if name_col:
        for nurse in problem_names:
            row_idx = row_by_name.get(str(nurse).strip())
            if row_idx:
                cell = ws.cell(row_idx, name_col)
                cell.fill = problem_fill
                cell.font = Font(bold=True, color=PROBLEM_FONT_COLOR)

