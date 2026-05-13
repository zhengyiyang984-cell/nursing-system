import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-預班表精準對接版", layout="wide")

# --- 1. 超強效姓名清理工具 (確保兩邊檔案的人名能對起來) ---
def clean_id(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    # 移除 PN1, PN2, PN3, 阿長 等職級標籤
    s = re.sub(r'P[Nn]\d+', '', s)
    s = s.replace("阿長", "").strip()
    # 移除所有空白字元
    s = re.sub(r'\s+', '', s)
    return '半職1' if '半職' in s else s

# --- 2. 解析檔案 A (產生成員名單) ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        # 假設姓名在第 2 欄 (Index 1)
        name_raw = str(row.iloc[1]) 
        sid = clean_id(name_raw)
        if sid and sid != "姓名" and len(sid) >= 1:
            # 抓取第 1 欄權限
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            # 抓取銜接 (從表格前面找最後一個班別作為歷史記錄)
            last_val = "off"
            for cell in reversed(row.values[2:6]):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val, "display_name": name_raw}
    return staff_data

# --- 3. 解析預班表 (檔案 B) ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        # 清理預班表裡的姓名
        sid = clean_id(row.iloc[1])
        if sid in names:
            # 重要：根據你的 CSV，日期是從第 5 欄 (Index 4) 開始
            for d in range(num_days):
                col_idx = d + 4 
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    # 辨識假別與固定班
                    if val in ["OFF", "V", "開會", "R"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (預班表對接優化版)")

with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    
    st.subheader("1. 匯入人員清單 (檔案 A)")
    base_file = st.file_uploader("上傳班表.csv", type=["xlsx", "csv"], key="A")
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 成功辨識 {len(staff_configs)} 位護理人員")
        except: st.error("檔案 A 讀取失敗")

    st.subheader("2. 匯入自訂假 (檔案 B)")
    vac_file = st.file_uploader("上傳預班表.csv", type=["xlsx", "csv"], key="B")

if not staff_configs:
    st.info("💡 請先上傳檔案 A，系統才能產生成員表格。")
    st.stop()

names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

# 初始化 Session State 的預約表
if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# --- 核心動作：點擊按鈕才將預班表連過去 ---
if vac_file:
    if st.button("🔄 點此將【預班表】資料連至下方表格", type="primary"):
        try:
            df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
            v_data = get_vacation_import(df_vac, names, num_days)
            st.session_state.v_df = pd.DataFrame(v_data).T
            st.session_state.v_df.columns = dates
            st.toast("✅ 預約假與固定班已成功同步！")
        except: st.error("預班表內容抓取失敗，請確認檔案格式")

st.subheader("📅 自訂休假與固定班別 (由預班表自動填入)")
# 顯示互動表格
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True, key="main_editor")

st.subheader("⚙️ 核對權限與已連班天數")
cols = st.columns(4)
final_perms, final_history, final_cont_days = {}, {}, {}
for i, n in enumerate(names):
    with cols[i % 4]:
        st.write(f"👤 **{staff_configs[n]['display_name']}**")
        final_perms[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}", label_visibility="collapsed")
        final_cont_days[n] = st.number_input(f"已連班天數", 0, 6, 0, key=f"c_{n}")
        final_history[n] = staff_configs[n]["last_day"]

# --- 排班運算 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    # 演算邏輯：4D/3E/2N
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        
        # 1. 抓取表格預約
        for n in names:
            val = str(edited_v_table.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]: 
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R": 
                res[n][d] = "R"; pool.remove(n)
            else:
                prev = res[n][d-1] if d > 0 else final_history[n]
                if prev == "N": res[n][d] = "v"; pool.remove(n)
                elif d == 0 and final_cont_days[n] >= 5: res[n][d] = "off"; pool.remove(n)
        
        # 2. 自動補人
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
