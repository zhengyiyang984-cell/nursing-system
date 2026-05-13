import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-兼容版", layout="wide")

# --- 1. 超強效清理工具 ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val)
    s = re.sub(r'P[Nn]\d+', '', s)
    s = s.replace("阿長", "")
    s = re.sub(r'[\s\u3000\n\r\t]', '', s)
    return '半職1' if '半職' in s else s

# --- 2. 檔案讀取工具 (自動處理編碼問題) ---
def safe_read_csv(file):
    try:
        # 先嘗試通用 UTF-8
        return pd.read_csv(file, header=None, encoding='utf-8')
    except UnicodeDecodeError:
        # 如果失敗，嘗試台灣常用的 Big5 (ANSI)
        file.seek(0) # 指針重置
        return pd.read_csv(file, header=None, encoding='big5')

# --- 3. 解析邏輯 ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        if i < 2: continue
        name_raw = str(row.iloc[2]).strip() 
        sid = super_clean(name_raw)
        if sid and sid not in ["姓名/職級", "nan", ""]:
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            last_val = "off"
            for cell in reversed(row.values[3:7]):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val, "display_name": name_raw}
    return staff_data

def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        if i < 2: continue
        sid = super_clean(row.iloc[2])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R", "0"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (編碼修正兼容版)")

with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    
    st.subheader("1. 匯入班表 (檔案 A)")
    base_file = st.file_uploader("上傳班表.csv", type=["csv", "xlsx"], key="A")
    staff_configs = {}
    if base_file:
        try:
            if base_file.name.endswith('.csv'):
                df_base = safe_read_csv(base_file)
            else:
                df_base = pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 辨識出 {len(staff_configs)} 人")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

    st.subheader("2. 匯入預班表 (檔案 B)")
    vac_file = st.file_uploader("上傳預班表.csv", type=["csv", "xlsx"], key="B")

if not staff_configs:
    st.info("💡 請先上傳檔案 A 產生成員名單。")
    st.stop()

names = list(staff_configs.keys())
dates = [f"{i+1}日" for i in range(num_days)]

if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

if vac_file:
    if st.button("🔄 點我：自動抓取預班表內容到表格", type="primary", use_container_width=True):
        try:
            if vac_file.name.endswith('.csv'):
                df_vac = safe_read_csv(vac_file)
            else:
                df_vac = pd.read_excel(vac_file, header=None)
            v_data = get_vacation_import(df_vac, names, num_days)
            st.session_state.v_df = pd.DataFrame(v_data).T
            st.session_state.v_df.columns = dates
            st.toast("✅ 預約內容已成功同步！")
        except Exception as e:
            st.error(f"預班表解析出錯: {e}")

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

if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
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
