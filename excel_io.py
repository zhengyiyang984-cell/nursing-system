import pandas as pd
import re

def clean_id(val: any) -> str:
    """清理人員 ID，移除空白字元並處理半職標記。"""
    if pd.isna(val): return ""
    s = re.sub(r'[\s\n\r\t\u200b-\u200d\ufeff]', '', str(val)).split('.')[0]
    return '半職1' if '半職' in s else s

def get_staff_base_data(df: pd.DataFrame) -> dict:
    """從 Excel 資料中偵測人員權限與上月銜接狀態。"""
    staff_data = {}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid and (sid.isdigit() or '半職' in sid):
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            last_val = "off"
            for cell in reversed(row.values):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val}
    return staff_data

def get_vacation_import(df: pd.DataFrame, names: list, num_days: int) -> dict:
    """從預約表中匯入自訂假與固定班。"""
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 # 假設日期從第 4 欄開始
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R"]:
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]:
                        v_map[sid][d] = val
    return v_map
