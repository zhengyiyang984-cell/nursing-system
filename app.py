import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-精準連動版", layout="wide")

# --- 1. 超強效清理工具 (解決對不到人的問題) ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val)
    # 移除 PN1, PN2, PN3, 阿長等職級標籤
    s = re.sub(r'P[Nn]\d+', '', s)
    s = s.replace("阿長", "")
    # 移除所有空白 (包含全形空格 \u3000)
    s = re.sub(r'[\s\u3000\n\r\t]', '', s)
    return '半職1' if '半職' in s else s

# --- 2. 解析班表 (產生成員與權限) ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        if i < 2: continue # 跳過標題列
        # 根據檔案，姓名在第 3 欄 (Index 2)
        name_raw = str(row.iloc[2]).strip() 
        sid = super_clean(name_raw)
        if sid and sid not in ["姓名/職級", "nan", ""]:
            # 權限在第 1 欄 (Index 0)
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            # 抓取銜接班別 (從日期欄位前幾格找最後一個有效班)
            last_val = "off"
            for cell in reversed(row.values[3:7]):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val, "display_name": name_raw}
    return staff_data

# --- 3. 解析預班表 (抓取預約內容) ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        if i < 2: continue # 跳過標題
        # 預班表的姓名也在第 3 欄 (Index 2)
        sid = super_clean(row.iloc[2])
        if sid in names:
            # 根據預班表檔案，日期從第 4 欄 (Index 3) 開始
            for d in range(num_days):
                col_idx = d + 3 
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    # 辨識假別 (包含處理 '0' 或 'R' 或 'OFF')
                    if val in ["OFF", "V", "開會", "R", "0"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (檔案 B 自動連動版)")

# --- 側邊欄匯入 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    
    st.subheader("1. 匯入班表 (檔案 A)")
    base_file = st.file_uploader("上傳班表.csv", type=["csv", "xlsx"], key="A")
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 辨識出 {len(staff_configs)} 人")
        except: st.error("班表讀取失敗")

    st.subheader("2. 匯入預班表 (檔案 B)")
    vac_file = st.file_uploader("上傳預班表.csv", type=["csv", "xlsx"], key="B")

if not staff_configs:
    st.info("💡 請先上傳檔案 A 產生成員名單。")
    st.stop()

names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

# 初始化或更新 Session State 表格
if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# --- 同步按鈕：讓檔案 B 的內容連過去 ---
if vac_file:
    if st.button("🔄 點我：自動抓取預班表內容到表格", type="primary", use_container_width=True):
        try:
            df_vac = pd.read_csv(vac_file, header=None)
            v_data = get_vacation_import(df_vac, names, num_days)
            st.session_state.v_df = pd.DataFrame(v_data).T
            st.session_state.v_df.columns = dates
            st.toast("✅ 預約內容已成功同步！")
        except: st.error("預班表解析出錯")

st.subheader("📅 自訂假與固定班別 (由預班表自動填入)")
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

st.subheader("⚙️ 核對權限與連班天數")
cols = st.columns(4)
final_perms, final_history, final_cont_days = {}, {}, {}
for i, n in enumerate(names):
    with cols[i % 4]:
        st.write(f"👤 **{staff_configs[n]['display_name']}**")
        final_perms[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        final_cont_days[n] = st.number_input(f"已連班天數", 0, 6, 0, key=f"c_{n}")
        final_history[n] = staff_configs[n]["last_day"]

# --- 排班邏輯 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    # 4D/3E/2N 邏輯
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        for n in names:
            val = str(edited_v_table.loc[n, f"{d+1}日"]).strip().upper()
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
    def style_f(v):
        c = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2', 'v': '#F5F5F5'}
        return f'background-color: {c.get(v, "transparent")}; color: black; font-weight: bold'
    st.dataframe(final_df.style.map(style_f), use_container_width=True)
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='2F結果')
    st.download_button("📥 下載 Excel", out.getvalue(), "2F_Schedule.xlsx")
