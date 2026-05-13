import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-預班表自動抓取版", layout="wide")

# --- 1. 超強效清理工具：專門對付全形空格與隱藏字元 ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val)
    # 移除 PN1, PN2, PN3, 阿長等職級標籤
    s = re.sub(r'P[Nn]\d+', '', s)
    s = s.replace("阿長", "")
    # 移除換行符、全形空格 (\u3000)、半形空格
    s = re.sub(r'[\s\u3000\n\r\t]', '', s)
    return '半職1' if '半職' in s else s

# --- 2. 解析檔案 A (班表.csv) ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        if i < 2: continue  # 跳過前兩列標題
        name_raw = str(row.iloc[2]).strip() # 姓名在第 3 欄 (Index 2)
        sid = super_clean(name_raw)
        if sid and sid not in ["姓名/職級", "nan", ""]:
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            # 抓取銜接班別 (從日期欄位前幾格抓)
            last_val = "off"
            for cell in reversed(row.values[3:7]):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val, "display_name": name_raw}
    return staff_data

# --- 3. 解析檔案 B (預班表.csv) ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        if i < 2: continue # 跳過標題
        sid = super_clean(row.iloc[2]) # 姓名在第 3 欄
        if sid in names:
            # 日期從第 4 欄 (Index 3) 開始
            for d in range(num_days):
                col_idx = d + 3 
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    # 辨識假別與固定班 (包含處理 '0' 代表休假的情況)
                    if val in ["OFF", "V", "開會", "R", "0"]: 
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: 
                        v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (預班表內容自動抓取)")

# --- 側邊欄匯入 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 28)
    
    base_file = st.file_uploader("1. 上傳【班表.csv】(產生成員)", type=["csv", "xlsx"])
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None, encoding='utf-8')
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 成功辨識 {len(staff_configs)} 人")
        except:
            st.error("檔案 A 讀取失敗，請確認是否為 CSV 格式")

    vac_file = st.file_uploader("2. 上傳【預班表.csv】(抓取內容)", type=["csv", "xlsx"])

if not staff_configs:
    st.info("💡 請先上傳檔案 A 產生成員名單。")
    st.stop()

names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

# 初始化資料表
if 'v_df' not in st.session_state:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# --- 核心按鈕：強制抓取檔案 B 內容 ---
if vac_file:
    if st.button("📥 點我：自動從預班表抓取內容", type="primary", use_container_width=True):
        try:
            df_vac = pd.read_csv(vac_file, header=None, encoding='utf-8')
            v_data = get_vacation_import(df_vac, names, num_days)
            st.session_state.v_df = pd.DataFrame(v_data).T
            st.session_state.v_df.columns = dates
            st.success("✅ 預約內容已成功填入下方表格！")
        except:
            st.error("預班表解析失敗，請確認檔案內容格式")

st.subheader("📅 自訂假與固定班別 (自動連動結果)")
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

# --- 人員權限與天數 ---
st.subheader("⚙️ 核對權限與連班天數")
cols = st.columns(4)
final_perms, final_history, final_cont_days = {}, {}, {}
for i, n in enumerate(names):
    with cols[i % 4]:
        st.write(f"👤 **{staff_configs[n]['display_name']}**")
        final_perms[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        final_cont_days[n] = st.number_input(f"已連班天數", 0, 6, 0, key=f"c_{n}")
        final_history[n] = staff_configs[n]["last_day"]

# --- 自動排班計算 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    # 排班演算邏輯 (4D/3E/2N)
    res = {n: [""] * num_days for n in names}
    # ... [此處省略後續排班演算代碼，請保留原本的演算區塊] ...
    st.write("排班運算中...")
    # (請確保將完整的排班迴圈放入此處)
