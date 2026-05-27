import streamlit as st
import pandas as pd
import random
from io import BytesIO

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 14 人名單
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇", "林郁珊"
]

st.title("🏥 2F 護理排班系統 (Excel 專用版)")

file_b = st.file_uploader("請上傳【預排休表.xlsx】", type=["xlsx"])

if file_b:
    try:
        # 使用 read_excel 讀取 .xlsx
        # header=0 代表第一列是標題，這通常是 Excel 的標準格式
        df = pd.read_excel(file_b, header=0)
        
        # 建立預排休地圖
        vacation_map = {}
        for _, row in df.iterrows():
            name = str(row.iloc[0]).strip()
            # 讀取該行從第 2 欄之後的所有日期 (共 30 天)
            vacation_map[name] = [str(val).upper() == "R" for val in row.iloc[1:31]]

        if st.button("🚀 啟動 14 人排班", type="primary", use_container_width=True):
            res = {n: ["off"] * 30 for n in CORE_STAFF_NAMES}
            
            for d in range(30):
                # 1. 優先處理預排休
                for n in CORE_STAFF_NAMES:
                    if n in vacation_map and len(vacation_map[n]) > d and vacation_map[n][d]:
                        res[n][d] = "off"
                
                # 2. 郭珍君 (半職) 規則
                if d < 10:
                    res["郭珍君"][d] = "D"
                elif res["郭珍君"][d] != "off":
                    res["郭珍君"][d] = "off"
                
                # 3. 準備上班的人員池 (排除郭珍君與已休假者)
                pool = [n for n in CORE_STAFF_NAMES if n != "郭珍君" and res[n][d] != "off"]
                random.shuffle(pool)
                
                # 4. 填入 4/3/2 人力
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
        st.error(f"讀取 Excel 失敗，請確認你的 Excel 第一列是否包含姓名: {e}")
