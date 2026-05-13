import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-全自動極簡版", layout="wide")

# --- 1. 核心解析邏輯 (背景作業) ---
def get_staff_data(file):
    """從檔案 A 抓取姓名與權限"""
    df = pd.read_excel(file, header=None)
    staff_list = []
    start_row = 0
    # 尋找關鍵字定位
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        # A欄:權限, B欄:序號, C欄:姓名
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        if name in ["", "nan", "None", "星期", "ALL"]: continue
        
        staff_list.append({
            "id": re.sub(r'[\s\u3000]', '', name), # 內部比對用
            "display": f"{no} {name}".strip(),     # 輸出結果用
            "perm": perm if perm != "NAN" else "DEN"
        })
    return staff_list

# --- 2. 介面與上傳 ---
st.title("🏥 2F 護理排班系統 (全背景同步版)")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

# --- 3. 背景自動處理邏輯 ---
if file_a and file_b:
    try:
        # 背景讀取人員名單
        staff_data = get_staff_data(file_a)
        sids = [s['id'] for s in staff_data]
        displays = {s['id']: s['display'] for s in staff_data}
        perms = {s['id']: s['perm'] for s in staff_data}

        # 背景讀取檔案 B 預約假
        df_b = pd.read_excel(file_b, header=None)
        # 初始化預約字典 { '姓名ID': ['假別1', '假別2', ...] }
        bg_vacations = {sid: [""] * num_days for sid in sids}

        for i in range(len(df_b)):
            name_b_raw = str(df_b.iloc[i, 2]).strip()
            sid_b = re.sub(r'[\s\u3000]', '', name_b_raw)
            
            if sid_b in bg_vacations:
                for d in range(num_days):
                    # 日期從第 4 欄 (Index 3) 開始
                    val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    # 自動將雜訊符號轉為 R班 (休假)
                    if val in ["R", "OFF", "V", "開會", "0", "O", "●"]:
                        bg_vacations[sid_b][d] = "R"
                    elif val in ["D", "E", "N"]:
                        bg_vacations[sid_b][d] = val

        st.success(f"✅ 已辨識 {len(staff_data)} 位人員，預班表資料已在背景同步完成。")
        st.info("💡 介面已簡化：預約表格已隱藏，請直接執行下方排班按鈕。")

        # --- 4. 自動排班運算 ---
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            schedule_results = {sid: [""] * num_days for sid in sids}
            
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2} # 標準人力配置
                pool = sids.copy()
                random.shuffle(pool)
                
                # A. 先套用背景抓到的預約假
                for sid in sids:
                    v_val = bg_vacations[sid][d]
                    if v_val in ["D", "E", "N"]:
                        schedule_results[sid][d] = v_val
                        target[v_val] -= 1
                        pool.remove(sid)
                    elif v_val == "R":
                        schedule_results[sid][d] = "off"
                        pool.remove(sid)
                
                # B. 分配剩餘人力 (按權限 N -> E -> D)
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop()
                            schedule_results[chosen][d] = shift
                            pool.remove(chosen)
                
                # C. 剩下的人全部休息
                for s in pool:
                    schedule_results[s][d] = "off"
            
            # --- 5. 顯示與下載排班結果 ---
            st.subheader("🎉 最終排班結果")
            final_df = pd.DataFrame(schedule_results).T
            final_df.index = [displays[sid] for sid in sids]
            st.dataframe(final_df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_df.to_excel(writer)
            st.download_button("📥 下載 Excel 結果", output.getvalue(), "2F_Schedule_Final.xlsx")

    except Exception as e:
        st.error(f"背景同步或排班運算發生錯誤: {e}")
else:
    st.info("👋 您好！請在左側上傳【班表】與【預班表】Excel 檔案以開始排班。")
