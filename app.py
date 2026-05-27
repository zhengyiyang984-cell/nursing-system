import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 【保留】get_staff_configs 完整解析邏輯 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r; break

    headers_row = df.iloc[start_row].tolist()
    hist_col_idx, streak_col_idx = -1, -1
    for idx, h in enumerate(headers_row):
        h_str = str(h).strip()
        if "系統接續_最後班別" in h_str: hist_col_idx = idx
        if "系統接續_連續天數" in h_str: streak_col_idx = idx

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        c0, c1, c2 = str(row.iloc[0]).strip(), str(row.iloc[1]).strip(), str(row.iloc[2]).strip()
        
        # 這裡保留了原本複雜的 ID 與 姓名解析
        target_label = next((val for val in [c0, c1, c2] if val.replace(".0", "").isdigit() and 1 <= int(val.replace(".0", "")) <= 13), "半職1")
        staff_name = next((val for val in [c2, c1, c0] if val and not val.replace(".0", "").isdigit() and "半職" not in val), target_label)
        
        # 【保留】銜接狀態讀取
        last_day = str(row.iloc[hist_col_idx]).strip() if hist_col_idx != -1 and hist_col_idx < len(row) else "off"
        loaded_streak = int(float(row.iloc[streak_col_idx])) if streak_col_idx != -1 and streak_col_idx < len(row) and pd.notna(row.iloc[streak_col_idx]) else 0

        configs[target_label] = {
            "pure_id": re.sub(r'[\s\u3000]', '', staff_name),
            "perm": "DEN", 
            "last_day": last_day if last_day in ["D", "E", "N", "off", "v", "R"] else "off",
            "streak": loaded_streak,
            "is_part_time": "半職" in target_label
        }
    return configs

# --- 【保留】原有功能函數 ---
def check_conflicts(display_names, bg_vacation, num_days):
    issues = []
    for d in range(num_days):
        d_count = sum(1 for n in display_names if bg_vacation[n][d] == "D")
        if d_count < 2: issues.append(f"第 {d+1} 天白班人力不足 (預排: {d_count} 人)")
    return issues

# ... (schedule_part_time 函數保持不變)

# --- UI 整合 ---
st.title("🏥 護理排班系統")

with st.sidebar:
    st.header("📂 檔案上傳與日期設定")
    today = datetime.date.today()
    start_date = st.date_input("排班開始日期", today.replace(day=1))
    end_date = st.date_input("排班結束日期", today.replace(day=28) + datetime.timedelta(days=3))
    
    # 【保留】動態天數計算
    if start_date <= end_date:
        date_objects = [start_date + datetime.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        num_days = len(date_objects)
    
    file_a = st.file_uploader("1. 上傳【班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】", type=["xlsx"])

if file_a and file_b and num_days > 0:
    staff_configs = get_staff_configs(file_a)
    display_names = list(staff_configs.keys())
    
    st.subheader("⚙️ 核對權限與銜接狀態")
    perm_final, history_final, cont_days_final = {}, {}, {}
    cols = st.columns(4)
    for i, n in enumerate(display_names):
        with cols[i % 4]:
            with st.container(border=True):
                st.markdown(f"**人員序號：{n}**")
                # 【優化】Multiselect 權限，保留原本銜接參數讀取
                perm_final[n] = st.multiselect("可排班別", ["D", "E", "N"], default=["D", "E", "N"], key=f"p_{n}")
                history_final[n] = st.selectbox("上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                key=f"h_{n}")
                cont_days_final[n] = st.number_input("連續天數", 0, 7, int(staff_configs[n]["streak"]), key=f"c_{n}")

    if st.button("🚀 啟動自動排班", type="primary"):
        # 執行原本的 1500 次嘗試迴圈與邏輯...
        # 記得在此處加入 pool.sort(key=lambda n: (7 - total_off_counts.get(n, 0)), reverse=True) 
        st.success("🎉 排班完成！")
