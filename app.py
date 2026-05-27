import streamlit as st
import pandas as pd
import random
from io import BytesIO

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 根據你的 CSV 內容，精確設定 14 人名單
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇", "林郁珊"
]

st.title("🏥 2F 護理排班系統 (14 人完整版)")

file_b = st.file_uploader("請上傳【預排休範本.csv】", type=["csv"])

if file_b:
    try:
        # 讀取 CSV，跳過上方標題說明列
        df_b = pd.read_csv(file_b, header=0)
        
        # 建立預排休地圖
        vacation_map = {}
        for _, row in df_b.iterrows():
            name = str(row.iloc[0]).strip()
            # 這裡讀取該行後面的所有日期欄位 (假設從第 2 欄開始)
            vacation_map[name] = [str(val).upper() == "R" for val in row[1:]]

        if st.button("🚀 啟動 14 人排班", type="primary", use_container_width=True):
            res = {n: ["off"] * 30 for n in CORE_STAFF_NAMES}
            
            for d in range(30):
                # 1. 處理預排休 (優先級最高)
                for n in CORE_STAFF_NAMES:
                    if n in vacation_map and len(vacation_map[n]) > d and vacation_map[n][d]:
                        res[n][d] = "off"
                
                # 2. 郭珍君 (半職) 規則
                # 每月前 10 天優先分配白班
                if d < 10:
                    res["郭珍君"][d] = "D"
                elif res["郭珍君"][d] != "off": # 若無預排休則為 off
                    res["郭珍君"][d] = "off"
                
                # 3. 其他 13 人人力池
                pool = [n for n in CORE_STAFF_NAMES if n != "郭珍君" and res[n][d] != "off"]
                random.shuffle(pool)
                
                # 4. 填入 4/3/2 人力配比
                targets = {"D": 4, "E": 3, "N": 2}
                for shift, count in targets.items():
                    for _ in range(count):
                        if pool:
                            res[pool.pop(0)][d] = shift
                
                # 5. 未排到的人補為 off
                for n in pool:
                    res[n][d] = "off"
            
            st.success("✅ 14 人排班表已產生！")
            st.dataframe(pd.DataFrame(res).T, use_container_width=True)
            
    except Exception as e:
        st.error(f"讀取 CSV 時發生錯誤，請檢查檔案格式是否包含姓名欄位: {e}")
