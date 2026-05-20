import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-區塊循環完全體", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 檔案讀取與設定 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r; break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        c0, c1, c2 = str(row.iloc[0]), str(row.iloc[1]), str(row.iloc[2])
        if any(k in f"{c0}{c1}{c2}" for k in ["每日人力", "總人數", "統計"]): continue
        
        # 簡易人員識別
        is_valid = any(x in c0 or x in c1 for x in ["半職", "1", "2", "3", "4", "5"])
        if not is_valid: continue
        
        name = c2 if c2 != "nan" else c1
        configs[name] = {
            "pure_id": name,
            "perm": "DEN",
            "last_day": "off",
            "streak": 0,
            "is_part_time": "半職" in c0 or "半職" in c1
        }
    return configs

# --- 2. 區塊循環演算法核心 ---
def generate_staff_blocks(num_days, perm, start_shift, start_streak):
    seq = []
    curr_streak = start_streak
    last_s = start_shift
    choices = [s for s in ["D", "E", "N"] if s in perm]
    
    for _ in range(num_days):
        # 若連班過長強制休息
        if curr_streak >= 5:
            seq.append("off")
            curr_streak = 0
            last_s = "off"
        else:
            # 隨機選擇或維持連班 (提高排班連貫性)
            if last_s in choices and random.random() < 0.8:
                s = last_s
            else:
                s = random.choice(choices) if choices else "off"
            seq.append(s)
            curr_streak = (curr_streak + 1) if s != "off" else 0
            last_s = s
    return seq

# --- 3. UI 介面 ---
st.title("🏥 2F 護理排班系統 (區塊循環完全體)")

with st.sidebar:
    start_date = st.date_input("開始日期")
    end_date = st.date_input("結束日期")
    file_a = st.file_uploader("上傳班表 (檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("上傳預班表 (檔案 B)", type=["xlsx"])

if file_a and file_b:
    num_days = (end_date - start_date).days + 1
    staff_configs = get_staff_configs(file_a)
    display_names = list(staff_configs.keys())
    full_time_names = [n for n in display_names if not staff_configs[n]["is_part_time"]]
    part_time_names = [n for n in display_names if staff_configs[n]["is_part_time"]]

    if st.button("🚀 啟動自動排班", type="primary"):
        success = False
        final_res = {}
        
        # 進行嘗試
        for attempt in range(2000):
            res = {n: [""] * num_days for n in display_names}
            
            # 產生初始循環區塊
            for n in full_time_names:
                res[n] = generate_staff_blocks(num_days, "DEN", "off", 0)
            for pt in part_time_names:
                res[pt] = ["D"] * num_days # 簡易範例
            
            # 衝突修復 (人力填補)
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                for n in display_names:
                    if res[n][d] in target: target[res[n][d]] -= 1
                
                for s, needed in target.items():
                    if needed > 0:
                        cands = [n for n in full_time_names if res[n][d] == "off"]
                        random.shuffle(cands)
                        for c in cands[:needed]: res[c][d] = s
            
            # 合法性檢查
            if all(res[n].count("off") >= 6 for n in full_time_names):
                final_res = res
                success = True
                break
        
        if success:
            st.success("🎉 排班完成！")
            final_df = pd.DataFrame(final_res).T
            st.dataframe(final_df)
            
            # 下載功能
            out = BytesIO()
            final_df.to_excel(out)
            st.download_button("📥 下載完整班表", data=out.getvalue(), file_name="Schedule.xlsx")
        else:
            st.error("⚠️ 無法排班，請調整預班條件。")
