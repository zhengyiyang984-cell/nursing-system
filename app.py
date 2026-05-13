import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-自動讀取版", layout="wide")

# --- 核心邏輯：從 Excel 自動抓取所有欄位 ---
def get_staff_auto_config(df, num_days):
    staff_data = {}
    # 尋找資料起始行 (通常姓名在第 3 欄，ID/班別在第 2 欄)
    # 我們根據關鍵字 "姓名" 或 "職級" 來定位，或者直接掃描含有有效資料的列
    for i, row in df.iterrows():
        # 嘗試抓取：第 1 欄是權限(DE/N/E)，第 2 欄是姓名/職級
        perm_raw = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else ""
        name_raw = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        
        # 過濾掉標題列，只抓取真正的護理人員列
        if any(p in perm_raw for p in ["D", "E", "N"]) and name_raw != "" and "姓名" not in name_raw:
            # 1. 取得乾淨的姓名 (去掉 PN2, PN3 等字眼)
            clean_name = name_raw.split('P')[0].strip()
            
            # 2. 自動偵測上次班別 (從日期欄位之前的最後一個有效格子抓取)
            # 假設第 3 欄 (index 2) 是上月最後一天的班別
            last_shift = str(row.iloc[2]).strip().upper() if pd.notna(row.iloc[2]) else "OFF"
            if last_shift not in ["D", "E", "N", "OFF", "V", "R"]: last_shift = "OFF"
            
            # 3. 抓取預約假/固定班 (從第 4 欄開始，對應 1~31 日)
            v_list = []
            for d in range(num_days):
                col_idx = d + 3
                val = str(row.iloc[col_idx]).strip().upper() if col_idx < len(row) else ""
                if val in ["OFF", "V", "R", "開會"]: v_list.append("R")
                elif val in ["D", "E", "N"]: v_list.append(val)
                else: v_list.append("")
            
            staff_data[clean_name] = {
                "perm": perm_raw,
                "last_day": last_shift.lower() if last_shift in ["OFF", "V"] else last_shift,
                "pre_set": v_list
            }
    return staff_data

st.title("🏥 2F 護理自動排班系統 (免打字自動讀取版)")

with st.sidebar:
    st.header("⚙️ 第一步：上傳檔案")
    num_days = st.slider("設定本月天數", 28, 31, 30)
    
    # 直接上傳一個檔案即可，系統會自動分析
    uploaded_file = st.file_uploader("請上傳包含姓名與權限的班表 (Excel/CSV)", type=["xlsx", "csv"])
    
    all_configs = {}
    if uploaded_file:
        try:
            # 支援 Excel 或 CSV 讀取
            if uploaded_file.name.endswith('.csv'):
                df_raw = pd.read_csv(uploaded_file, header=None)
            else:
                df_raw = pd.read_excel(uploaded_file, header=None)
            
            all_configs = get_staff_auto_config(df_raw, num_days)
            if all_configs:
                st.success(f"✅ 成功辨識出 {len(all_configs)} 位成員！")
        except Exception as e:
            st.error(f"檔案讀取失敗，請確認格式。錯誤：{e}")

if not all_configs:
    st.info("💡 請在左側上傳 Excel，系統會自動帶入所有人名與設定。")
    st.stop()

# --- 第二步：自動顯示讀取結果 ---
st.subheader("📋 系統自動讀取結果 (無需手動輸入)")
names = list(all_configs.keys())

# 將資訊呈現給使用者確認
cols = st.columns(4)
final_perms = {}
final_hist = {}
for i, n in enumerate(names):
    with cols[i % 4]:
        st.info(f"👤 **{n}**\n\n權限：`{all_configs[n]['perm']}`\n\n上次：`{all_configs[n]['last_day']}`")
        # 雖然是自動讀取，但保留隱藏的變數供後續運算
        final_perms[n] = all_configs[n]['perm']
        final_hist[n] = all_configs[n]['last_day']

# --- 第三步：預約假表格 (自動填入 Excel 裡的 R 與 DEN) ---
st.subheader("📅 預約假與指定班別 (已自動從 Excel 帶入)")
dates = [f"{i+1}日" for i in range(num_days)]
init_v_df = pd.DataFrame([all_configs[n]["pre_set"] for n in names], index=names, columns=dates)

# 使用編輯器，讓使用者如果有臨時變動還能改
edited_v_df = st.data_editor(init_v_df, use_container_width=True)

# --- 第四步：一鍵排班 ---
if st.button("🚀 開始自動排班", type="primary", use_container_width=True):
    res = {n: [""] * num_days for n in names}
    
    for d in range(num_days):
        target = {"D": 4, "E": 3, "N": 2}
        pool = names.copy()
        random.shuffle(pool)
        
        # 優先權 1：處理預約假與固定班
        for n in names:
            val = str(edited_v_df.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val == "R":
                res[n][d] = "R"; pool.remove(n)
            else:
                # 處理大夜銜接休假
                prev = res[n][d-1] if d > 0 else final_hist[n]
                if prev == "N":
                    res[n][d] = "v"; pool.remove(n)

        # 優先權 2：補滿人力
        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in final_perms[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop()
                    res[staff][d] = shift; pool.remove(staff)
        
        # 剩下的人排休
        for n in pool: res[n][d] = "off"

    # 顯示結果
    final_df = pd.DataFrame(res).T
    st.success("🎉 排班完成！")
    
    def style_v(v):
        c = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2'}
        return f'background-color: {c.get(v, "transparent")}; color: black; font-weight: bold'
    
    st.dataframe(final_df.style.map(style_v), use_container_width=True)
    
    # 下載
    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        final_df.to_excel(writer, sheet_name='2F班表')
    st.download_button("📥 下載最終 Excel 班表", out.getvalue(), "Final_Schedule.xlsx")
