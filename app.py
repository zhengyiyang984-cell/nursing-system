import streamlit as st
import pandas as pd
import random
from io import BytesIO

st.set_page_config(page_title="2F 護理排班系統-手動穩定版", layout="wide")

st.title("🏥 2F 護理排班系統 (手動穩定版)")

# --- 側邊欄設定 ---
with st.sidebar:
    st.header("⚙️ 排班設定")
    num_days = st.slider("本月天數", 28, 31, 30)
    num_staff = st.number_input("護理人員總數", 1, 30, 15)

# --- 核心表格區 ---
st.subheader("📅 1. 編輯人員與預約假 (R=休假, D/E/N=固定班)")
st.info("💡 提示：你可以直接從 Excel 複製人名，點擊下方表格的第一格後「貼上」即可。")

dates = [f"{i+1}日" for i in range(num_days)]
# 建立一個全空的表格，讓使用者掌握最高權限
if 'manual_df' not in st.session_state or len(st.session_state.manual_df) != num_staff:
    st.session_state.manual_df = pd.DataFrame(
        "", 
        index=[f"人員 {i+1}" for i in range(num_staff)], 
        columns=dates
    )

# 讓使用者直接在網頁上編輯名字與假別
edited_df = st.data_editor(st.session_state.manual_df, use_container_width=True)

# --- 權限設定 ---
st.subheader("⚙️ 2. 核對權限 (預設皆為 DEN)")
names = edited_df.index.tolist()
final_perms = {}
cols = st.columns(4)
for i, name in enumerate(names):
    with cols[i % 4]:
        final_perms[name] = st.text_input(f"{name} 權限", value="DEN", key=f"p_{i}")

# --- 執行排班 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        
        # 1. 抓取預約
        for n in names:
            val = str(edited_df.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R":
                res[n][d] = "R"; pool.remove(n)
        
        # 2. 補滿人力
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in final_perms[n]]
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop()
                    res[staff][d] = shift; pool.remove(staff)
        for n in pool: res[n][d] = "off"

    st.success("🎉 排班完成！")
    final_res = pd.DataFrame(res).T
    st.dataframe(final_res, use_container_width=True)
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        final_res.to_excel(writer)
    st.download_button("📥 下載 Excel", out.getvalue(), "Schedule.xlsx")
