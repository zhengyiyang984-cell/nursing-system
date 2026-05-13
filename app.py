import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-13人獨立核對版", layout="wide")

# --- 1. 背景解析邏輯 ---
def get_staff_list(file):
    df = pd.read_excel(file, header=None)
    staff_list = []
    # 根據你的 Excel，從第 3 列 (Index 2) 開始抓取
    for i in range(2, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 過濾雜訊列
        if name in ["", "nan", "None", "姓名/職級"] or "星期" in name or "ALL" in name: 
            continue
            
        sid = re.sub(r'[\s\u3000]', '', name)
        staff_list.append({
            "id": sid,
            "display": f"{no} {name}".strip(),
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": "off" 
        })
    return staff_list

st.title("🏥 2F 護理排班系統 (極簡獨立核對)")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b:
    try:
        # 背景作業：掃描名單與預排班內容
        all_staff = get_staff_list(file_a)
        sids = [s['id'] for s in all_staff]
        
        df_b = pd.read_excel(file_b, header=None)
        bg_vacation = {sid: [""] * num_days for sid in sids}
        
        # 背景自動掃描檔案 B 的內容
        for i in range(len(df_b)):
            b_name_raw = str(df_b.iloc[i, 2]).strip()
            sid_b = re.sub(r'[\s\u3000]', '', b_name_raw)
            if sid_b in bg_vacation:
                for d in range(num_days):
                    val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    # 符號自動轉換
                    if val in ["R", "OFF", "V", "開會", "0", "O", "●"]: 
                        bg_vacation[sid_b][d] = "R"
                    elif val in ["D", "E", "N"]: 
                        bg_vacation[sid_b][d] = val

        st.success(f"✅ 已辨識 {len(all_staff)} 位人員，預班表資料已在背景完成同步。")

        # --- 2. 獨立核對區 (每個人分開顯示) ---
        st.subheader("⚙️ 每位護理人員狀態核對")
        st.info("系統已自動掃描預班表。請確認下方每人的排班權限與起始狀態：")
        
        final_perms = {}
        final_cont_days = {}
        
        # 設置每排 4 個人，讓 14 個人整齊排列
        rows_to_display = [all_staff[i:i+4] for i in range(0, len(all_staff), 4)]
        
        for row_staff in rows_to_display:
            cols = st.columns(4)
            for idx, s in enumerate(row_staff):
                sid = s['id']
                with cols[idx]:
                    # 使用 container 做出獨立的小區塊
                    with st.container(border=True):
                        st.markdown(f"👤 **{s['display']}**")
                        final_perms[sid] = st.text_input("權限", value=s['perm'], key=f"p_{sid}")
                        final_cont_days[sid] = st.number_input("連班天數", 0, 6, 0, key=f"c_{sid}")

        # --- 3. 執行排班 ---
        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            schedule_results = {sid: [""] * num_days for sid in sids}
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                # A. 優先處理背景抓到的預排假
                for sid in sids:
                    v = bg_vacation[sid][d]
                    if v in ["D", "E", "N"]:
                        schedule_results[sid][d] = v
                        target[v] -= 1
                        pool.remove(sid)
                    elif v == "R":
                        schedule_results[sid][d] = "off"
                        pool.remove(sid)
                
                # B. 分配其餘人力
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in final_perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            c = qualified.pop()
                            schedule_results[c][d] = shift
                            pool.remove(c)
                
                for s in pool:
                    schedule_results[s][d] = "off"

            st.success("🎉 排班完成！")
            
            # --- 4. 結果輸出 ---
            final_df = pd.DataFrame(schedule_results).T
            final_df.index = [s['display'] for s in all_staff]
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_df.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Schedule_Final.xlsx")

    except Exception as e:
        st.error(f"解析發生錯誤: {e}")
else:
    st.info("👋 請在左側上傳【班表 A】與【預班表 B】。")
