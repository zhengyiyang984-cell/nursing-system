import streamlit as st
import pandas as pd
import random
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# --- 核心邏輯：姓名導向解析 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    # 自動尋找包含「姓名」的標題行
    for r in range(min(15, len(df))):
        if "姓名" in "".join(str(v) for v in df.iloc[r].values):
            start_row = r; break

    headers = df.iloc[start_row].tolist()
    hist_idx = next((i for i, h in enumerate(headers) if "系統接續_最後班別" in str(h)), -1)
    streak_idx = next((i for i, h in enumerate(headers) if "系統接續_連續天數" in str(h)), -1)

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        # 直接抓取第三欄 (C欄) 姓名
        staff_name = str(row.iloc[2]).strip()
        if not staff_name or "nan" in staff_name or any(k in staff_name for k in ["姓名", "合計"]): continue
        
        last_day = str(row.iloc[hist_idx]).strip() if hist_idx != -1 else "off"
        streak = int(float(row.iloc[streak_idx])) if streak_idx != -1 and pd.notna(row.iloc[streak_idx]) else 0

        configs[staff_name] = {
            "perm": ["D", "E", "N"], 
            "last_day": last_day if last_day in ["D", "E", "N", "off", "v", "R"] else "off",
            "streak": streak,
            "is_part_time": "半職" in staff_name
        }
    return configs

# --- 衝突預警 ---
def check_conflicts(display_names, bg_vacation, num_days):
    issues = []
    for d in range(num_days):
        d_count = sum(1 for n in display_names if bg_vacation[n][d] == "D")
        if d_count < 2: issues.append(f"第 {d+1} 天白班人力僅 {d_count} 人，建議確認。")
    return issues

# --- UI 介面 ---
st.title("🏥 護理排班系統 (姓名姓名制)")

with st.sidebar:
    start_date = st.date_input("排班開始日期", datetime.date.today().replace(day=1))
    end_date = st.date_input("排班結束日期", datetime.date.today().replace(day=28))
    num_days = (end_date - start_date).days + 1
    file_a = st.file_uploader("1. 上傳【班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】", type=["xlsx"])

if file_a and file_b:
    staff_configs = get_staff_configs(file_a)
    display_names = list(staff_configs.keys())
    
    st.subheader("⚙️ 人員權限與銜接設定")
    perm_final, history_final, cont_days_final = {}, {}, {}
    cols = st.columns(4)
    for i, name in enumerate(display_names):
        with cols[i % 4]:
            with st.container(border=True):
                st.markdown(f"**人員：{name}**")
                # 【優化：Multiselect 防止輸入錯誤】
                perm_final[name] = st.multiselect("可排班別", ["D", "E", "N"], default=["D", "E", "N"], key=f"p_{name}")
                history_final[name] = st.selectbox("上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                  index=["D", "E", "N", "off", "v", "R"].index(staff_configs[name]["last_day"]),
                                                  key=f"h_{name}")
                cont_days_final[name] = st.number_input("連續天數", 0, 7, int(staff_configs[name]["streak"]), key=f"c_{name}")

    if st.button("🚀 啟動自動排班", type="primary"):
        # 【優化：執行前檢查】
        # 這裡請放入您原本的 bg_vacation 解析邏輯
        # issues = check_conflicts(display_names, bg_vacation, num_days)
        # if issues:
        #    for issue in issues: st.warning(issue)
        #    if not st.checkbox("人力緊張，強制排班？"): st.stop()
        
        # --- 原有排班迴圈 ---
        # 在迴圈內的分配邏輯加入加權：
        # pool.sort(key=lambda n: (7 - total_off_counts.get(n, 0)), reverse=True)
        
        st.success("🎉 排班完成！")
