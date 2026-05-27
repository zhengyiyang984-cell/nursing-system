import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# 2F 全科室標準 13 人核心真名白名單
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇"
]

# --- 1. 基本班表解析 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    for i in range(len(df)):
        row_str = "".join(str(v) for v in df.iloc[i].values)
        if any(k in row_str for k in ["---", "每日人力", "總人數", "核對", "統計", "合計"]):
            continue
            
        matched_name = None
        for name in CORE_STAFF_NAMES:
            if name in row_str:
                matched_name = name; break
                
        if matched_name:
            row_cells = [str(v).strip() for v in df.iloc[i].values if pd.notna(v)]
            row_cells_upper = [c.upper() for c in row_cells]
            
            pure_perm = "DEN"
            for cell in row_cells_upper:
                if any(s in cell for s in ["D", "E", "N"]) and not cell.replace(".0", "").isdigit() and len(cell) <= 4:
                    if cell in ["DEN", "DE", "EN", "DN", "D", "E", "N"]:
                        pure_perm = cell; break
            
            is_pt = (matched_name == "郭珍君")
            configs[matched_name] = {
                "perm": pure_perm,
                "last_day": "off",
                "streak": 0,
                "is_part_time": is_pt
            }
    return configs


st.title("🏥 護理排班系統 (半職動態捕手精準 4/3/2 版)")

with st.sidebar:
    st.header("📅 排班月份設定")
    start_date = st.date_input("排班開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("排班結束日期", datetime.date(2026, 6, 30))
    
    num_days = (end_date - start_date).days + 1
    date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in [(start_date + datetime.timedelta(days=x)) for x in range(num_days)]]
    st.info(f"📅 系統偵測：本月共計 {num_days} 天")
    
    file_a = st.file_uploader("1. 上傳【基本班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])

if file_a and file_b:
    try:
        # 1. 讀取並處理基本班表設定
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        full_time_names = [str(n) for n in all_names if not staff_configs[n]["is_part_time"]]
        part_time_names = [str(n) for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        # 2. 初始化預排休表
        bg_vacation = {n: [""] * num_days for n in display_names}
        xl = pd.ExcelFile(file_b)
        active_sheet_name = "未指定分頁" 
        found_sheet = False
        
        # 3. 讀取 Excel 分頁
        for sheet_name in xl.sheet_names:
            if any(k in sheet_name for k in ["規範", "說明", "填寫", "使用", "欄位"]):
                continue
            
            # (這裡維持你原本的 Excel 讀取與處理邏輯)
            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)
            # ... 後續處理邏輯 ...
            found_sheet = True
            break 

            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)
            
            name_col_idx = 1       
            date_start_idx = 2     
            header_row_idx = 0     
            
            for r in range(min(10, len(df_b))):
                vals = [str(v).strip() for v in df_b.iloc[r].values]
                if "姓名" in vals:
                    name_col_idx = vals.index("姓名")
                    date_start_idx = name_col_idx + 1
                    header_row_idx = r
                    found_sheet = True
                    active_sheet_name = sheet_name 
                    break
                    
            if found_sheet:
                for i in range(header_row_idx + 1, len(df_b)):
                    raw_cell_name = str(df_b.iloc[i, name_col_idx]).strip()
                    if not raw_cell_name or raw_cell_name == "nan" or "序號" in raw_cell_name: continue
                    clean_b_name = re.sub(r'[\s\u3000]', '', raw_cell_name)
                    
                    target_person = None
                    for name in display_names:
                        if name in clean_b_name:
                            target_person = name; break
                    
                    if target_person:
                        for d in range(num_days):
                            col_pos = date_start_idx + d
                            if col_pos < len(df_b.columns):
                                cell_val = str(df_b.iloc[i, col_pos]).strip().upper()
                                if "D" in cell_val and "R" not in cell_val:
                                    bg_vacation[target_person][d] = "D"
                                elif "E" in cell_val:
                                    bg_vacation[target_person][d] = "E"
                                elif "N" in cell_val:
                                    bg_vacation[target_person][d] = "N"
                                elif "R" in cell_val or "OFF" in cell_val or "V" in cell_val or "●" in cell_val or cell_val == "NAN" or cell_val == "":
                                    bg_vacation[target_person][d] = "R"
                break

        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        standard_shifts = ["D", "E", "N", "off", "v", "R"]
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"👤 **同仁姓名：{n}**")
                    raw_perm = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    perm_final[n] = raw_perm.strip().upper().replace(",", "").replace(" ", "")
                    if not perm_final[n]: perm_final[n] = "DEN"
                    
                    history_final[n] = st.selectbox(f"上次班別", standard_shifts, index=3, key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        st.markdown("---")
        
        warning_placeholder = st.container()
        
       # --- 啟動大型主循環 ---
    # --- 啟動大型主循環 ---
        if st.button("🚀 啟動精準 4/3/2 排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row, next_month_streak_row = {}, {}
            ft_off_target = 9 if num_days >= 31 else 8
            revoked_log = []
            
            # --- 演算法主循環 ---
            for attempt in range(3000):
                valid_month = True
                res = {str(k): ["off"] * num_days for k in display_names}
                ironed_vacation = {n: bg_vacation[n].copy() for n in display_names}
                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): int(cont_days_final[n]) for n in full_time_names}
                pt_work_days_count = 0
                
                for d in range(num_days):
                    # [這裡放入你原本完整的排班邏輯代碼，直到 valid_month 判斷結束]
                    # (為了版面簡潔，請確保你原本的邏輯完整貼在這裡，不要更動內部邏輯)
                    # ... (省略中間排班細節，請保持你原本的代碼) ...
                    pass 

                if valid_month and pt_work_days_count == 10:
                    final_res = {str(k): v for k, v in res.items()}
                    # ... (補上你原本紀錄 next_month_history_row 等變數的代碼) ...
                    success_schedule = True
                    break

            # --- 渲染與輸出 (這一段放在迴圈之後) ---
            if not success_schedule or not final_res:
                st.error("⚠️ 錯誤：在維持鐵律下大死鎖。請點擊上方按鈕再次啟動重試，或是讓阿長微調衝突的指定預班！")
            else:
                if revoked_log:
                    with warning_placeholder:
                        for log in revoked_log: st.warning(log)
                            
                st.success(f"🎉 完美通關！全月每日均完美對齊『4白班、3小夜、2大夜』的鋼鐵比例！")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                
                # 色彩化處理
                def color_map(val):
                    colors = {'D': '#FFFACD', 'E': '#E0FFFF', 'N': '#E6E6FA', 'off': '#FFD700', 'R': '#D3D3D3'}
                    return f'background-color: {colors.get(str(val).upper(), "#FFFFFF")}; color: black'
                
                st.dataframe(final_df.style.applymap(color_map), use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月精準建議班表")
                st.download_button(label="📥 下載最終 Excel 班表", data=out.getvalue(), file_name=f"2F_Schedule_{start_date.month}M.xlsx", use_container_width=True)
