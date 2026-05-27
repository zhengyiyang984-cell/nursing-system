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

st.title("🏥 護理排班系統 (精準正職 4/3/2 核心完全版)")

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
        
          for d in range(num_days):
                    if not valid_month: break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    pool = [str(n) for n in full_time_names]
                    
                    # 1. 處理特殊休假與連班限制 (優先級最高)
                    for n in pool.copy():
                        # 5連班斷班
                        if d > 0 and streak_tracker[n] >= 5:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                        # 強制預排休 (R)
                        elif ironed_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                        # 戰術區間避開
                        elif d in critical_days and n in real_vacation_staff:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)

                    # 2. 核心分配：優先填入最難排的班 (基於權限長度排序)
                    pool.sort(key=lambda x: len(perm_final[x]))
                    
                    for shift in ["D", "E", "N"]:
                        # 找合適人選
                        candidates = [n for n in pool if shift in perm_final[n]]
                        candidates.sort(key=lambda x: streak_tracker[x]) # 避免過勞優先
                        
                        while target[shift] > 0 and candidates:
                            chosen = candidates.pop(0)
                            # 檢查班別銜接 (避免夜班接白班)
                            prev_1 = res[chosen][d-1] if d > 0 else history_final[chosen]
                            if d not in critical_days and shift == "D" and prev_1 in ["N", "E"]:
                                continue
                            
                            res[chosen][d] = shift
                            streak_tracker[chosen] += 1
                            pool.remove(chosen)
                            target[shift] -= 1
                    
                    # 3. 處理當天未被選中且無法補齊的人員 (強制休假)
                    for n in pool:
                        res[n][d] = "off"
                        total_off_counts[n] += 1
                    
                    # 4. 如果當天沒湊滿 4/3/2，該月直接失敗重算
                    if target["D"] > 0 or target["E"] > 0 or target["N"] > 0:
                        valid_month = False
            else:
                st.success(f"🎉 完美通關！全月每日人數均完美鎖死為『 4白班、3小夜、2大夜』的鋼鐵正職比例（半職外掛空降疊加）！")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                
                last_day_list, streak_list = [], []
                for n in final_df.index:
                    raw_last = next_month_history_row.get(str(n), "off")
                    last_day_list.append(raw_last if raw_last in ["D", "E", "N"] else "off")
                    streak_list.append(next_month_streak_row.get(str(n), 0))
                        
                final_df["系統接續_最後班別"] = last_day_list
                final_df["系統接續_連續天數"] = streak_list
                
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月精準班表")
                st.download_button(label="📥 下載最終精準 4/3/2 Excel 班表", data=out.getvalue(), file_name=f"2F_Perfect_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
