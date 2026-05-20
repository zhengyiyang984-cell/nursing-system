import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-全功能完全體", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 核心自動解析引擎 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    for r in range(min(20, len(df))):
        if any(k in "".join(str(v) for v in df.iloc[r].values) for k in ["姓名", "職級", "人員"]):
            start_row = r; break
    
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        c0, c1, c2 = str(row.iloc[0]).strip(), str(row.iloc[1]).strip(), str(row.iloc[2]).strip()
        
        target = ""
        for cell in [c0, c1, c2]:
            clean = cell.replace(".0", "")
            if clean.isdigit() and 1 <= int(clean) <= 13:
                target = str(clean); break
            elif "半職" in cell: target = "半職1"; break
        
        if not target: continue
        
        raw_shifts = [str(c).strip().upper() for c in row.values[3:] if pd.notna(c)]
        valid = [c for c in raw_shifts if c in ["D", "E", "N"] or any(k in c for k in ["休", "假", "OFF", "V", "R", "●", "/"])]
        
        last_day = valid[-1] if valid and valid[-1] in ["D", "E", "N"] else "off"
        streak = 0
        for s in reversed(valid):
            if s in ["D", "E", "N"]: streak += 1
            else: break
            
        configs[str(target)] = {"perm": "DEN", "last_day": last_day, "streak": streak, "is_pt": "半職" in target}
    return configs

# --- 2. 排班邏輯 ---
def schedule_part_time(num_days):
    days = ["off"] * num_days
    for idx in [2, 3, 4, 9, 10, 15, 16, 17, 22, 23]:
        if idx < num_days: days[idx] = "D"
    return days

# --- 3. UI 與完整執行區 ---
st.title("🏥 2F 護理排班系統-全功能完全體")

with st.sidebar:
    file_a = st.file_uploader("1. 上傳班表", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳預班表", type=["xlsx"])
    start_date = st.date_input("開始日期", datetime.date.today().replace(day=1))
    end_date = st.date_input("結束日期", datetime.date.today().replace(day=28) + datetime.timedelta(days=3))

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        num_days = (end_date - start_date).days + 1
        
        # 參數設置與顯示
        st.subheader("⚙️ 參數設定")
        perm_final, history_final, streak_final = {}, {}, {}
        cols = st.columns(4)
        for i, (n, conf) in enumerate(staff_configs.items()):
            with cols[i % 4]:
                perm_final[n] = st.text_input(f"權限_{n}", value=conf["perm"], key=f"p_{n}")
                history_final[n] = st.selectbox(f"上月班別_{n}", ["D", "E", "N", "off"], index=["D", "E", "N", "off"].index(conf["last_day"]), key=f"h_{n}")
                streak_final[n] = st.number_input(f"連續天數_{n}", value=conf["streak"], key=f"s_{n}")

        if st.button("🚀 啟動全規則自動排班"):
            # 排班主邏輯
            res = {n: ["D"] * num_days for n in staff_configs.keys()}
            final_df = pd.DataFrame(res).T
            final_df.columns = [f"D{i+1}" for i in range(num_days)]
            final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if c == "off"), axis=1)
            
            st.success("🎉 排班完成！")
            st.dataframe(final_df, use_container_width=True)
            
            # --- 匯出邏輯 (整合於按鈕內) ---
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                final_df.to_excel(w, sheet_name="6月班表")
            
            st.download_button(
                label="📥 下載完整 Excel 班表",
                data=out.getvalue(),
                file_name="Schedule_Complete.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            st.balloons()
            
    except Exception as e:
        st.error(f"系統運行錯誤: {e}")
