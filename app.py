import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-自動顯示預約版", layout="wide")

# --- 1. 輔助函數：清理與解析 ID ---
def clean_id(val):
    if pd.isna(val): return ""
    # 去除空格、換行，並過濾掉可能帶有的 PN 職級標籤
    s = re.sub(r'[\s\n\r\t\u200b-\u200d\ufeff]', '', str(val)).split('.')[0]
    s = s.split('P')[0].strip()
    return '半職1' if '半職' in s else s

# --- 2. 輔助函數：解析檔案 A (基礎資料) ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid and (sid.isdigit() or '半職' in sid or len(sid) > 1):
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            # 偵測上次班別
            last_val = "off"
            for cell in reversed(row.values[2:5]): # 檢查前幾欄找銜接
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val}
    return staff_data

# --- 3. 輔助函數：解析檔案 B (自動帶入預約假與固定班) ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 # 假設日期從第 4 欄開始
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R"]:
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]:
                        v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (預約表自動顯示版)")

# --- 側邊欄：雙匯入功能 ---
with st.sidebar:
    st.header("⚙️ 設定與匯入")
    num_days = st.slider("本月排班天數", 28, 31, 31)
    
    st.divider()
    st.subheader("📥 檔案 A：偵測人員名單")
    base_file = st.file_uploader("上傳上月班表 (檔案 A)", type=["xlsx", "csv"], key="base")
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 已載入 {len(staff_configs)} 人名單")
        except: st.error("檔案 A 讀取失敗")

    st.divider()
    st.subheader("📥 檔案 B：自動帶入預約")
    vac_file = st.file_uploader("上傳本月預約表 (檔案 B)", type=["xlsx", "csv"], key="vac")

if not staff_configs:
    st.info("💡 請先上傳「檔案 A」以產生成員名單。")
    st.stop()

# --- 核對狀態區 ---
st.subheader("⚙️ 核對權限與銜接狀態")
names = list(staff_configs.keys())
perm_final, history_final = {}, {}
cols = st.columns(4)
for i, n in enumerate(names):
    with cols[i % 4]:
        perm_final[n] = st.text_input(f"{n} 權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        history_final[n] = staff_configs[n]["last_day"] # 隱藏處理

# --- 關鍵功能：檔案 B 自動同步到網頁表格 ---
st.subheader("📅 自訂休假與固定班 (已根據檔案 B 自動更新)")
dates = [f"{i+1}日" for i in range(num_days)]

# 邏輯：如果檔案 B 有變動，重新生成 session_state 裡的表格資料
if vac_file:
    try:
        df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
        imported_data = get_vacation_import(df_vac, names, num_days)
        # 強制更新網頁上的編輯器內容
        st.session_state.v_df = pd.DataFrame(imported_data).T
        st.session_state.v_df.columns = dates
    except:
        st.warning("檔案 B 解析失敗，請檢查格式。")

# 初始化或顯示表格
if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# 使用 Data Editor 顯示，並允許最後微調
final_v_table = st.data_editor(st.session_state.v_df, use_container_width=True, key="main_editor")

# --- 執行排班 ---
if st.button("🚀 執行自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    # (排班邏輯：包含 4D/3E/2N 與 R 優先)
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        
        # 1. 填入表格中顯示的 R 或 D/E/N
        for n in names:
            val = str(final_v_table.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R":
                res[n][d] = "R"; pool.remove(n)
        
        # 2. 自動補人
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in perm_final[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop(); res[staff][d] = shift; pool.remove(staff)
        
        for n in pool: res[n][d] = "off"

    st.success("🎉 排班完成！")
    def style_f(v):
        colors = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2'}
        return f'background-color: {colors.get(v, "transparent")}; color: black; font-weight: bold'
    st.dataframe(pd.DataFrame(res).T.style.map(style_f), use_container_width=True)
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        pd.DataFrame(res).T.to_excel(writer, sheet_name='結果')
    st.download_button("📥 下載 Excel", out.getvalue(), "2F_Schedule.xlsx")
