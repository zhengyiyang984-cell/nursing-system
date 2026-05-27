import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

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

# --- 2. 區塊循環排班演算法 ---
def schedule_part_time(num_days):
    for _ in range(1000):
        days = ["off"] * num_days
        available_patterns = [[2, 2, 2, 2, 2], [3, 3, 2, 2], [3, 2, 3, 2], [2, 3, 2, 3], [2, 2, 3, 3]]
        work_blocks = random.choice(available_patterns)
        random.shuffle(work_blocks) 
        
        current_idx = random.randint(0, 2)
        success = True
        for block in work_blocks:
            if current_idx + block > num_days:
                success = False; break
            for _ in range(block):
                if current_idx < num_days:
                    days[current_idx] = "D"
                    current_idx += 1
            current_idx += random.randint(2, 4)
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
    return ["off"] * num_days


st.title("🏥 護理排班系統 (滑動視窗動態修剪版)")

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
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        full_time_names = [n for n in all_names if not staff_configs[n]["is_part_time"]]
        part_time_names = [n for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        bg_vacation = {n: ["R"] * num_days for n in display_names}
        
        xl = pd.ExcelFile(file_b)
        active_sheet_name = "未指定分頁" # ⚡ 關鍵修正：在迴圈前先給予預設值，徹底封殺 UnboundLocalError
        found_sheet = False
        
        for sheet_name in xl.sheet_names:
            if any(k in sheet_name for k in ["規範", "說明", "填寫", "使用", "欄位"]):
                continue
                
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
                    active_sheet_name = sheet_name # ⚡ 精準賦值
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
                                if cell_val in ["D", "E", "N"]:
                                    if target_person not in part_time_names:
                                        bg_vacation[target_person][d] = cell_val
                                else:
                                    bg_vacation[target_person][d] = "R"
                break

        if len(display_names) > 0:
            st.success(f"✅ 成功辨識全科共 {len(display_names)} 位人員！已成功綁定假表分頁：【{active_sheet_name}】。")
        else:
            st.error("❌ 錯誤：無法從基本班表中讀取到任何護理同仁姓名，請確認班表格式！")

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
        if st.button("🚀 啟動滑動視窗排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row, next_month_streak_row = {}, {}
            ft_off_target = 9 if num_days >= 31 else 8
            
            for attempt in range(2500):
                valid_month = True
                res = {k: ["off"] * num_days for k in display_names}
                
                for pt_name in part_time_names: 
                    res[pt_name] = schedule_part_time(num_days)
                    
                total_off_counts = {n: 0 for n in full_time_names}
                streak_tracker = {n: 0 for n in full_time_names}
                
                for d in range(num_days):
                    if not valid_month: break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[n][d-1] == "off":
                                streak_tracker[n] = 0
                    
                    pool = [n for n in full_time_names]
                    
                    # 5連班斷班
                    for n in pool.copy():
                        if streak_tracker[n] >= 5:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                            
                    # 處理預約假
                    for n in pool.copy():
                        if bg_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                            
                    # 抬頭看明天 - 碎班防禦
                    for n in pool.copy():
                        prev_is_off = (res[n][d-1] == "off") if d > 0 else (history_final[n] == "off")
                        next_is_vacation = (bg_vacation[n][d+1] == "R") if d < (num_days - 1) else False
                        if prev_is_off and next_is_vacation:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)

                    # 填入指定預班
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[n]:
                                res[n][d] = v
                                target[v] -= 1
                                streak_tracker[n] += 1
                                pool.remove(n)
                            else:
                                valid_month = False
                    
                    if not valid_month: break
                    
                    random.shuffle(pool)
                    pool.sort(key=lambda x: (streak_tracker[x] > 0, total_off_counts[x]), reverse=True)
                    
                    # 分派 N -> E -> D
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in perm_final[n]:
                                prev_1 = res[n][d-1] if d > 0 else history_final[n]
                                if shift == "D" and prev_1 in ["N", "E"]: continue
                                if shift == "E" and prev_1 == "N"]: continue
                                qualified.append(n)
                                
                        for _ in range(max(0, target[shift])):
                            if qualified:
                                chosen = qualified.pop(0)
                                res[chosen][d] = shift
                                streak_tracker[chosen] += 1
                                pool.remove(chosen)
                            else:
                                valid_month = False; break
                        if not valid_month: break
                                
                    for n in pool:
                        res[n][d] = "off"
                        total_off_counts[n] += 1

                # 月底大驗證
                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] != ft_off_target: 
                            valid_month = False; break
                        
                        days_str = "".join(["0" if res[n][x] == "off" else "1" for x in range(num_days)])
                        if "010" in days_str or days_str.startswith("10") or days_str.endswith("01"):
                            valid_month = False; break

                if valid_month:
                    final_res = {k: v for k, v in res.items()}
                    for n in display_names:
                        next_month_history_row[n] = res[n][-1]
                        s_count = 0
                        for cell_b in reversed(res[n]):
                            if cell_b in ["D", "E", "N"]: s_count += 1
                            else: break
                        next_month_streak_row[n] = s_count
                    success_schedule = True
                    break
            
            if not success_schedule or not final_res:
                st.error("⚠️ 滑動視窗動態匹配失敗。請確認每日空白人數少於 4 人後再次點擊啟動！")
            else:
                st.success(f"🎉 成功！【滑動視窗動態修剪法】已完美產出 {start_date.month} 月份區塊班表。")
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                final_df["系統接續_最後班別"] = [next_month_history_row[n] for n in display_names]
                final_df["系統接續_連續天數"] = [next_month_streak_row[n] for n in display_names]
                
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月動態建議班表")
                st.download_button(label="📥 下載滑動視窗版 Excel 班表", data=out.getvalue(), file_name=f"2F_SlidingWindow_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
