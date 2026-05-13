import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-獨立核對版", layout="wide")

# --- 1. 核心解析邏輯 (背景作業) ---
def get_staff_list(file):
    df = pd.read_excel(file, header=None)
    staff_list = []
    # 根據你的 Excel 結構，從第 3 列 (Index 2) 開始抓取
    for i in range(2, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        if name in ["", "nan", "None"] or "星期" in name: continue
            
        sid = re.sub(r'[\s\u3000]', '', name)
        staff_list.append({
            "id": sid,
            "display": f"{no} {name}".strip(),
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": "off" # 預設銜接為休假
        })
    return staff_list

st.title("🏥 2F 護理排班系統 (13+1 全員核對版)")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b:
    try:
        # 背景作業：掃描名單與預排班
        all_staff = get_staff_list(file_a)
        sids = [s['id'] for s in all_staff]
        
        df_b = pd.read_excel(file_b, header=None)
        bg_vacation = {sid: [""] * num_days for sid in sids}
        
        # 全自動後台掃描填寫
        for i in range(len(df_b)):
            b_name = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            if b_name in bg_vacation:
                for d in range(num_days):
                    val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                    if val in ["R", "OFF", "V", "開會", "0", "●"]: bg_vacation[b_name][d] = "R"
                    elif val in ["D", "E", "N"]: bg_vacation[b_name][d] = val

        st.success(f"✅ 已辨識 {len(all_staff)} 位人員 (13位正職 + 半職)，預排班已自動對齊。")

        # --- 2. 獨立核對區 (你要求保留的部分) ---
        st.subheader("⚙️ 人員權限與銜接天數核對")
        st.write("請分別確認每位人員的狀況：")
        
        final_perms = {}
        final_cont_days = {}
        
        # 使用 columns 讓每個人分開顯示
        cols = st.columns(4) 
        for i, s in enumerate(all_staff):
            sid = s['id']
            with cols[i % 4]:
                st.container(border=True).markdown(f"👤 **{s['display']}**")
                final_perms[sid] = st.text_input("排班權限", value=s['perm'], key=f"p_{sid}")
                final_cont_days[sid] = st.number_input("起始連班", 0, 6, 0, key=f"c_{sid}")

        # --- 3. 啟動排班 ---
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {sid: [""] * num_days for sid in sids}
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                # A. 套用背景掃描到的假
                for sid in sids:
                    v = bg_vacation[sid][d]
                    if v in ["D", "E", "N"]:
                        res[sid][d] = v; target[v] -= 1; pool.remove(sid)
                    elif v == "R":
                        res[sid][d] = "off"; pool.remove(sid)
                
                # B. 分配其餘人力
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in final_perms[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            c = qualified.pop(); res[c][d] = shift; pool.remove(c)
                for s in pool: res[s][d] = "off"

            st.success("🎉 排班計算完成！")
            final_df = pd.DataFrame(res).T
            final_df.index = [s['display'] for s in all_staff]
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_df.to_excel(w)
            st.download_button("📥 下載 Excel 班表", out.getvalue(), "Final_Schedule.xlsx")

    except Exception as e:
        st.error(f"解析失敗: {e}")
else:
    st.info("👋 請上傳檔案 A 與 檔案 B。系統將自動掃描並為每個人建立獨立核對區。")
