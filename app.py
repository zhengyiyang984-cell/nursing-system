import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-即時連動版", layout="wide")

# --- 1. 基礎輔助工具 ---
def clean_id(val):
    if pd.isna(val): return ""
    s = re.sub(r'[\s\n\r\t\u200b-\u200d\ufeff]', '', str(val)).split('.')[0]
    s = s.split('P')[0].strip() # 處理像 PN2 這種字眼
    return '半職1' if '半職' in s else s

# --- 2. 解析檔案 B (預約表) ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 # 日期從第 4 欄開始
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R"]:
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]:
                        v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (檔案 B 自動連動版)")

# --- 側邊欄 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 31)
    
    st.subheader("📥 檔案 A (名單)")
    base_file = st.file_uploader("上傳上月班表", type=["xlsx", "csv"], key="base")
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            # 建立名單
            for i, row in df_base.iterrows():
                sid = clean_id(row.iloc[1])
                if sid and (sid.isdigit() or '半職' in sid or len(sid) > 1):
                    perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
                    staff_configs[sid] = {"perm": perm}
            st.success(f"✅ 已讀取 {len(staff_configs)} 人")
        except: st.error("檔案 A 讀取失敗")

    st.subheader("📥 檔案 B (預約)")
    vac_file = st.file_uploader("上傳預約表", type=["xlsx", "csv"], key="vac_uploader")

if not staff_configs:
    st.info("💡 請先上傳檔案 A 以顯示人員表格。")
    st.stop()

# --- 關鍵：處理檔案 B 的即時顯示邏輯 ---
names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

# 如果檔案 B 剛剛被上傳，我們強制更新 Session State
if vac_file:
    try:
        df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
        v_data = get_vacation_import(df_vac, names, num_days)
        # 直接更新儲存格數據
        st.session_state.v_df = pd.DataFrame(v_data).T
        st.session_state.v_df.columns = dates
    except:
        st.warning("檔案 B 解析出錯")

# 若尚未初始化表格，則建立空白表
if 'v_df' not in st.session_state:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

st.subheader("📅 自訂休假與固定班 (上傳檔案 B 後自動顯示於此)")
# 顯示互動式表格
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True, key="data_editor_main")

# --- 啟動排班 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        
        # 1. 讀取畫面上表格的內容 (包含檔案 B 自動填入的 R/D/E/N)
        for n in names:
            val = str(edited_v_table.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R":
                res[n][d] = "R"; pool.remove(n)

        # 2. 隨機補人邏輯
        random.shuffle(pool)
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in staff_configs[n]["perm"]]
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop()
                    res[staff][d] = shift; pool.remove(staff)
        for n in pool: res[n][d] = "off"

    st.success("✅ 排班成功！")
    def style_f(v):
        colors = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2'}
        return f'background-color: {colors.get(v, "transparent")}; color: black; font-weight: bold'
    st.dataframe(pd.DataFrame(res).T.style.map(style_f), use_container_width=True)
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame(res).T.to_excel(writer)
    st.download_button("📥 下載 Excel", out.getvalue(), "Schedule.xlsx")
