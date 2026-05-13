import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-精簡銜接版", layout="wide")

# --- 核心解析邏輯 ---
def get_staff_data(file):
    df = pd.read_excel(file, header=None)
    staff_list = []
    start_row = 0
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
        
        # 抓取前一天的班別 (銜接邏輯)
        last_day_val = "off"
        for cell in reversed(row.values[3:7]): # 檢查 Excel 前幾格找最後一個有效班
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_day_val = c.lower() if c in ["OFF", "V"] else c
                break
        
        staff_list.append({
            "id": re.sub(r'[\s\u3000]', '', name),
            "display": f"{no} {name}".strip(),
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": last_day_val
        })
    return staff_list

st.title("🏥 2F 護理排班系統 (背景同步+銜接核對版)")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b:
    try:
        # 1. 背景處理：解析人員與銜接資料
        staff_data = get_staff_data(file_a)
        sids = [s['id'] for s in staff_data]
        displays = {s['id']: s['display'] for s in staff_data}
        
        # 2. 背景處理：讀取預班表 (檔案 B)
        df_b = pd.read_excel(file_b, header=None)
        bg_vacations = {sid: [""] * num_days for sid in sids}
        for i in range(len(df_b)):
            name_b = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            if name_b in bg_vacations:
                for d in range(num_days):
                    val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    if val in ["R", "OFF", "V", "開會", "0", "O", "●"]:
                        bg_vacations[name_b][d] = "R"
                    elif val in ["D", "E", "N"]:
                        bg_vacations[name_b][d] = val
        
        st.success(f"✅ 已辨識 {len(staff_data)} 位人員，預班表資料已同步。")

        # --- 3. 保留核對區 (這部分會顯示在網頁上) ---
        st.subheader("⚙️ 排班銜接核對 (請確認權限與連班天數)")
        st.info("系統已自動帶入檔案 A 的初始值，如有需要請修改：")
        
        cols = st.columns(4)
        final_perms = {}
        final_cont_days = {}
        final_history = {}
        
        for i, s in enumerate(staff_data):
            with cols[i % 4]:
                st.write(f"👤 **{s['display']}**")
                # 權限核對
                final_perms[s['id']] = st.text_input("權限", value=s['perm'], key=f"p_{s['id']}")
                # 連班天數核對 (讓你可以手動輸入前面已經上幾天了)
                final_cont_days[s['id']] = st.number_input("已連班天數", 0, 6, 0, key=f"c_{s['id']}")
                # 紀錄前一天的班別 (隱藏處理，用於演算)
                final_history[s['id']] = s['last_day']

        # --- 4. 自動排班運算 ---
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {sid: [""] * num_days for sid in sids}
            
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                # A. 先處理預約假與背景假別
                for sid in sids:
                    v_val = bg_vacations[sid][d]
                    if v_val in ["D", "E", "N"]:
                        res[sid][d] = v_val
                        target[v_val] -= 1
                        pool.remove(sid)
                    elif v_val == "R":
                        res[sid][d] = "off"
                        pool.remove(sid)
                    else:
                        # 處理前一天是大夜 (N) 的銜接：隔天必須休假 (v)
                        prev = res[sid][d-1] if d > 0 else final_history[sid]
                        if prev == "N":
                            res[sid][d] = "v"
                            pool.remove(sid)
                
                # B. 分配人力
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in final_perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop()
                            res[chosen][d] = shift
                            pool.remove(chosen)
                
                for s in pool: res[s][d] = "off"
            
            st.subheader("🎉 最終排班結果")
            final_df = pd.DataFrame(res).T
            final_df.index = [displays[sid] for sid in sids]
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_df.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Result_Final.xlsx")

    except Exception as e:
        st.error(f"執行出錯: {e}")
else:
    st.info("👋 請上傳檔案 A 與 檔案 B 以開始核對銜接狀況。")
