import streamlit as st

import pandas as pd

import random

from io import BytesIO

import datetime

import re



st.set_page_config(page_title="2F 護理排班系統", layout="wide")



WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]



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

            configs[matched_name] = {

                "perm": pure_perm,

                "last_day": "off",

                "streak": 0,

                "is_part_time": (matched_name == "郭珍君")

            }

    return configs



st.title("🏥 護理排班系統")



with st.sidebar:

    st.header("📅 排班月份設定")

    start_date = st.date_input("排班開始日期", datetime.date(2026, 6, 1))

    end_date = st.date_input("排班結束日期", datetime.date(2026, 6, 30))

    

    num_days = (end_date - start_date).days + 1

    date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in [(start_date + datetime.timedelta(days=x)) for x in range(num_days)]]

    file_a = st.file_uploader("1. 上傳【基本班表】", type=["xlsx"])

    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])



if file_a and file_b:

    try:

        staff_configs = get_staff_configs(file_a)

        all_names = list(staff_configs.keys())

        full_time_names = [str(n) for n in all_names if not staff_configs[n]["is_part_time"]]

        part_time_names = [str(n) for n in all_names if staff_configs[n]["is_part_time"]]

        display_names = full_time_names + part_time_names



        bg_vacation = {n: [""] * num_days for n in display_names}

        xl = pd.ExcelFile(file_b)

        active_sheet_name = "未指定分頁" 

        found_sheet = False

        

        for sheet_name in xl.sheet_names:

            if any(k in sheet_name for k in ["規範", "說明", "填寫", "使用", "欄位"]):

                continue

            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)

            name_col_idx, date_start_idx, header_row_idx = 1, 2, 0

            for r in range(min(10, len(df_b))):

                vals = [str(v).strip() for v in df_b.iloc[r].values]

                if "姓名" in vals:

                    name_col_idx = vals.index("姓名")

                    date_start_idx = name_col_idx + 1

                    header_row_idx = r

                    found_sheet = True; break

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

                                if "D" in cell_val and "R" not in cell_val: bg_vacation[target_person][d] = "D"

                                elif "E" in cell_val: bg_vacation[target_person][d] = "E"

                                elif "N" in cell_val: bg_vacation[target_person][d] = "N"

                                else: bg_vacation[target_person][d] = "R"

                break



        st.subheader("⚙️ 核對權限與銜接狀態")

        history_final, perm_final, cont_days_final = {}, {}, {}

        cols = st.columns(4)

        for i, n in enumerate(display_names):

            with cols[i % 4]:

                with st.container(border=True):

                    st.markdown(f"👤 **{n}**")

                    raw_perm = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")

                    perm_final[n] = raw_perm.strip().upper().replace(",", "").replace(" ", "")

                    if not perm_final[n]: perm_final[n] = "DEN"

                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], index=3, key=f"h_{n}")

                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")



        st.markdown("---")

        warning_placeholder = st.container()

        

        if st.button("🚀 啟動排班", type="primary", use_container_width=True):
            # 預先計算每日最大可用人力
            daily_available = [0] * num_days
            for d in range(num_days):
                for n in full_time_names:
                    if bg_vacation[n][d] != "R": daily_available[d] += 1
            
            # 檢查極端缺口
            shortage_days = [d+1 for d, count in enumerate(daily_available) if count < 9]
            if shortage_days:
                st.warning(f"⚠️ 警告：以下日期正職人力不足 9 人 (無法滿足 4/3/2)：{shortage_days}，系統將盡力補足但不保證完美。")

            # 增加一個變數儲存「最接近」的結果
            best_res = None
            min_gap = 999 

            for attempt in range(10000): # 縮減次數以優化回應速度
                # ... [保留原本的循環邏輯，但在結束時計算 gap]
                
                current_gap = 0
                # 計算當前方案與 4/3/2 的誤差
                # ... (在 validation 階段加入 current_gap 計算)
                
                if current_gap < min_gap:
                    min_gap = current_gap
                    best_res = {k: v[:] for k, v in res.items()}
                
                if min_gap == 0: break # 完美解

            if best_res:
                if min_gap > 0:
                    st.error(f"⚠️ 系統已運算完畢，但無法達到完美 4/3/2 配置，誤差值為 {min_gap}。")
                else:
                    st.success("🎉 完美通關！")
                except Exception as e:
                # 當排班邏輯出錯時，顯示錯誤訊息給使用者
                st.error(f"排班運算過程中發生錯誤: {e}")
                # 繪製表格邏輯...
 

