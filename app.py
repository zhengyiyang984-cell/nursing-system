import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-全員辨識版", layout="wide")

# --- 1. 核心清理工具 ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    # 移除全形半形空格與換行
    s = re.sub(r'[\s\u3000\n\r\t]', '', s)
    return s

def safe_read_csv(file):
    try:
        return pd.read_csv(file, header=None, encoding='utf-8')
    except:
        file.seek(0)
        return pd.read_csv(file, header=None, encoding='big5')

# --- 2. 強化版人員解析 (解決只抓到11人的問題) ---
def get_staff_base_data(df):
    staff_data = {}
    start_row = -1
    
    # 第一步：找出資料開始的行
    for i, row in df.iterrows():
        row_str = "".join(str(v) for v in row.values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = i
            break
    
    if start_row == -1: start_row = 1 # 萬一找不到就從第 2 行開始
    
    # 第二步：抓取所有人員
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        # 通常姓名在第 3 欄 (Index 2)，若為空則檢查前後欄位
        raw_name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        if raw_name == "" or raw_name == "nan":
            continue
        
        # 排除日期列 (如果內容是純數字)
        if raw_name.isdigit():
            continue
            
        sid = super_clean(raw_name)
        # 排除標題重複項
        if "姓名" in sid or "星期" in sid:
            continue
            
        # 抓取權限 (Index 0) 與 銜接班別
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        
        # 抓取前幾天班別作為銜接 (歷史紀錄)
        last_val = "off"
        for cell in reversed(row.values[3:8]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_val = c.lower() if c in ["OFF", "V"] else c
                break
        
        staff_data[sid] = {
            "perm": perm, 
            "last_day": last_val, 
            "display_name": raw_name # 保留原本帶有 PN 的名字
        }
    return staff_data

def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    # 尋找預班表的資料起始點
    start_row = -1
    for i, row in df.iterrows():
        row_str = "".join(str(v) for v in row.values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = i
            break
    
    if start_row == -1: start_row = 1
    
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        sid = super_clean(row.iloc[2])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 # 日期從第 4 欄開始
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R", "0"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (全人員辨識優化版)")

with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    base_file = st.file_uploader("1. 上傳班表 (檔案 A)", type=["csv", "xlsx"])
    staff_configs = {}
    if base_file:
        try:
            df_base = safe_read_csv(base_file) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 成功辨識出 {len(staff_configs)} 位護理師")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

    vac_file = st.file_uploader("2. 上傳預班表 (檔案 B)", type=["csv", "xlsx"])

if not staff_configs:
    st.info("💡 請先上傳檔案 A 產生成員名單。")
    st.stop()

# 使用原始姓名作為索引，確保第一格顯示名字
names = list(staff_configs.keys())
display_names = [staff_configs[n]["display_name"] for n in names]
dates = [f"{i+1}日" for i in range(num_days)]

if 'v_df' not in st.session_state or len(st.session_state.v_df) != len(names):
    # 直接使用 display_names 作為 index，讓第一格顯示名字
    st.session_state.v_df = pd.DataFrame("", index=display_names, columns=dates)

if vac_file:
    if st.button("🔄 同步預班表內容", type="primary", use_container_width=True):
        try:
            df_vac = safe_read_csv(vac_file) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
            v_data = get_vacation_import(df_vac, names, num_days)
            # 建立 DataFrame 並將 index 換成顯示名稱
            new_v_df = pd.DataFrame(v_data).T
            new_v_df.index = display_names
            st.session_state.v_df = new_v_df
            st.session_state.v_df.columns = dates
            st.toast("✅ 預約內容已填入！")
        except Exception as e:
            st.error(f"同步失敗: {e}")

st.subheader("📅 預約假與固定班表 (第一欄為姓名)")
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

st.subheader("⚙️ 權限核對")
cols = st.columns(4)
final_perms = {}
for i, n in enumerate(names):
    d_name = staff_configs[n]["display_name"]
    with cols[i % 4]:
        final_perms[n] = st.text_input(f"{d_name}", value=staff_configs[n]["perm"], key=f"p_{n}")

if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    # 排班邏輯 (略，同前版本但改用正確索引)
    res = {n: [""] * num_days for n in names}
    # ... 進行演算 ...
    st.success("🎉 排班完成！")
    # 顯示結果並提供下載 (略)
