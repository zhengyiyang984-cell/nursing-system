import streamlit as st
import pandas as pd
from io import BytesIO
import datetime

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 14 人完整名單
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇", "林郁珊"
]

st.title("🏥 2F 護理排班系統 (完整整合版)")

# --- 側邊欄：上傳與設定 ---
with st.sidebar:
    st.header("⚙️ 設定區")
    start_date = st.date_input("排班開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("排班結束日期", datetime.date(2026, 6, 30))
    file_a = st.file_uploader("1. 上傳【基本班表】(xlsx)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】(xlsx)", type=["xlsx"])

# --- 校對介面 ---
if file_a and file_b:
    st.subheader("⚙️ 核對權限與銜接狀態 (手動設定)")
    cols = st.columns(4)
    perm_final, history_final, cont_days_final = {}, {}, {}
    
    for i, n in enumerate(CORE_STAFF_NAMES):
        with cols[i % 4]:
            with st.expander(f"👤 {n}"):
                perm_final[n] = st.text_input("權限", value="DEN", key=f"p_{n}").upper()
                history_final[n] = st.selectbox("上月最後班別", ["D", "E", "N", "off"], index=3, key=f"h_{n}")
                cont_days_final[n] = st.number_input("上月已連續天數", 0, 6, 0, key=f"c_{n}")

    # --- 排班運算 ---
    if st.button("🚀 啟動 14 人完整排班", type="primary", use_container_width=True):
        num_days = (end_date - start_date).days + 1
        
        # 讀取預排休 (讀取 Excel)
        df_vac = pd.read_excel(file_b, header=0)
        vacation_map = {}
        for _, row in df_vac.iterrows():
            name = str(row.iloc[0]).strip()
            vacation_map[name] = [str(val).upper() == "R" for val in row.iloc[1:num_days+1]]

        res = {n: ["off"] * num_days for n in CORE_STAFF_NAMES}
        streak = {n: int(cont_days_final[n]) for n in CORE_STAFF_NAMES}
        
        for d in range(num_days):
            # 1. 預排休覆蓋
            for n in CORE_STAFF_NAMES:
                if n in vacation_map and len(vacation_map[n]) > d and vacation_map[n][d]:
                    res[n][d] = "off"
            
            # 2. 郭珍君 (半職) 規則
            if d < 10:
                res["郭珍君"][d] = "D"
            elif res["郭珍君"][d] != "off":
                res["郭珍君"][d] = "off"
            
            # 3. 準備上班池
            pool = [n for n in CORE_STAFF_NAMES if n != "郭珍君" and res[n][d] != "off"]
            random.shuffle(pool)
            
            # 4. 4/3/2 排班邏輯
            targets = {"D": 4, "E": 3, "N": 2}
            for shift, count in targets.items():
                for _ in range(count):
                    # 篩選有權限的人
                    candidates = [n for n in pool if shift in perm_final[n]]
                    if candidates:
                        chosen = candidates[0]
                        res[chosen][d] = shift
                        pool.remove(chosen)
                        streak[chosen] += 1
            
            # 5. 其餘補休
            for n in pool:
                res[n][d] = "off"

        # 輸出結果
        final_df = pd.DataFrame(res).T
        st.success("✅ 排班表產生成功！")
        st.dataframe(final_df, use_container_width=True)
        
        out = BytesIO()
        final_df.to_excel(out)
        st.download_button("📥 下載 Excel", data=out.getvalue(), file_name="2F_June_Schedule.xlsx")
