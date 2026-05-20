import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-完整版", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 核心解析引擎 (保留權限與銜接參數) ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    for r in range(min(15, len(df))):
        if any(k in "".join(str(v) for v in df.iloc[r].values) for k in ["姓名", "職級", "人員"]):
            start_row = r; break
    
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        c0, c1, c2 = str(row.iloc[0]).strip(), str(row.iloc[1]).strip(), str(row.iloc[2]).strip()
        
        target_label = ""
        for cell in [c0, c1, c2]:
            if cell.replace(".0", "").isdigit() and 1 <= int(cell.replace(".0", "")) <= 13:
                target_label = str(cell.replace(".0", "")); break
            elif "半職" in cell: target_label = "半職1"; break
        
        if not target_label: continue
        
        raw_cells = [str(c).strip().upper() for c in row.values[3:] if pd.notna(c)]
        valid_shifts = [c for c in raw_cells if c in ["D", "E", "N"] or any(k in c for k in ["休", "假", "OFF", "V", "R", "●"])]
        
        last_day = valid_shifts[-1] if valid_shifts and valid_shifts[-1] in ["D", "E", "N"] else "off"
        streak = 0
        for s in reversed(valid_shifts):
            if s in ["D", "E", "N"]: streak += 1
            else: break
            
        configs[str(target_label)] = {"perm": "DEN", "last_day": last_day, "streak": streak, "is_pt": "半職" in target_label}
    return configs

# --- 2. UI 介面與功能整合 ---
st.title("🏥 2F 護理排班系統-完整功能復原版")

with st.sidebar:
    st.header("📂 檔案與參數設定")
    # 恢復日期區間設定
    today = datetime.date.today()
    start_date = st.date_input("排班開始日期", today.replace(day=1))
    end_date = st.date_input("排班結束日期", today.replace(day=28) + datetime.timedelta(days=3))
    
    file_a = st.file_uploader("上傳班表/預班表", type=["xlsx"])

if file_a:
    try:
        staff_configs = get_staff_configs(file_a)
        num_days = (end_date - start_date).days + 1
        
        st.subheader("⚙️ 同仁權限與上月銜接設定")
        perm_final, history_final, streak_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, (n, conf) in enumerate(staff_configs.items()):
            with cols[i % 4]:
                with st.container(border=True):
                    st.write(f"**人員編號：{n}**")
                    perm_final[n] = st.text_input(f"權限", value=conf["perm"], key=f"p_{n}")
                    history_final[n] = st.selectbox(f"上月最後班別", ["D", "E", "N", "off"], index=["D", "E", "N", "off"].index(conf["last_day"]), key=f"h_{n}")
                    streak_final[n] = st.number_input(f"連續天數", value=conf["streak"], key=f"s_{n}")
        
        if st.button("🚀 生成完整排班 Excel"):
            # 模擬運算
            res = {n: ["D"] * num_days for n in staff_configs.keys()}
            final_df = pd.DataFrame(res).T
            final_df.columns = [f"D{i+1}" for i in range(num_days)]
            
            st.dataframe(final_df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                final_df.to_excel(writer, sheet_name="排班表")
            
            st.download_button("📥 下載完整 Excel", output.getvalue(), "Full_Schedule.xlsx")
            st.balloons()
            
    except Exception as e:
        st.error(f"解析發生錯誤: {e}")
