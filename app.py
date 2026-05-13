import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-強制定位版", layout="wide")

# --- 1. 核心清理工具 ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    s = re.sub(r'[\s\u3000\n\r\t]', '', s) # 移除所有空白
    return s

def safe_read_csv(file):
    # 嘗試多種台灣常見編碼，確保不報錯
    for enc in ['utf-8', 'big5', 'gbk', 'utf-16']:
        try:
            file.seek(0)
            return pd.read_csv(file, header=None, encoding=enc)
        except:
            continue
    return None

# --- 2. 強制解析邏輯 (直接指定第 3 欄) ---
def get_staff_base_data(df):
    staff_data = {}
    # 根據你的檔案，我們強制從第 3 列 (Index 2) 開始抓資料
    # 姓名強制鎖定在第 3 欄 (Index 2)
    for i in range(2, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        raw_name = str(row.iloc[2]).strip()
        # 過濾無效資料
        if raw_name in ["", "nan", "姓名", "職級", "姓名/職級"] or raw_name.isdigit():
            continue
            
        sid = super_clean(raw_name)
        # 權限在第 1 欄 (Index 0)
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        
        # 抓取銜接班別 (從 D 欄開始找)
        last_val = "off"
        for cell in reversed(row.values[3:7]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_val = c.lower() if c in ["OFF", "V"] else c
                break
        
        staff_data[sid] = {
            "perm": perm, 
            "last_day": last_val, 
            "display_name": raw_name 
        }
    return staff_data

def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    # 預班表同樣強制從第 3 列、第 3 欄開始
    for i in range(2, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        sid = super_clean(row.iloc[2])
        if sid in names:
            # 日期從第 4 欄 (Index 3) 開始
            for d in range(num_days):
                col_idx = d + 3
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R", "0", "O"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (強制欄位校正版)")

with st.sidebar:
    st.header("⚙️ 1. 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 28)
    base_file = st.file_uploader("上傳班表 (檔案 A)", type=["csv", "xlsx"])
    staff_configs = {}
    if base_file:
        df_base = safe_read_csv(base_file) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
        if df_base is not None:
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 已讀取 {len(staff_configs)} 人")
        else:
            st.error("檔案格式無法讀取")

    vac_file = st.file_uploader("2. 上傳預班表 (檔案 B)", type=["csv", "xlsx"])

if not staff_configs:
    st.info("💡 請上傳檔案 A 以產生成員名單。")
    st.stop()

names = list(staff_configs.keys())
display_names = [staff_configs[n]["display_name"] for n in names]
dates = [f"{i+1}日" for i in range(num_days)]

if 'v_df' not in st.session_state or len(st.session_state.v_df) != len(names):
    st.session_state.v_df = pd.DataFrame("", index=display_names, columns=dates)

if vac_file:
    if st.button("🔄 強制同步預班表內容", type="primary", use_container_width=True):
        df_vac = safe_read_csv(vac_file) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
        if df_vac is not None:
            v_data = get_vacation_import(df_vac, names, num_days)
            new_df = pd.DataFrame(v_data).T
            new_df.index = display_names
            st.session_state.v_df = new_df
            st.session_state.v_df.columns = dates
            st.toast("✅ 預約假已填入！")

st.subheader("📅 自訂預約表格 (第一欄應為姓名)")
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

# --- 人員權限與連班 ---
st.subheader("⚙️ 核對權限與已連班天數")
cols = st.columns(4)
final_perms, final_history, final_cont_days = {}, {}, {}
for i, n in enumerate(names):
    d_name = staff_configs[n]["display_name"]
    with cols[i % 4]:
        st.write(f"👤 **{d_name}**")
        final_perms[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        final_cont_days[n] = st.number_input(f"連班天數", 0, 6, 0, key=f"c_{n}")
        final_history[n] = staff_configs[n]["last_day"]

if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        for n in names:
            d_name = staff_configs[n]["display_name"]
            val = str(edited_v_table.loc[d_name, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]: res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R": res[n][d] = "R"; pool.remove(n)
            else:
                prev = res[n][d-1] if d > 0 else final_history[n]
                if prev == "N": res[n][d] = "v"; pool.remove(n)
                elif d == 0 and final_cont_days[n] >= 5: res[n][d] = "off"; pool.remove(n)
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in final_perms[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop(); res[staff][d] = shift; pool.remove(staff)
        for n in pool: res[n][d] = "off"

    st.success("🎉 排班完成！")
    final_df = pd.DataFrame(res).T
    final_df.index = display_names
    def style_f(v):
        c = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2', 'v': '#F5F5F5'}
        return f'background-color: {c.get(v, "transparent")}; color: black; font-weight: bold'
    st.dataframe(final_df.style.map(style_f), use_container_width=True)
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='結果')
    st.download_button("📥 下載 Excel", out.getvalue(), "2F_Schedule.xlsx")
