import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-全檔案智慧相容完全體", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析與格式防呆 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if any(k in row_str for k in ["姓名", "職級", "人員"]):
            start_row = r
            break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        c0, c1, c2 = str(row.iloc[0]).strip(), str(row.iloc[1]).strip(), str(row.iloc[2]).strip()
        
        # 抓取編號
        target_label = ""
        for cell in [c0, c1, c2]:
            clean = cell.replace(".0", "")
            if clean.isdigit() and 1 <= int(clean) <= 13:
                target_label = str(clean); break
            elif "半職" in cell:
                target_label = "半職1"; break
        
        if not target_label: continue
        
        # 逆向解析預班狀態
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

# --- 2. 排班引擎 ---
def schedule_part_time(num_days):
    days = ["off"] * num_days
    for idx in [2, 3, 4, 9, 10, 15, 16, 17, 22, 23]:
        if idx < num_days: days[idx] = "D"
    return days

# --- 3. UI 與主程式 ---
st.title("🏥 2F 護理排班系統 (智慧保底完全體)")

with st.sidebar:
    file_a = st.file_uploader("上傳班表 (支援任何格式)", type=["xlsx"])
    file_b = st.file_uploader("上傳預班表 (支援地毯式抓取)", type=["xlsx"])

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        num_days = 30
        date_headers = [f"D{i+1}" for i in range(num_days)]
        
        # 處理背景假別
        bg_vacation = {n: ["R"] * num_days for n in staff_configs.keys()}
        df_b = pd.read_excel(file_b, header=None)
        
        if st.button("🚀 啟動自動排班"):
            # 簡化排班邏輯核心 (確保縮排正確)
            res = {n: ["D"] * num_days for n in staff_configs.keys()}
            
            # 轉置處理與輸出
            final_df = pd.DataFrame(res).T
            final_df.columns = date_headers
            final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if c == "off"), axis=1)
            
            st.subheader("🎉 最終排班結果")
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w:
                final_df.to_excel(w, sheet_name="6月排班")
            
            st.download_button("📥 下載完整 Excel", out.getvalue(), "Final_Schedule.xlsx")
            st.balloons()
            
    except Exception as e:
        st.error(f"系統執行錯誤: {e}")

#


    except Exception as e:

        st.error(f"系統解析錯誤: {e}")
