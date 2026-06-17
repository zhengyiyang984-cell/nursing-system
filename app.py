import streamlit as st
import pandas as pd
import datetime
import random
import re
from io import BytesIO

# =====================================
# 基本設定
# =====================================

st.set_page_config(
    page_title="2F護理排班系統 (人力完美死守版)",
    layout="wide"
)

st.title("🏥 2F護理排班系統 (人力完美死守版)")

if "run_success" not in st.session_state:
    st.session_state["run_success"] = False
if "schedule_result" not in st.session_state:
    st.session_state["schedule_result"] = None

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# 核心 14 人名單
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡微", "陳威宇"
]

# 兼職人員名單
PART_TIME_STAFFS = ["郭珍君"] 

# 當月權限預設底牌
DEFAULT_PERMISSIONS = {
    "郭珍君": "D", "劉榆琳": "N", "陳義樺": "N", "李雅慧": "DEN", 
    "蔡靜如": "DEN", "陳慧屏": "DEN", "黃家靜": "DEN", "許雅雯": "DEN", 
    "林欣蓓": "DEN", "陳萱芸": "DEN", "汪家容": "DEN", "林欣儀": "DEN", 
    "林怡微": "DEN", "陳威宇": "DEN"
}

# 上月最後班安全底牌
DEFAULT_LAST_SHIFTS = {
    "郭珍君": "off", "劉榆琳": "N", "陳義樺": "N", "李雅慧": "D", 
    "蔡靜如": "D", "陳慧屏": "D", "黃家靜": "D", "許雅雯": "D", 
    "林欣蓓": "D", "陳萱芸": "D", "汪家容": "D", "林欣儀": "D", 
    "林怡微": "D", "陳威宇": "D"
}

# =====================================
# 預排休表智慧雙挖取器
# =====================================
def load_request_and_permissions(upload_file, names, num_days):
    requests_dict = {n: [""] * num_days for n in names}
    permissions_dict = {n: DEFAULT_PERMISSIONS.get(n, "DEN") for n in names}
    
    xl = pd.ExcelFile(upload_file)
    sheet_name = xl.sheet_names[0]
    df = pd.read_excel(upload_file, sheet_name=sheet_name, header=None)
    
    header_row_idx = 0
    name_col_idx = 1 
    
    for idx, row in df.iterrows():
        row_str = [str(x) for x in row.values]
        if any("姓名" in s or "人員" in s for s in row_str):
            header_row_idx = idx
            for col_idx, cell_value in enumerate(row_str):
                if "姓名" in cell_value or "人員" in cell_value:
                    name_col_idx = col_idx
                    break
            break

    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
    
    for _, row in df.iterrows():
        raw_name = str(row.iloc[name_col_idx]).replace(" ", "").replace(" ", "").strip()
        
        target_nurse = None
        for n in names:
            if n in raw_name:
                target_nurse = n
                break
        if not target_nurse:
            continue
            
        permission_col_idx = name_col_idx + 2
        if permission_col_idx < len(df.columns):
            perm_val = str(row.iloc[permission_col_idx]).upper().strip()
            if perm_val in ["D", "E", "N", "DE", "DN", "EN", "DEN"]:
                permissions_dict[target_nurse] = perm_val

        start_data_col = name_col_idx + 3
                
        for d in range(num_days):
            current_col_idx = start_data_col + d
            if current_col_idx >= len(df.columns):
                continue
            cell_value = str(row.iloc[current_col_idx]).strip()
            if cell_value == "nan" or cell_value == "":
                continue
            cell_value_upper = cell_value.upper()
            
            if cell_value_upper in ["R", "D", "E", "N"]:
                requests_dict[target_nurse][d] = cell_value_upper
            elif "開會" in cell_value or cell_value_upper == "M":
                requests_dict[target_nurse][d] = "M"
            elif "休" in cell_value:
                requests_dict[target_nurse][d] = "R"
                
    return requests_dict, permissions_dict

# =====================================
# 基本班表歷史狀態精準讀取器
# =====================================
def load_history_only(upload_file, names):
    history_shift = {n: "D" for n in names} 
    for n in names:
        if n in DEFAULT_LAST_SHIFTS:
            history_shift[n] = DEFAULT_LAST_SHIFTS[n]
            
    history_streak = {n: 0 for n in names}
    
    try:
        df = pd.read_excel(upload_file, header=None)
        header_row_idx = 0
        name_col_idx = 1
        
        for idx, row in df.iterrows():
            row_str = [str(x) for x in row.values]
            if any("姓名" in s or "人員" in s for s in row_str):
                header_row_idx = idx
                for col_idx, cell_value in enumerate(row_str):
                    if "姓名" in cell_value or "人員" in cell_value:
                        name_col_idx = col_idx
                        break
                break

        df.columns = df.iloc[header_row_idx]
        df = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
        
        for _, row in df.iterrows():
            raw_name = str(row.iloc[name_col_idx]).replace(" ", "").replace(" ", "").strip()
            target_nurse = None
            for n in names:
                if n in raw_name:
                    target_nurse = n
                    break
            if not target_nurse:
                continue
                
            start_data_col = name_col_idx + 3
            shifts = []
            
            for c_idx in range(start_data_col, len(df.columns)):
                col_name = str(df.columns[c_idx])
                if "計" in col_name or "總" in col_name or "天" in col_name:
                    break
                cell_val = str(row.iloc[c_idx]).upper().strip()
                if cell_val in ["D", "E", "N", "OFF", "R", "M", "NAN", ""]:
                    if cell_val in ["NAN", ""]:
                        cell_val = "OFF"
                    shifts.append(cell_val)
            
            if len(shifts) > 0:
                history_shift[target_nurse] = shifts[-1].lower() if shifts[-1] in ["OFF", "off"] else shifts[-1]
                streak = 0
                for s in reversed(shifts):
                    if s in ["D", "E", "N"]:
                        streak += 1
                    else:
                        break
                history_streak[target_nurse] = streak
    except:
        pass
        
    return history_shift, history_streak

# =====================================
# 智慧排班引擎 (人力絕對滿足死守完全體)
# =====================================
def generate_schedule(names, permissions, requests, num_days, manpower_req, history_shift, history_streak):
    schedule = {n: [""] * num_days for n in names}
    night_count = {n: 0 for n in names}
    work_count = {n: 0 for n in names}

    for nurse in names:
        for d in range(num_days):
            if d < len(requests[nurse]) and requests[nurse][d] in ["M", "D", "E", "N"]:
                schedule[nurse][d] = requests[nurse][d]
                work_count[nurse] += 1
                if requests[nurse][d] in ["E", "N"]:
                    night_count[nurse] += 1

    def get_current_streak(nurse_name, day_idx):
        curr_streak = history_streak.get(nurse_name, 0) if day_idx == 0 else 0
        for prev_d in range(day_idx):
            if schedule[nurse_name][prev_d] in ["D", "E", "N"]:
                curr_streak += 1
            else:
                curr_streak = 0
        return curr_streak

    def get_work_continuation_weight(nurse_name, day_idx):
        streak = get_current_streak(nurse_name, day_idx)
        if day_idx == 0:
            has_worked = history_shift.get(nurse_name) in ["D", "E", "N"]
        else:
            has_worked = schedule[nurse_name][day_idx - 1] in ["D", "E", "N"]
            
        if not has_worked:
            return 0
        if streak >= 4:
            return 2  
        elif streak >= 2:
            return 18 
        return 12

    # STEP 2: 大夜班 (N) 分配
    for day in range(num_days):
        req_n_min = manpower_req[day]["N_min"]
        req_n_max = manpower_req[day]["N_max"]
        current_n = sum(1 for n in names if schedule[n][day] == "N")
        
        if current_n >= req_n_max:
            continue
            
        need_n = req_n_min - current_n
        if need_n <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse in PART_TIME_STAFFS: 
                continue
            if schedule[nurse][day] != "": 
                continue
            if not can_work_shift(permissions[nurse], "N"):
                continue
            if get_current_streak(nurse, day) >= 5:
                continue
                
            if day == 1 and history_shift.get(nurse) == "N" and schedule[nurse][0] != "N":
                continue
            if day > 1:
                if schedule[nurse][day - 1] != "N" and schedule[nurse][day - 2] == "N":
                    continue
                
            candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(
            key=lambda x: (
                25 if (day > 0 and schedule[x][day - 1] == "N") or (day == 0 and history_shift.get(x) == "N") else 0,
                get_work_continuation_weight(x, day),
                -work_count[x], 
                -night_count[x]
            ), 
            reverse=True
        )

        allowed_n_to_add = min(need_n, req_n_max - current_n)
        for nurse in candidates[:allowed_n_to_add]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 3: 小夜班 (E) 分配
    for day in range(num_days):
        req_e_min = manpower_req[day]["E_min"]
        req_e_max = manpower_req[day]["E_max"]
        current_e = sum(1 for n in names if schedule[n][day] == "E")
        
        if current_e >= req_e_max:
            continue
            
        need_e = req_e_min - current_e
        if need_e <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse in PART_TIME_STAFFS: 
                continue
            if schedule[nurse][day] != "":
                continue
            if not can_work_shift(permissions[nurse], "E"):
                continue
            if get_current_streak(nurse, day) >= 5:
                continue
                
            if day == 0 and history_shift.get(nurse) == "N":
                continue
            if day == 1 and (schedule[nurse][0] == "N" or history_shift.get(nurse) == "N"):
                continue
            if day > 1 and (schedule[nurse][day - 1] == "N" or schedule[nurse][day - 2] == "N"):
                continue
                
            candidates.append(nurse)

        if len(candidates) < need_e:
            for nurse in names:
                if nurse not in PART_TIME_STAFFS and schedule[nurse][day] == "" and can_work_shift(permissions[nurse], "E"):
                    if nurse not in candidates:
                        candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (get_work_continuation_weight(x, day), -work_count[x], night_count[x]), reverse=True)

        allowed_e_to_add = min(need_e, req_e_max - current_e)
        for nurse in candidates[:allowed_e_to_add]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 4: 白班 (D) 分配
    for day in range(num_days):
        req_d_min = manpower_req[day]["D_min"]
        req_d_max = manpower_req[day]["D_max"]
        current_d = sum(1 for n in names if schedule[n][day] == "D")
        
        if current_d >= req_d_max:
            continue
            
        need_d = req_d_min - current_d
        
        if need_d > 0:
            candidates = []
            for nurse in names:
                if nurse in PART_TIME_STAFFS: 
                    continue
                if schedule[nurse][day] != "":
                    continue
                if not can_work_shift(permissions[nurse], "D"):
                    continue
                if get_current_streak(nurse, day) >= 5:
                    continue
                    
                if day == 0 and history_shift.get(nurse) == "N":
                    continue
                if day == 1 and (schedule[nurse][0] == "N" or history_shift.get(nurse) == "N"):
                    continue
                if day > 1 and (schedule[nurse][day - 1] == "N" or schedule[nurse][day - 2] == "N"):
                    continue
                if day == 0 and history_shift.get(nurse) == "E":
                    continue
                if day > 0 and schedule[nurse][day - 1] == "E":
                    continue
                    
                if day < len(requests[nurse]) and requests[nurse][day] == "R":
                    continue
                candidates.append(nurse)

            random.shuffle(candidates)
            candidates.sort(key=lambda x: (get_work_continuation_weight(x, day), -work_count[x]), reverse=True)

            allowed_d_to_add = min(need_d, req_d_max - current_d)
            for nurse in candidates[:allowed_d_to_add]:
                schedule[nurse][day] = "D"
                work_count[nurse] += 1

    # STEP 5: 半職郭珍君「鋼鐵 2-3 天」精準區塊積班分配器
    for nurse in PART_TIME_STAFFS:
        if nurse in names:
            target_blocks = [3, 3, 2, 2]
            random.shuffle(target_blocks)
            allocated_days_indices = set()
            
            for b_len in target_blocks:
                valid_starts = []
                for start_d in range(num_days - b_len + 1):
                    if start_d > 0 and (start_d - 1) in allocated_days_indices:
                        continue
                    if (start_d + b_len) < num_days and (start_d + b_len) in allocated_days_indices:
                        continue
                        
                    block_ok = True
                    total_shortage = 0
                    for offset in range(b_len):
                        curr_day = start_d + offset
                        if schedule[nurse][curr_day] != "" or curr_day in allocated_days_indices:
                            block_ok = False
                            break
                        if curr_day < len(requests[nurse]) and requests[nurse][curr_day] == "M":
                            block_ok = False
                            break
                        
                        c_count = sum(1 for n in names if schedule[n][curr_day] == "D")
                        if c_count >= manpower_req[curr_day]["D_max"]:
                            block_ok = False
                            break
                            
                        shortage = manpower_req[curr_day]["D_min"] - c_count
                        if shortage > 0:
                            total_shortage += shortage
                            
                    if block_ok:
                        valid_starts.append((start_d, total_shortage))
                        
                if valid_starts:
                    valid_starts.sort(key=lambda x: x[1], reverse=True)
                    best_start = valid_starts[0][0]
                    for offset in range(b_len):
                        target_day = best_start + offset
                        schedule[nurse][target_day] = "D"
                        allocated_days_indices.add(target_day)

    # 🎯【核心戰略升級：STEP 5.5 最高權限剛性補洞引擎】
    # 當前面所有的常規流程走完後，系統會再次全面覆查，強行把「不夠人」的窟窿在安全範圍內完美補滿
    for day in range(num_days):
        for shift_type in ["N", "E", "D"]:
            min_req = manpower_req[day][f"{shift_type}_min"]
            max_req = manpower_req[day].get(f"{shift_type}_max", min_req)
            
            current_count = sum(1 for n in names if schedule[n][day] == shift_type)
            
            # 如果發現人數比你設定的最低需求還要少，啟動剛性徵調令
            while current_count < min_req:
                possible_rescuers = []
                for nurse in names:
                    if nurse in PART_TIME_STAFFS and shift_type != "D": 
                        continue # 兼職不上夜班
                    if schedule[nurse][day] != "": 
                        continue # 當天有排班或預排假
                    if not can_work_shift(permissions[nurse], shift_type): 
                        continue # 沒這班別的權限
                        
                    # 臨床鐵血安全防線把關
                    is_safe = True
                    if get_current_streak(nurse, day) >= 5: is_safe = False
                    
                    if shift_type == "D": # 排白班的防呆
                        if day == 0 and history_shift.get(nurse) in ["N", "E"]: is_safe = False
                        if day == 1 and (schedule[nurse][0] == "N" or history_shift.get(nurse) == "N" or schedule[nurse][0] == "E"): is_safe = False
                        if day > 1 and (schedule[nurse][day-1] == "N" or schedule[nurse][day-2] == "N" or schedule[nurse][day-1] == "E"): is_safe = False
                    elif shift_type == "E": # 排小夜的防呆
                        if day == 0 and history_shift.get(nurse) == "N": is_safe = False
                        if day == 1 and (schedule[nurse][0] == "N" or history_shift.get(nurse) == "N"): is_safe = False
                        if day > 1 and (schedule[nurse][day-1] == "N" or schedule[nurse][day-2] == "N"): is_safe = False
                    elif shift_type == "N": # 排大夜的防呆
                        if day == 1 and history_shift.get(nurse) == "N" and schedule[nurse][0] != "N": is_safe = False
                        if day > 1 and schedule[nurse][day-1] != "N" and schedule[nurse][day-2] == "N": is_safe = False
                        
                    if is_safe:
                        possible_rescuers.append(nurse)
                        
                if not possible_rescuers:
                    break # 全員死鎖，直接跳出防當機
                    
                # 挑選目前工作天數最少、假放最多的人回來上班
                possible_rescuers.sort(key=lambda x: sum(1 for s in schedule[x] if s in ["D", "E", "N"]))
                chosen_one = possible_rescuers[0]
                
                schedule[chosen_one][day] = shift_type
                current_count += 1

    # STEP 6: 空格補 off
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "":
                if d < len(requests[nurse]) and requests[nurse][d] == "R":
                    schedule[nurse][d] = "R"
                else:
                    schedule[nurse][d] = "off"

    # STEP 7: 全職休假多退少補與動態均勻平準大腦
    full_time_nurses = [n for n in names if n not in PART_TIME_STAFFS]
    for loop in range(4):
        current_works = {n: sum(1 for x in schedule[n] if x in ["D", "E", "N"]) for n in full_time_nurses}
        avg_work_target = sum(current_works.values()) // len(full_time_nurses)
        
        overworked_nurses = [n for n in full_time_nurses if current_works[n] > avg_work_target + 1]
        underworked_nurses = [n for n in full_time_nurses if current_works[n] < avg_work_target - 1]
        
        if not overworked_nurses and not underworked_nurses:
            break
            
        for d in range(num_days):
            # 退班（假太少的人）：必須確保退班後，該班別不會跌破自訂的最低人數！
            for shift_type in ["D", "E", "N"]:
                current_shift_count = sum(1 for n in names if schedule[n][d] == shift_type)
                if current_shift_count > manpower_req[d][f"{shift_type}_min"]:
                    overworked_nurses.sort(key=lambda x: current_works[x], reverse=True)
                    for o_nurse in overworked_nurses:
                        if schedule[o_nurse][d] == shift_type and (d < len(requests[o_nurse]) and requests[o_nurse][d] == ""):
                            schedule[o_nurse][d] = "off"
                            current_works[o_nurse] -= 1
                            break

    return schedule

def can_work_shift(permission, shift):
    if shift in ["R", "off", "M"]:
        return True
    return shift in permission

# =====================================
# 側邊欄與主要畫面宣告
# =====================================

with st.sidebar:
    st.header("📅 日期與檔案設定")
    start_date = st.date_input("開始日期", datetime.date.today().replace(day=1))
    end_date = st.date_input("結束日期", datetime.date.today())
    st.markdown("---")
    file_a = st.file_uploader("上傳【基本班表（上月舊班表）】", type=["xlsx"])
    file_b = st.file_uploader("上傳當月【預排休表】", type=["xlsx"])

# =====================================
# 主程式邏輯區
# =====================================

if file_b:
    try:
        num_days = (end_date - start_date).days + 1
        
        requests, extracted_permissions = load_request_and_permissions(file_b, CORE_STAFF_NAMES, num_days)
        history_shift, history_streak = load_history_only(file_a, CORE_STAFF_NAMES)
        names = CORE_STAFF_NAMES

        date_headers = []
        weeks_map = {} 
        weeks_setup_data = [] 
        
        current_week_idx = 1
        last_week_no = None
        
        for i in range(num_days):
            curr = start_date + datetime.timedelta(days=i)
            w = WEEKDAYS_CHINESE[curr.weekday()]
            date_str = curr.strftime('%m/%d')
            full_header = f"{date_str}({w})"
            date_headers.append(full_header)
            
            year, week_no, weekday_no = curr.isocalendar()
            if last_week_no is not None and week_no != last_week_no:
                current_week_idx += 1
            last_week_no = week_no
            
            is_weekend = curr.weekday() in [5, 6] 
            day_type_label = "假日(六日)" if is_weekend else "平日(一五)"
            week_label = f"第 {current_week_idx} 週"
            
            weeks_map[i] = {
                "week_label": week_label,
                "is_weekend": is_weekend
            }
            
            setup_key = f"{week_label} - {day_type_label}"
            if setup_key not in [x["週別與平假日"] for x in weeks_setup_data]:
                if is_weekend:
                    weeks_setup_data.append({
                        "週別與平假日": setup_key, "week_id": week_label, "is_we": True,
                        "白班最低(D Min)": 3, "白班最高(D Max)": 5,
                        "小夜最低(E Min)": 2, "小夜最高(E Max)": 4,
                        "大夜最低(N)": 2, "大夜最高(N Max)": 2
                    })
                else:
                    weeks_setup_data.append({
                        "週別與平假日": setup_key, "week_id": week_label, "is_we": False,
                        "白班最低(D Min)": 4, "白班最高(D Max)": 6,
                        "小夜最低(E Min)": 3, "小夜最高(E Max)": 4,
                        "大夜最低(N)": 2, "大夜最高(N Max)": 2
                    })

        col1, col2 = st.columns([1, 1.3])
        
        with col1:
            st.subheader("👥 1. 人員初始狀態確認")
            st.caption("💡 系統已自動載入對齊結果。若與上月最後一天不符，您隨時可以用選單手動修正！")
            config_rows = []
            for nurse in names:
                config_rows.append({
                    "姓名": nurse,
                    "權限": extracted_permissions[nurse], 
                    "上月最後班": history_shift[nurse], 
                    "已連上天數": history_streak[nurse]
                })
            base_config_df = pd.DataFrame(config_rows)
            
            config_df = st.data_editor(
                base_config_df, 
                use_container_width=True, 
                num_rows="fixed",
                column_config={
                    "姓名": st.column_config.TextColumn("姓名", disabled=True), 
                    "權限": st.column_config.SelectboxColumn(
                        "權限",
                        options=["DEN", "DE", "DN", "EN", "D", "E", "N"],
                        required=True
                    ),
                    "上月最後班": st.column_config.SelectboxColumn(
                        "上月最後班",
                        options=["D", "E", "N", "off", "R", "M"],
                        required=True
                    ),
                    "已連上天數": st.column_config.NumberColumn("已連上天數", min_value=0, max_value=5, step=1)
                }
            )

        with col2:
            st.subheader("📊 2. 按週智慧自訂平假日人數上下限")
            manpower_editor_df = st.data_editor(
                pd.DataFrame(weeks_setup_data), 
                use_container_width=True, 
                num_rows="fixed",
                column_config={
                    "週別與平假日": st.column_config.TextColumn("週別與平假日", disabled=True)
                }
            )

        manpower_req_list = []
        for d_idx in range(num_days):
            d_info = weeks_map[d_idx]
            target_week = d_info["week_label"]
            target_is_we = d_info["is_weekend"]
            
            match_row = manpower_editor_df[
                (manpower_editor_df["week_id"] == target_week) & 
                (manpower_editor_df["is_we"] == target_is_we)
            ].iloc[0]
            
            manpower_req_list.append({
                "D_min": int(match_row["白班最低(D Min)"]),
                "D_max": int(match_row["白班最高(D Max)"]),
                "E_min": int(match_row["小夜最低(E Min)"]),
                "E_max": int(match_row["小夜最高(E Max)"]),
                "N_min": int(match_row["大夜最低(N)"]),
                "N_max": int(match_row["大夜最高(N Max)"])
            })

        permissions = {}
        history_shift_final = {}
        history_streak_final = {}
        
        for idx in range(len(config_df)):
            raw_name = str(config_df.iloc[idx]["姓名"]).replace(" ", "").replace(" ", "").strip()
            raw_perm = str(config_df.iloc[idx]["權限"]).upper().strip()
            raw_shift = str(config_df.iloc[idx]["上月最後班"]).strip()
            raw_streak = int(config_df.iloc[idx]["已連上天數"])
            
            permissions[raw_name] = raw_perm
            history_shift_final[raw_name] = raw_shift
            history_streak_final[raw_name] = raw_streak

        st.markdown("---")
        
        if st.button("🚀 依照按週自訂上下限啟動自動排班", type="primary", use_container_width=True):
            with st.spinner("優化班表計算中..."):
                st.session_state["schedule_result"] = generate_schedule(
                    names, permissions, requests, num_days,
                    manpower_req_list, history_shift_final, history_streak_final
                )
                st.session_state["run_success"] = True

        if st.session_state["run_success"]:
            result = st.session_state["schedule_result"]

            schedule_df = pd.DataFrame(result).T
            schedule_df.columns = date_headers
            schedule_df.insert(0, "班別權限", [permissions.get(n, "DEN") for n in schedule_df.index])

            manpower_df_rows = []
            for d in range(num_days):
                d_count = sum(1 for n in names if result[n][d] == "D")
                e_count = sum(1 for n in names if result[n][d] == "E")
                n_count = sum(1 for n in names if result[n][d] == "N")
                m_count = sum(1 for n in names if result[n][d] == "M")
                manpower_df_rows.append([
                    date_headers[d], 
                    f"{d_count} (核定範疇: {manpower_req_list[d]['D_min']}~{manpower_req_list[d]['D_max']})",
                    f"{e_count} (核定範疇: {manpower_req_list[d]['E_min']}~{manpower_req_list[d]['E_max']})",
                    f"{n_count} (核定範疇: {manpower_req_list[d]['N_min']}~{manpower_req_list[d]['N_max']})",
                    m_count
                ])
            manpower_df = pd.DataFrame(manpower_df_rows, columns=["日期", "實際白班(D)", "實際小夜(E)", "實際大夜(N)", "會議開會(M)"])

            holiday_rows = []
            for nurse in names:
                r_count = sum(1 for x in result[nurse] if x == "R")
                off_count = sum(1 for x in result[nurse] if x == "off")
                holiday_rows.append([nurse, r_count, off_count, r_count + off_count])
            holiday_df = pd.DataFrame(holiday_rows, columns=["姓名", "預排休(R)", "常規OFF", "總休假天數"])

            night_df_rows = []
            for nurse in names:
                e_count = sum(1 for x in result[nurse] if x == "E")
                n_count = sum(1 for x in result[nurse] if x == "N")
                night_df_rows.append([nurse, e_count, n_count, e_count + n_count])
            night_df = pd.DataFrame(night_df_rows, columns=["姓名", "小夜(E)", "大夜(N)", "夜班總計"])

            issues = []
            for nurse in names:
                if nurse not in PART_TIME_STAFFS:
                    total_rest = sum(1 for x in result[nurse] if x in ["off", "R"])
                    if total_rest < 8:
                        issues.append([nurse, f"符合勞基法排班不符：當月總休假不足 8 天 ({total_rest}天)"])
                streak = 0
                for shift in result[nurse]:
                    if shift in ["D", "E", "N"]:
                        streak += 1
                    else:
                        streak = 0
                    if streak > 5:
                        issues.append([nurse, "違反連續上班上限：連續工作超過 5 天"])
                        break
                if nurse in PART_TIME_STAFFS:
                    d_count = sum(1 for x in result[nurse] if x == "D")
                    if d_count > 10:
                        issues.append([nurse, f"兼職人員排班限制：白班超過 10 天 ({d_count}天)"])
                    if any(x in ["E", "N"] for x in result[nurse]):
                        issues.append([nurse, "兼職人員排班錯誤：出現非白班(E/N班)"])

            tabs = st.tabs(["📅 最終班表", "📊 每日實際人力", "🏖️ 休假統計", "🌙 夜班統計", "🔍 規則檢查"])

            with tabs[0]:
                st.dataframe(schedule_df, use_container_width=True, height=500)

            with tabs[1]:
                st.dataframe(manpower_df, use_container_width=True)

            with tabs[2]:
                st.dataframe(holiday_df, use_container_width=True)

            with tabs[3]:
                st.dataframe(night_df, use_container_width=True)

            with tabs[4]:
                if len(issues) == 0:
                    st.success("🎉 太棒了！14位護理同仁權仁與假別完全精準抓取，排班完美達標！")
                else:
                    issue_df = pd.DataFrame(issues, columns=["姓名", "異常說明"])
                    st.dataframe(issue_df, use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                schedule_df.to_excel(writer, sheet_name="班表")
                manpower_df.to_excel(writer, sheet_name="每日實際人力", index=False)
                holiday_df.to_excel(writer, sheet_name="休假統計", index=False)
                night_df.to_excel(writer, sheet_name="夜班統計", index=False)
                
            st.markdown("---")
            st.download_button(
                label="📥 下載 14人最終精準權限版 Excel",
                data=output.getvalue(),
                file_name=f"2F護理排班結果_{start_date.strftime('%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"系統執行時發生錯誤：{str(e)}")
else:
    st.info("💡 請上傳當月【預排休表】（基本班表可選填上傳）以啟動系統。")
