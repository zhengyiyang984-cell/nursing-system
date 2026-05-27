import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(page_title="2F 智慧排班測試系統", layout="wide")

# --- 1. 定義人員與預設 ---
STAFF_LIST = ["郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", "汪家容", "林欣儀", "林怡薇"]

# --- 2. 介面 ---
st.title("🏥 2F 智慧排班系統 (測試版)")
st.info("您目前尚未上傳檔案，系統將為您產生一張 30 天的空白班表供測試。")

# --- 3. 自動產生空白班表 ---
if 'schedule_df' not in st.session_state:
    # 產生 30 天的列，人員為行
    days = [f"{i+1}日" for i in range(30)]
    st.session_state.schedule_df = pd.DataFrame("", index=STAFF_LIST, columns=days)

st.subheader("📝 本月排班編輯")
edited_df = st.data_editor(st.session_state.schedule_df, use_container_width=True)

# --- 4. 自動補班邏輯 ---
if st.button("🚀 執行智慧自動排班"):
    # 簡單自動補位邏輯：如果該格是空的，暫時隨機補入 D/E/N (僅供測試)
    filled_df = edited_df.copy()
    for col in filled_df.columns:
        for row in filled_df.index:
            if filled_df.loc[row, col] == "":
                # 這裡會是您的智慧權重引擎
                filled_df.loc[row, col] = np.random.choice(['D', 'E', 'N', 'off'])
    
    st.success("✅ 測試版自動排班完成！")
    st.dataframe(filled_df, use_container_width=True)
    
    # 下載功能
    csv = filled_df.to_csv().encode('utf-8')
    st.download_button("📥 下載測試班表", csv, "Test_Schedule.csv")
