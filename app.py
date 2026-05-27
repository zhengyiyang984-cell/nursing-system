import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇", "林郁珊"
]

st.title("🏥 2F 護理排班系統 (精準對齊版)")

file_b = st.file_uploader("請上傳【預排休範本.csv】", type=["csv"])

if file_b:
    df = pd.read_csv(file_b)
    
    # 建立預排休地圖：確保日期 1-31 對齊
    vacation_map = {}
    for _, row in df.iterrows():
        name = str(row.iloc[1]).strip() # 姓名在第 2 欄 (index 1)
        # 日期從第 3 欄開始 (index 2)，抓取 30 天
        vacation_map[name] = [str(val).upper() == "R" for val in row.iloc[2:32]]

    if st.button("🚀 啟動精準排班", type="primary"):
        res = {n: ["off"] * 30 for n in CORE_STAFF_NAMES}
        
        for d in range(30):
            # 1. 優先標記預排休為 off
            for n in CORE_STAFF_NAMES:
                if n in vacation_map and len(vacation_map[n]) > d and vacation_map[n][d]:
                    res[n][d] = "off"
            
            # 2. 處理郭珍君 (半職邏輯)
            if res["郭珍君"][d] != "off":
                res["郭珍君"][d] = "D" if d < 10 else "off"
            
            # 3. 準備「可排班」的正職池 (排除郭珍君與已休假者)
            pool = [n for n in CORE_STAFF_NAMES if n != "郭珍君" and res[n][d] == "off"]
            random.shuffle(pool)
            
            # 4. 填入 4/3/2 人力 (精確分配)
            targets = {"D": 4, "E": 3, "N": 2}
            for shift, count in targets.items():
                for _ in range(count):
                    if pool:
                        chosen = pool.pop(0)
                        res[chosen][d] = shift
        
        # 顯示結果
        final_df = pd.DataFrame(res).T
        # 標題修正為 1-30
        final_df.columns = [f"{i+1}" for i in range(30)]
        st.dataframe(final_df, use_container_width=True)
        
        out = BytesIO()
        final_df.to_excel(out)
        st.download_button("📥 下載 Excel", out.getvalue(), "June_Schedule.xlsx")
