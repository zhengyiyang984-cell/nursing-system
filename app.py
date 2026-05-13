import streamlit as st
import pandas as pd
from io import BytesIO
import sys
import os

# 將專案根目錄加入路徑以利匯入
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))

from src.data_access.excel_io import get_staff_base_data, get_vacation_import
from src.logic.scheduler import run_scheduling

st.set_page_config(page_title="2F 護理排班系統-雙匯入整合版", layout="wide")

st.title("🏥 2F 護理排班系統 (三層架構版)")

# --- 1. 側邊欄：雙匯入區塊 ---
with st.sidebar:
    st.header("⚙️ 設定與匯入")
    num_days = st.slider("本月排班天數", 28, 31, 31)
    
    st.divider()
    st.subheader("📥 檔案 A：偵測權限與銜接")
    base_file = st.file_uploader("上傳上月班表", type=["xlsx", "csv"], key="base")
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 已載入 {len(staff_configs)} 人名單")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

    st.divider()
    st.subheader("📥 檔案 B：自訂假與固定班")
    vac_file = st.file_uploader("上傳本月預約表 (選填)", type=["xlsx", "csv"], key="vac")
    
    imported_v_map = None
    if vac_file and staff_configs:
        try:
            df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
            imported_v_map = get_vacation_import(df_vac, list(staff_configs.keys()), num_days)
            st.success("✅ 已載入自訂休假與固定班")
        except Exception as e:
            st.warning(f"預約表讀取失敗: {e}")

if not staff_configs:
    st.info("💡 請先在左側上傳「檔案 A」以產生成員名單。")
    st.stop()

# --- 2. 銜接核對 ---
st.subheader("⚙️ 核對權限與銜接狀態")
names = list(staff_configs.keys())
history_final, perm_final, cont_days_final = {}, {}, {}
cols = st.columns(4)
for i, n in enumerate(names):
    with cols[i % 4]:
        perm_final[n] = st.text_input(f"{n} 權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        history_final[n] = st.selectbox(f"{n} 上次", ["D", "E", "N", "off", "v", "R"], 
                                       index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), key=f"h_{n}")
        cont_days_final[n] = st.number_input(f"{n} 連續天數", 0, 6, 0, key=f"c_{n}")

# --- 3. 預約假表格 ---
st.subheader("📅 自訂休假與固定班 (R 為休假)")
dates = [f"{i+1}日" for i in range(num_days)]

if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    if imported_v_map:
        st.session_state.v_df = pd.DataFrame(imported_v_map).T
        st.session_state.v_df.columns = dates
    else:
        st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

edited_df = st.data_editor(st.session_state.v_df, use_container_width=True)

# --- 4. 啟動 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    final_res, err = run_scheduling(names, num_days, history_final, cont_days_final, edited_df, perm_final)
    if err:
        st.error(err)
    else:
        st.success("✅ 排班成功！")
        def style_f(v):
            colors = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2'}
            return f'background-color: {colors.get(v, "transparent")}; color: black; font-weight: bold'
        st.dataframe(final_res.style.map(style_f), use_container_width=True)
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            final_res.to_excel(writer, sheet_name='建議班表')
        st.download_button("📥 下載 Excel 結果", out.getvalue(), "2F_Schedule.xlsx")
# 找到這一段，確保有寫 engine='openpyxl'
with pd.ExcelWriter(out, engine='openpyxl') as writer:
    final_res.to_excel(writer, sheet_name='建議班表')
