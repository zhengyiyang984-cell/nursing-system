import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-全功能終極版", layout="wide")

# --- 1. 核心解析工具 ---
def clean_id(val):
    if pd.isna(val): return ""
    s = re.sub(r'[\s\n\r\t\u200b-\u200d\ufeff]', '', str(val)).split('.')[0]
    s = s.split('P')[0].strip()
    return '半職1' if '半職' in s else s

def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid and (sid.isdigit() or '半職' in sid or len(sid) > 1):
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            # 偵測上次最後一天的班別
            last_val = "off"
            for cell in reversed(row.values[2:6]):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val}
    return staff_data

def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (全邏輯 + 檔案 B 自動連動)")

# --- 側邊欄：匯入區 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    base_file = st.file_uploader("1. 上傳檔案 A (產生成員與權限)", type=["xlsx", "csv"])
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 已讀取 {len(staff_configs)} 人")
        except: st.error("檔案 A 讀取失敗")

    vac_file = st.file_uploader("2. 上傳檔案 B (預約假自動填入表格)", type=["xlsx", "csv"])

if not staff_configs:
    st.info("💡 請先上傳檔案 A 以顯示人員表格。")
    st.stop()

# --- 狀態管理：確保檔案 B 能直接顯示在表格裡 ---
names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

# 如果偵測到新上傳的檔案 B，強制更新表格狀態
if vac_file:
    try:
        df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
        v_data = get_vacation_import(df_vac, names, num_days)
        st.session_state.v_df = pd.DataFrame(v_data).T
        st.session_state.v_df.columns = dates
    except: st.warning("檔案 B 解析失敗")

# 初始化空白表格
if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# --- 介面佈局 ---
st.subheader("📅 自訂休假與固定班別 (檔案 B 上傳後會自動填入)")
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

# 顯示權限確認（小區塊）
with st.expander("🔍 查看人員權限與上次班別"):
    cols = st.columns(4)
    final_perms = {}
    final_history = {}
    for i, n in enumerate(names):
        with cols[i % 4]:
            final_perms[n] = st.text_input(f"{n} 權 es", value=staff_configs[n]["perm"], key=f"p_{n}")
            final_history[n] = staff_configs[n]["last_day"]

# --- 核心排班邏輯 (把之前的規則加回來) ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    
    # A. 處理半職 1 (固定 10 天 D 班邏輯)
    if "半職1" in names:
        # 讀取表格中半職 1 的預約 R
        pt_r = [d for d in range(num_days) if str(edited_v_table.loc["半職1", f"{d+1}日"]).strip().upper() == "R"]
        for d in pt_r: res["半職1"][d] = "R"
        # 隨機塞 10 天 D 班，避開 R
        possible_days = [d for d in range(num_days) if d not in pt_r]
        if len(possible_days) >= 10:
            for d in random.sample(possible_days, 10): res["半職1"][d] = "D"
        for d in range(num_days):
            if res["半職1"][d] == "": res["半職1"][d] = "off"

    # B. 處理其餘人員
    others = [n for n in names if n != "半職1"]
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2} # 每日人力目標
        if "半職1" in res and res["半職1"][d] == "D": target["D"] -= 1
        
        pool = others.copy()
        random.shuffle(pool)
        
        # 1. 優先處理表格中的預約 (R, D, E, N)
        for n in others:
            val = str(edited_v_table.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R":
                res[n][d] = "R"; pool.remove(n)
            else:
                # 處理大夜銜接休假 (v)
                prev = res[n][d-1] if d > 0 else final_history[n]
                if prev == "N":
                    res[n][d] = "v"; pool.remove(n)

        # 2. 依照權限補滿人力
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in final_perms[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop()
                    res[staff][d] = shift; pool.remove(staff)
        
        # 3. 剩下的排休
        for n in pool: res[n][d] = "off"

    # 顯示結果
    final_df = pd.DataFrame(res).T
    st.success("🎉 自動排班已完成！")
    def style_f(v):
        c = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2', 'v': '#F5F5F5'}
        return f'background-color: {c.get(v, "transparent")}; color: black; font-weight: bold'
    st.dataframe(final_df.style.map(style_f), use_container_width=True)
    
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='2F班表')
    st.download_button("📥 下載 Excel 結果", out.getvalue(), "2F_Schedule.xlsx")
