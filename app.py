import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

# 頁面基本配置
st.set_page_config(page_title="2F 護理排班系統-全自動背景版", layout="wide")

# --- 1. 核心解析邏輯 (背景自動掃描) ---
def get_staff_base_data(file):
    """從檔案 A 抓取姓名、序號、初始權限與銜接班別"""
    df = pd.read_excel(file, header=None)
    staff_list = []
    start_row = 0
    
    # 智慧搜尋：找出包含「姓名」或「職級」的那一行作為起始
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    # 從標題下一行開始抓取人員資料
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        # 定位：A欄(0)權限, B欄(1)序號, C欄(2)姓名
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 過濾無效列
        if name in ["", "nan", "None", "星期", "ALL"]: continue
        
        # 抓取銜接班別 (從日期欄位前幾格找最後一個有效班別)
        last_val = "off"
        for cell in reversed(row.values[3:8]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_day_val = c.lower() if c in ["OFF", "V"] else c
                break
        
        staff_list.append({
            "id": re.sub(r'[\s\u3000]', '', name), # 內部比對用
            "display": f"{no} {name}".strip(),     # 網頁顯示用
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": last_day_val
        })
    return staff_list

st.title("🏥 2F 護理排班系統 (背景自動同步版)")

# --- 2. 側邊欄：上傳與設定 ---
with st.sidebar:
    st.header("⚙️ 檔案匯入")
    num_days = st.slider("本月排班天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

# --- 3. 背景自動處理與核對區 ---
if file_a and file_b:
    try:
        # A. 背景解析人員清單
        staff_data = get_staff_base_data(file_a)
        sids = [s['id'] for s in staff_data]
        displays = {s['id']: s['display'] for s in staff_data}
        
        # B. 背景讀取預班表 (檔案 B)
        df_b = pd.read_excel(file_b, header=None)
        # 初始化預約假字典
        bg_vacations = {sid: [""] * num_days for sid in sids}
        
        for i in range(len(df_b)):
            name_b = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            if name_b in bg_vacations:
                for d in range(num_days):
                    val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    # 自動辨識各類休假符號
                    if val in ["R", "OFF", "V", "開會", "0", "O", "●"]:
                        bg_vacations[name_b][d] = "R"
                    elif val in ["D", "E", "N"]:
                        bg_vacations[name_b][d] = val
        
        st.success(f"✅ 已成功辨識 {len(staff_data)} 位人員，並自動完成背景假別同步。")

        # C. 顯示核對區 (權限、連班天數)
        st.subheader("⚙️ 排班權限與起始連班核對")
        st.info("系統已自動隱藏預約表格。請確認下方每位人員的權限與上月銜接狀況：")
        
        final_perms = {}
        final_cont_days = {}
        final_history = {}
        
        cols = st.columns(4)
        for i, s in enumerate(staff_data):
            sid = s['id']
            with cols[i % 4]:
                st.write(f"👤 **{s['display']}**")
                final_perms[sid] = st.text_input("權限", value=s['perm'], key=f"p_{sid}")
                final_cont_days[sid] = st.number_input("起始連班", 0, 6, 0, key=f"c_{sid}")
                final_history[sid] = s['last_day']

        # --- 4. 排班演算 ---
        if st.button("🚀 啟動自動排班 (含背景同步資料)", type="primary", use_container_width=True):
            res = {sid: [""] * num_days for sid in sids}
            
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                # 優先權 1：填入背景抓到的預班表假別
                for sid in sids:
                    v_val = bg_vacations[sid][d]
                    if v_val in ["D", "E", "N"]:
                        res[sid][d] = v_val
                        target[v_val] -= 1
                        pool.remove(sid)
                    elif v_val == "R":
                        res[sid][d] = "off"
                        pool.remove(sid)
                
                # 優先權 2：大夜銜接 (前一天 N，今天必休)
                for sid in list(pool):
                    prev = res[sid][d-1] if d > 0 else final_history[sid]
                    if prev == "N":
                        res[sid][d] = "v"
                        pool.remove(sid)
                
                # 優先權 3：分配人力需求 (N -> E -> D)
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in final_perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            c = qualified.pop()
                            res[c][d] = shift
                            pool.remove(c)
                
                # 剩下的排休
                for s in pool:
                    res[s][d] = "off"

            st.success("🎉 排班計算完成！")
            
            # --- 5. 結果顯示與下載 ---
            final_df = pd.DataFrame(res).T
            final_df.index = [displays[sid] for sid in sids]
            st.dataframe(final_df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer)
            st.download_button("📥 下載 Excel 結果", output.getvalue(), "2F_Final_Schedule.xlsx")

    except Exception as e:
        st.error(f"系統自動掃描失敗: {e}")
else:
    st.info("👋 您好！請在左側上傳【班表】與【預班表】Excel，系統將自動完成背景同步。")
