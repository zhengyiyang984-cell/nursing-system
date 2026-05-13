import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-Excel 專用版", layout="wide")

# --- 1. 核心解析邏輯 ---
def get_clean_staff_list(df):
    """從 Excel 抓取姓名與初始權限"""
    staff_data = {}
    # 根據你的 Excel 結構：從第 3 列 (Index 2) 開始掃描
    for i in range(2, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        # 姓名鎖定在第 3 欄 (Index 2，即 Excel 的 C 欄)
        raw_name = str(row.iloc[2]).strip()
        
        # 過濾標題與無效字串 (如 1, 2, 3 日期或空白)
        if raw_name in ["", "nan", "姓名/職級", "姓名", "職級"] or raw_name.isdigit():
            continue
            
        # 移除空格，作為系統識別碼 (sid)
        sid = re.sub(r'[\s\u3000\n\r\t]', '', raw_name)
        
        # 抓取權限 (通常在第一欄 Index 0)，若無則預設 DEN
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        if perm not in ["D", "E", "N", "DE", "DN", "EN", "DEN"]: 
            perm = "DEN"
        
        staff_data[sid] = {
            "display_name": raw_name,
            "perm": perm,
            "last_day": "off" 
        }
    return staff_data

def sync_vacation_excel(df_vac, names_dict, num_days):
    """將預班表 (檔案 B) 的資料對齊到網頁表格"""
    v_map = {sid: [""] * num_days for sid in names_dict.keys()}
    
    for i in range(2, len(df_vac)):
        row = df_vac.iloc[i]
        if len(row) < 3: continue
        
        raw_name = str(row.iloc[2]).strip()
        sid = re.sub(r'[\s\u3000\n\r\t]', '', raw_name)
        
        if sid in v_map:
            # 預班表日期通常從姓名後一欄開始 (Index 3)
            for d in range(num_days):
                col_idx = d + 3
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    # 辨識休假關鍵字
                    if val in ["R", "OFF", "V", "開會", "0", "O"]: 
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]: 
                        v_map[sid][d] = val
    return v_map

# --- 2. 網頁介面 ---
st.title("🏥 2F 護理排班系統 (Excel 專用連動版)")

with st.sidebar:
    st.header("⚙️ Excel 匯入區")
    num_days = st.slider("本月排班天數", 28, 31, 30)
    
    file_a = st.file_uploader("1. 上傳【班表】Excel (檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】Excel (檔案 B)", type=["xlsx"])

# --- 3. 處理邏輯 ---
if file_a:
    # 讀取 Excel
    try:
        df_a = pd.read_excel(file_a, header=None)
        staff_configs = get_clean_staff_list(df_a)
        sids = list(staff_configs.keys())
        display_names = [staff_configs[s]["display_name"] for s in sids]
        
        st.success(f"✅ 已辨識出 {len(sids)} 位護理人員")
        
        # 初始化預約表格狀態
        if 'v_df' not in st.session_state or len(st.session_state.v_df) != len(sids):
            st.session_state.v_df = pd.DataFrame(
                "", 
                index=display_names, 
                columns=[f"{i+1}日" for i in range(num_days)]
            )

        # 同步按鈕
        if file_b:
            if st.button("🔄 同步預班表內容到下方表格", type="primary", use_container_width=True):
                df_b = pd.read_excel(file_b, header=None)
                v_data = sync_vacation_excel(df_b, staff_configs, num_days)
                # 重新填充 session_state
                new_rows = [v_data[sid] for sid in sids]
                st.session_state.v_df = pd.DataFrame(
                    new_rows, 
                    index=display_names, 
                    columns=[f"{i+1}日" for i in range(num_days)]
                )
                st.toast("✅ 預約資料同步成功！")

        # --- 4. 編輯與排班 ---
        st.subheader("📅 1. 確認/修改預約假與固定班")
        final_v_df = st.data_editor(st.session_state.v_df, use_container_width=True)

        st.subheader("⚙️ 2. 核對權限與已連班天數")
        cols = st.columns(4)
        user_perms = {}
        user_cont = {}
        for i, sid in enumerate(sids):
            with cols[i % 4]:
                st.write(f"👤 **{staff_configs[sid]['display_name']}**")
                user_perms[sid] = st.text_input("權限", value=staff_configs[sid]['perm'], key=f"p_{sid}")
                user_cont[sid] = st.number_input("連班天數", 0, 6, 0, key=f"c_{sid}")

        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {sid: [""] * num_days for sid in sids}
            # 排班演算邏輯 (4D/3E/2N)
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                # 處理預約
                for sid in sids:
                    d_name = staff_configs[sid]['display_name']
                    val = str(final_v_df.loc[d_name, f"{d+1}日"]).strip().upper()
                    if val in ["D", "E", "N"]:
                        res[sid][d] = val; target[val] -= 1; pool.remove(sid)
                    elif val == "R":
                        res[sid][d] = "R"; pool.remove(sid)
                # 填充人力
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in user_perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop()
                            res[chosen][d] = shift; pool.remove(chosen)
                for s in pool: res[s][d] = "off"

            st.success("🎉 排班完成！")
            final_res = pd.DataFrame(res).T
            final_res.index = display_names
            st.dataframe(final_res.style.highlight_max(axis=0, color='#f0f0f0'), use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                final_res.to_excel(writer)
            st.download_button("📥 下載 Excel 結果", output.getvalue(), "Result.xlsx")
    except Exception as e:
        st.error(f"Excel 讀取發生錯誤: {e}")
else:
    st.info("請先上傳【檔案 A】Excel 以產生成員清單。")
