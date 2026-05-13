import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-最終修正版", layout="wide")

# --- 1. 核心解析邏輯 ---
def get_excel_data(file):
    # 直接讀取 Excel，不設標題
    df = pd.read_excel(file, header=None)
    staff_list = []
    
    # 尋找「姓名」兩字所在的行
    start_row = 0
    for r in range(min(10, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str:
            start_row = r
            break

    # 從標題下一行開始抓
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        # A欄:權限, B欄:序號, C欄:姓名
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        if name == "" or name == "nan" or "星期" in name: continue
            
        # 建立顯示用的標籤 (序號+姓名)
        display_label = f"{no} {name}".strip()
        # 建立比對用的ID (純姓名)
        pure_id = re.sub(r'[\s\u3000\n\r\t]', '', name)
        
        staff_list.append({
            "id": pure_id,
            "display": display_label,
            "perm": perm if perm != "NAN" else "DEN"
        })
    return staff_list

st.title("🏥 2F 護理排班系統 (最終修正版)")

with st.sidebar:
    st.header("⚙️ 1. 匯入檔案")
    num_days = st.slider("排班天數", 28, 31, 31)
    file_a = st.file_uploader("上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a:
    try:
        staff_data = get_excel_data(file_a)
        if not staff_data:
            st.error("找不到人員資料，請確認 Excel 的 C 欄是否有姓名。")
            st.stop()

        # 準備顯示用的清單
        sids = [s['id'] for s in staff_data]
        display_names = [s['display'] for s in staff_data]
        perms_map = {s['id']: s['perm'] for s in staff_data}
        label_map = {s['id']: s['display'] for s in staff_data}

        # --- 強制刷新機制 ---
        # 如果人名清單變了，就重設 session_state
        if 'current_staff_ids' not in st.session_state or st.session_state.current_staff_ids != sids:
            st.session_state.current_staff_ids = sids
            st.session_state.v_df = pd.DataFrame("", index=display_names, columns=[f"{i+1}日" for i in range(num_days)])

        st.success(f"✅ 已成功辨識 {len(staff_data)} 位護理人員")

        # --- 同步檔案 B ---
        if file_b:
            if st.button("🔄 同步預班表假別", type="primary", use_container_width=True):
                df_b = pd.read_excel(file_b, header=None)
                # 建立一個暫存的 DataFrame 來更新
                temp_df = st.session_state.v_df.copy()
                
                for i in range(len(df_b)):
                    raw_b_name = str(df_b.iloc[i, 2]).strip()
                    b_id = re.sub(r'[\s\u3000\n\r\t]', '', raw_b_name)
                    
                    if b_id in sids:
                        row_label = label_map[b_id]
                        for d in range(num_days):
                            val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                            if val in ["R", "OFF", "V", "開會", "0"]: temp_df.loc[row_label, f"{d+1}日"] = "R"
                            elif val in ["D", "E", "N"]: temp_df.loc[row_label, f"{d+1}日"] = val
                st.session_state.v_df = temp_df
                st.toast("預約資料已填入表格！")

        # --- 表格編輯區 ---
        st.subheader("📅 2. 預約假確認 (第一欄應為 序號+姓名)")
        edited_v_df = st.data_editor(st.session_state.v_df, use_container_width=True)

        # --- 排班按鈕 ---
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {sid: [""] * num_days for sid in sids}
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                # 抓取表格資料
                for sid in sids:
                    dn = label_map[sid]
                    val = str(edited_v_table.loc[dn, f"{d+1}日"]).strip().upper() if 'edited_v_table' in locals() else str(edited_v_df.loc[dn, f"{d+1}日"]).strip().upper()
                    if val in ["D", "E", "N"]:
                        res[sid][d] = val; target[val] -= 1; pool.remove(sid)
                    elif val == "R":
                        res[sid][d] = "R"; pool.remove(sid)

                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in perms_map[s]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            c = qualified.pop(); res[c][d] = shift; pool.remove(c)
                for s in pool: res[s][d] = "off"
            
            st.success("🎉 排班完成！")
            final_res = pd.DataFrame(res).T
            final_res.index = display_names
            st.dataframe(final_res, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_res.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Result.xlsx")

    except Exception as e:
        st.error(f"系統出錯: {e}")
else:
    st.info("請先上傳檔案 A。")
