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
    import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-最終修正版", layout="wide")

# --- 1. 超強效清理工具 ---
def super_clean(val):
    if pd.isna(val): return ""
    s = str(val).strip()
    # 移除所有空白字元與換行
    s = re.sub(r'[\s\u3000\n\r\t]', '', s)
    return s

def safe_read_csv(file):
    try:
        return pd.read_csv(file, header=None, encoding='utf-8')
    except:
        file.seek(0)
        return pd.read_csv(file, header=None, encoding='big5')

# --- 2. 智慧定位解析：自動搜尋「姓名」關鍵字 ---
def get_staff_base_data(df):
    staff_data = {}
    name_col = -1
    start_row = -1
    
    # 掃描整張表找出「姓名」或「職級」所在的格子
    for r in range(len(df)):
        for c in range(len(df.columns)):
            val = str(df.iloc[r, c])
            if "姓名" in val or "職級" in val:
                name_col = c
                start_row = r
                break
        if name_col != -1: break
    
    # 如果真的找不到關鍵字，預設使用第 3 欄 (Index 2)
    if name_col == -1: name_col = 2
    if start_row == -1: start_row = 1

    # 開始從標題行的下一行抓取人員
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        raw_name = str(row.iloc[name_col]).strip()
        
        # 過濾雜訊：如果是空的、是數字(日期)、或包含標題字眼就跳過
        if raw_name == "" or raw_name == "nan" or raw_name.isdigit() or "姓名" in raw_name:
            continue
            
        sid = super_clean(raw_name)
        # 抓取權限 (通常在第一欄 Index 0)
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        
        # 抓取銜接班別 (從日期欄位前幾格找最後一個有效班)
        last_val = "off"
        for cell in reversed(row.values[name_col+1 : name_col+5]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_val = c.lower() if c in ["OFF", "V"] else c
                break
        
        staff_data[sid] = {
            "perm": perm, 
            "last_day": last_val, 
            "display_name": raw_name  # 這就是你要在表格第一欄看到的帶 PN 的名字
        }
    return staff_data

def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    # 同樣在預班表尋找「姓名」定位
    name_col = -1
    start_row = -1
    for r in range(len(df)):
        for c in range(len(df.columns)):
            val = str(df.iloc[r, c])
            if "姓名" in val or "職級" in val:
                name_col = c
                start_row = r
                break
        if name_col != -1: break
        
    if name_col == -1: name_col = 2
    if start_row == -1: start_row = 1

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        sid = super_clean(row.iloc[name_col])
        if sid in names:
            # 日期通常從姓名後一欄開始
            for d in range(num_days):
                col_idx = d + name_col + 1
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R", "0"]: v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (智慧定位修正版)")

# --- 側邊欄匯入 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 28)
    base_file = st.file_uploader("1. 上傳班表 (檔案 A)", type=["csv", "xlsx"])
    staff_configs = {}
    if base_file:
        try:
            df_base = safe_read_csv(base_file) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 成功辨識出 {len(staff_configs)} 位護理師")
        except: st.error("班表解析失敗，請確認檔案格式")

    vac_file = st.file_uploader("2. 上傳預班表 (檔案 B)", type=["csv", "xlsx"])

if not staff_configs:
    st.info("💡 請上傳檔案 A 以產生成員表格。")
    st.stop()

# --- 介面管理：強制第一欄顯示名字 ---
names = list(staff_configs.keys())
display_names = [staff_configs[n]["display_name"] for n in names]
dates = [f"{i+1}日" for i in range(num_days)]

# 初始化或強制刷新表格
if 'v_df' not in st.session_state or len(st.session_state.v_df) != len(names):
    st.session_state.v_df = pd.DataFrame("", index=display_names, columns=dates)

if vac_file:
    if st.button("🔄 同步預班表內容到下方表格", type="primary", use_container_width=True):
        try:
            df_vac = safe_read_csv(vac_file) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
            v_data = get_vacation_import(df_vac, names, num_days)
            # 建立 DataFrame 並將 index 換成正確的顯示名稱
            new_v_df = pd.DataFrame(v_data).T
            new_v_df.index = display_names
            st.session_state.v_df = new_v_df
            st.toast("✅ 預約內容已成功填入！")
        except: st.error("預班表同步失敗")

st.subheader("📅 自訂假與固定班別 (第一欄為姓名)")
# 顯示互動表格
edited_v_table = st.data_editor(st.session_state.v_df, use_container_width=True)

# --- 人員核對區 ---
st.subheader("⚙️ 權限與連班天數核對")
cols = st.columns(4)
final_perms, final_history, final_cont_days = {}, {}, {}
for i, n in enumerate(names):
    d_name = staff_configs[n]["display_name"]
    with cols[i % 4]:
        st.write(f"👤 **{d_name}**")
        final_perms[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        final_cont_days[n] = st.number_input(f"連班天數", 0, 6, 0, key=f"c_{n}")
        final_history[n] = staff_configs[n]["last_day"]

# --- 啟動排班 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    # (排班演算邏輯...)
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
