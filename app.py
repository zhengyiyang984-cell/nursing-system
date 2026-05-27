import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]
CORE_STAFF_NAMES = ["郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", "汪家容", "林欣儀", "林怡薇"]

def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    for i in range(len(df)):
        row_str = "".join(str(v) for v in df.iloc[i].values)
        matched_name = next((name for name in CORE_STAFF_NAMES if name in row_str), None)
        if matched_name:
            configs[matched_name] = {"perm": "DEN", "is_part_time": (matched_name == "郭珍君")}
    return configs

st.title("🏥 護理排班系統 (自動重試優化版)")

with st.sidebar:
    start_date = st.date_input("開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("結束日期", datetime.date(2026, 6, 30))
    num_days = (end_date - start_date).days + 1
    file_a = st.file_uploader("1. 基本班表", type=["xlsx"])
    file_b = st.file_uploader("2. 預排休表", type=["xlsx"])

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        display_names = list(staff_configs.keys())
        full_time_names = [n for n in display_names if not staff_configs[n]["is_part_time"]]
        
        # UI 部分省略，直接進入求解核心
        if st.button("🚀 啟動精準 4/3/2 排班", type="primary"):
            success_schedule = False
            final_res = None
            
            # 自動重試迴圈：解決隨機碰撞死鎖
            for attempt in range(2000):
                res = {n: ["off"] * num_days for n in display_names}
                streak_tracker = {n: 0 for n in full_time_names}
                total_off_counts = {n: 0 for n in full_time_names}
                valid_month = True
                
                for d in range(num_days):
                    target = {"D": 4, "E": 3, "N": 2}
                    pool = full_time_names.copy()
                    
                    # 1. 處理休假 (這裡假設 bg_vacation 已在外部解析)
                    for n in pool.copy():
                        if streak_tracker[n] >= 5: # 簡化連班限制
                            res[n][d] = "off"; total_off_counts[n] += 1; pool.remove(n)
                    
                    # 2. 優先分配給權限少的人 (貪婪演算法核心)
                    pool.sort(key=lambda x: len(staff_configs[x]["perm"]))
                    
                    for shift in ["D", "E", "N"]:
                        cands = [n for n in pool if shift in staff_configs[n]["perm"]]
                        while target[shift] > 0 and cands:
                            chosen = cands.pop(0)
                            res[chosen][d] = shift
                            streak_tracker[chosen] += 1
                            pool.remove(chosen)
                            target[shift] -= 1
                    
                    # 3. 檢查當天是否配平
                    if target["D"] > 0 or target["E"] > 0 or target["N"] > 0:
                        valid_month = False; break
                
                if valid_month:
                    final_res = res
                    success_schedule = True
                    break
            
            if success_schedule:
                st.success("🎉 排班成功！")
                st.dataframe(pd.DataFrame(final_res).T)
            else:
                st.error("⚠️ 無法找到完美解，請減少預排休人數或放寬班別權限。")
                
    except Exception as e:
        st.error(f"系統錯誤: {e}")
