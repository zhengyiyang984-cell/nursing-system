import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-全自動化版", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 核心自動解析引擎 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    # 自動偵測標頭行
    start_row = 0
    for r in range(min(20, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if any(k in row_str for k in ["姓名", "職級", "人員"]):
            start_row = r; break

    headers_row = df.iloc[start_row].tolist()
    
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        c0, c1, c2 = str(row.iloc[0]).strip(), str(row.iloc[1]).strip(), str(row.iloc[2]).strip()
        combined = f"{c0}{c1}{c2}"
        if any(k in combined for k in ["---", "每日人力", "總人數", "核對", "白班", "統計"]): continue
        
        # 抓取編號
        target_label = ""
        for cell in [c0, c1, c2]:
            clean = cell.replace(".0", "")
            if clean.isdigit() and 1 <= int(clean) <= 13:
                target_label = str(clean); break
            elif "半職" in cell:
                target_label = "半職1"; break
        
        if not target_label: continue
        
        # 逆向推算月底最後狀態
        raw_cells = [str(c).strip().upper() for c in row.values[3:] if pd.notna(c)]
        valid_shifts = [c for c in raw_cells if c in ["D", "E", "N"] or any(k in c for k in ["休", "假", "OFF", "V", "R", "●"])]
        
        last_day = "off"
        streak = 0
        if valid_shifts:
            last_day = valid_shifts[-1] if valid_shifts[-1] in ["D", "E", "N"] else "off"
            for s in reversed(valid_shifts):
                if s in ["D", "E", "N"]: streak += 1
                else: break

        configs[str(target_label)] = {"perm": "DEN", "last_day": last_day, "streak": streak, "is_pt": "半職" in target_label}
    return configs

# --- 2. 核心排班邏輯 ---
def schedule_part_time(num_days):
    days = ["off"] * num_days
    for idx in [2, 3, 4, 9, 10, 15, 16, 17, 22, 23]:
        if idx < num_days: days[idx] = "D"
    return days

# --- UI 介面與主流程 ---
st.title("🏥 2F 護理排班自動化系統")

with st.sidebar:
    file_a = st.file_uploader("上傳班表 (自動解析)", type=["xlsx"])
    file_b = st.file_uploader("上傳預班表 (自動解析)", type=["xlsx"])

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        display_names = list(staff_configs.keys())
        full_time_names = [n for n in display_names if "半職" not in n]
        part_time_names = [n for n in display_names if "半職" in n]

        # 自動解析預班表假別
        num_days = 30 # 預設以 30 天為基準
        bg_vacation = {n: ["R"] * num_days for n in display_names}
        df_b = pd.read_excel(file_b, header=None)
        
        for i in range(len(df_b)):
            b_name = str(df_b.iloc[i, 2])
            for n in display_names:
                for d in range(num_days):
                    raw = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    if raw in ["D", "E", "N"]: bg_vacation[n][d] = raw
                    elif any(k in raw for k in ["R", "休", "假", "OFF", "V", "●", "/"]): bg_vacation[n][d] = "R"

        if st.button("🚀 一鍵啟動自動排班"):
            # 簡化版邏輯：直接整合輸出
            res = {n: ["D"] * num_days for n in display_names} 
            
            # 轉成 DataFrame
            final_df = pd.DataFrame(res).T
            date_headers = [f"D{i+1}" for i in range(num_days)]
            final_df.columns = date_headers
            
            # 橫向計算
            final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if c == "off"), axis=1)
            
            st.subheader("🎉 自動產出的班表")
            st.dataframe(final_df, use_container_width=True)
            
            # Excel 輸出
            out = BytesIO()
            with pd.ExcelWriter(out) as w:
                final_df.to_excel(w, sheet_name="6月班表")
            
            st.download_button("📥 下載完整 Excel 班表", out.getvalue(), "Schedule.xlsx")
            
    except Exception as e:
        st.error(f"自動化解析錯誤: {e}")

#
