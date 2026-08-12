from io import BytesIO
import pandas as pd
from openpyxl.styles import PatternFill, Alignment, Font, Border, Side
from openpyxl.utils import get_column_letter
from config import PERMISSION_CELL_COLOR


def export_workbook(schedule_df, manpower_df, person_df, issues_df, leave_df=None):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        schedule_df.to_excel(writer, sheet_name="班表")
        manpower_df.to_excel(writer, sheet_name="每日人力", index=False)
        person_df.to_excel(writer, sheet_name="個人統計", index=False)
        issues_df.to_excel(writer, sheet_name="違規檢查", index=False)
        if leave_df is not None and not leave_df.empty:
            leave_df.to_excel(writer, sheet_name="請假紀錄", index=False)

        wb = writer.book
        for ws in wb.worksheets:
            style_sheet(ws)
        color_schedule_sheet(wb["班表"])
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


def color_schedule_sheet(ws):
    """
    最終班表配色規則：
    1. D/E/N/M/R/off/請假種類全部不使用底色。
    2. 只有「班別權限」欄使用統一淺藍底色。
    """

    # 先清除資料區所有舊的班別底色。
    no_fill = PatternFill(fill_type=None)

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

    # 找「班別權限」欄，不依賴固定欄號。
    permission_col = None

    for cell in ws[1]:
        if str(cell.value).strip() == "班別權限":
            permission_col = cell.column
            break

    if permission_col is None:
        return

    permission_fill = PatternFill(
        "solid",
        fgColor=PERMISSION_CELL_COLOR
    )

    for row_idx in range(2, ws.max_row + 1):
        cell = ws.cell(row=row_idx, column=permission_col)

        # 人力統計列等沒有權限內容的列不著色。
        value = "" if cell.value is None else str(cell.value).strip()

        if value:
            cell.fill = permission_fill
            cell.font = Font(
                bold=True,
                color="000000"
            )
