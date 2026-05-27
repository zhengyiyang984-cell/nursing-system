import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# --- 核心數據 ---
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

st.title("🏥 2F 護理排班系統 (精準 4/3/2 核心恢復版)")

# --- 側邊欄 ---
with st.sidebar:
    start_date = st.date_input("開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("結束日期", datetime.date(2026, 6, 30))
    num_days = (end_date - start_date).days + 1
    file_a = st.file_uploader("1. 上傳【基本班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])

if file_a and file_b:
    staff_configs = get_staff_configs(file_a)
    display_names = list(staff_configs.keys())

    # --- 校對介面 ---
    st.subheader("⚙️ 核對權限與銜接狀態")
    history_final, perm_final, cont_days_final = {}, {}, {}
    cols = st.columns(4)
    for i, n in enumerate(display_names):
        with cols[i % 4]:
            with st.container(border=True):
                st.markdown(f"👤 **{n}**")
                perm_final[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}").upper()
                history_final[n] = st.selectbox(f"上個月最後班別", ["D", "E", "N", "off"], index=3, key=f"h_{n}")
                cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

    # --- 排班邏輯 ---
    if st.button("🚀 啟動精準 4/3/2 排班", type="primary", use_container_width=True):
        success_schedule = False
        final_res = {}
        
        # 進行 5000 次嘗試
        for attempt in range(5000):
            res = {n: ["off"] * num_days for n in display_names}
            streak = {n: int(cont_days_final[n]) for n in display_names}
            valid = True
            
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = display_names.copy()
                random.shuffle(pool)
                
                # 權限與連班處理
                for n in pool[:]:
                    if d > 0 and streak[n] >= 5:
                        res[n][d] = "off"; pool.remove(n)
                
                # 核心分配
                for shift in ["D", "E", "N"]:
                    cands = [n for n in pool if shift in perm_final[n]]
                    for n in cands:
                        if target[shift] > 0:
                            res[n][d] = shift
                            streak[n] += 1
                            pool.remove(n)
                            target[shift] -= 1
                
                if target["D"] > 0 or target["E"] > 0 or target["N"] > 0:
                    valid = False; break
            
            if valid:
                final_res = res
                success_schedule = True
                break
        
        if success_schedule:
            st.success("🎉 排班完成！")
            st.dataframe(pd.DataFrame(final_res).T)
        else:
            st.error("⚠️ 條件過於嚴苛，請嘗試放寬權限或減少預排休。")
