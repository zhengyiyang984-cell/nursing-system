import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-序號姓名版", layout="wide")

def get_excel_data(file):
    # 讀取 Excel 且不設表頭，方便我們手動定位
    df = pd.read_excel(file, header=None)
    staff_data = {}
    
    # 根據你的檔案結構：
    # Index 0 (A 欄): 權限 (DE/N/E...)
    # Index 1 (B 欄): 序號 (半職1, 1, 2, 3...)
    # Index 2 (C 欄): 姓名/職級 (郭珍君PN2...)
    
    # 找出資料起始行（搜尋包含「姓名」的格子）
    start_row = 0
    for r in range(len(df)):
        if "姓名" in str(df.iloc[r, 2]):
            start_row = r
            break

    # 從標題列的下一列開始抓取
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 過濾無效行
        if name in ["", "nan", "None"] or "星期" in name:
            continue
            
        # 結合序號與姓名作為顯示名稱
        full_display = f"{no} {name}".strip()
        # sid 作為內部比對碼（移除所有空白）
        sid = re.sub(r'[\s\u3000\n\r\t]', '', name)
        
        staff_data[sid] = {
            "display_name": full_display,
            "perm": perm if perm != "NAN" else "DEN"
        }
    return staff_data, start_row

st.title("🏥 2F 護理排班系統 (序號+姓名辨識版)")

with st.sidebar:
    st.header("⚙️ Excel 匯入")
    num_days = st.slider("本月天數", 28, 31, 30)
    file_a = st.file_uploader("1. 上傳【班表】Excel (檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】Excel (檔案 B)", type=["xlsx"])

if file_a:
    try:
        staff_configs, start_row = get_excel_data(file_a)
        sids = list(staff_configs.keys())
        display_names = [staff_configs[s]["display_name"] for s in sids]
        
        if not sids:
            st.error("❌ 抓不到人員資料，請確認 Excel 的 C 欄是否有姓名。")
            st.stop()

        st.success(f"✅ 已成功載入 {len(sids)} 位人員 (含序號)")

        # 初始化預約表格
        if 'v_df' not in st.session_state or len(st.session_state.v_df) != len(sids):
            st.session_state.v_df = pd.DataFrame("", index=display_names, columns=[f"{i+1}日" for i in range(num_days)])

        # 同步檔案 B
        if file_b:
            if st.button("🔄 同步預班表 (檔案 B) 的假別", type="primary", use_container_width=True):
                df_b = pd.read_excel(file_b, header=None)
                new_v_df = st.session_state.v_df.copy()
                
                # 遍歷檔案 B 找人名比對
                for i in range(len(df_b)):
                    b_name = str(df_b.iloc[i, 2]).strip()
                    b_sid = re.sub(r'[\s\u3000\n\r\t]', '', b_name)
                    
                    if b_sid in sids:
                        target_display = staff_configs[b_sid]["display_name"]
                        # 日期從第 4 欄 (Index 3) 開始
                        for d in range(num_days):
                            val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                            if val in ["R", "OFF", "V", "開會", "0"]: new_v_df.loc[target_display, f"{d+1}日"] = "R"
                            elif val in ["D", "E", "N"]: new_v_df.loc[target_display, f"{d+1}日"] = val
                st.session_state.v_df = new_v_df
                st.toast("✅ 預約假已同步！")

        st.subheader("📅 預約假確認 (第一欄為 序號+姓名)")
        final_v_df = st.data_editor(st.session_state.v_df, use_container_width=True)

        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            # 排班邏輯 (4D/3E/2N)
            res = {s: [""] * num_days for s in sids}
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = sids.copy()
                random.shuffle(pool)
                
                for s in sids:
                    dn = staff_configs[s]["display_name"]
                    val = str(final_v_df.loc[dn, f"{d+1}日"]).strip().upper()
                    if val in ["D", "E", "N"]: res[s][d] = val; target[val] -= 1; pool.remove(s)
                    elif val == "R": res[s][d] = "R"; pool.remove(s)
                
                for shift in ["N", "E", "D"]:
                    qualified = [s for s in pool if shift in staff_configs[s]["perm"]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            c = qualified.pop(); res[c][d] = shift; pool.remove(c)
                for s in pool: res[s][d] = "off"
            
            st.success("🎉 排班完成！")
            f_df = pd.DataFrame(res).T
            f_df.index = display_names
            st.dataframe(f_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: f_df.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Schedule_Result.xlsx")

    except Exception as e:
        st.error(f"發生錯誤: {e}")
else:
    st.info("請先上傳檔案 A 以產生成員清單。")
