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
    page_title="2F護理排班系統 (精準完全體)",
    layout="wide"
)

st.title("🏥 2F護理排班系統 (精準完全體)")

# 初始化 Streamlit 永久記憶體狀態
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

# 備用安全底牌
DEFAULT_PERMISSIONS = {
    "郭珍君": "D", "劉榆琳": "N", "陳義樺": "N", "李雅慧": "DEN", 
    "蔡靜如": "DEN", "陳慧屏": "DEN", "黃家靜": "DEN", "許雅雯": "DEN", 
    "林欣蓓": "DEN", "陳萱芸": "DEN", "汪家容": "DEN", "林欣儀": "DEN", 
    "林怡微": "DEN", "陳威宇": "DEN"
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
# 歷史狀態載入
# =====================================
def load_history_only(upload_file, names):
    history_shift = {n: "off" for n in names}
    history_streak = {n: 0 for n in names}
    
    df = pd.read_excel(upload_file, header=None)
    for r in range(len(df)):
        row = [str(x).strip() for x in df.iloc[r].values]
        row_text = "".join(row).replace(" ", "").replace(" ", "")
        
        target = None
        for nurse in names:
            if nurse in row_text:
                target = nurse
                break
        if not target:
            continue
            
        shifts = []
        for cell in row:
            cell = str(cell).upper()
            if cell in ["D", "E", "N", "OFF", "R", "M"]:
                shifts.append(cell)
        if len(shifts) == 0:
            continue
            
        history_shift[target] = shifts[-1]
        
        streak = 0
        for s in reversed(shifts):
            if s in ["D", "E", "N"]:
                streak += 1
            else:
                break
        history_streak[target] = streak
        
    return history_shift, history_streak

# =====================================
# 智慧排班引擎 (完全體修正版)
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

    # STEP 2: 大夜班 (N) 分配 —— 滿載優先
    for day in range(num_days):
        req_n_min = manpower_req[day]["N_min"]
        current_n = sum(1 for n in names if schedule[n][day] == "N")
        # 🎯【精準修復】完全移除不小心黏在一起的 = n_min 語法錯誤
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
            if day == 0 and history_shift.get(nurse) == "N":
                continue
            if day > 0 and day - 1 < len(schedule[nurse]) and schedule[nurse][day - 1] == "N":
                continue
            candidates.append(nurse)

        # 大夜班極限救火防線
        if len(candidates) < need_n:
            for nurse in names:
                if nurse not in PART_TIME_STAFFS and schedule[nurse][day] == "" and can_work_shift(permissions[nurse], "N"):
                    if nurse not in candidates:
                        candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (1 if (day < len(requests[x]) and requests[x][day] == "R") else 0, night_count[x], work_count[x]))

        for nurse in candidates[:need_n]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 3: 小夜班 (E) 分配
    for day in range(num_days):
        req_e_min = manpower_req[day]["E_min"]
        current_e = sum(1 for n in names if schedule[n][day] == "E")
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
            if day > 0 and day - 1 < len(schedule[nurse]) and schedule[nurse][day - 1] == "N":
                continue
            candidates.append(nurse)

        if len(candidates) < need_e:
            for nurse in names:
                if nurse not in PART_TIME_STAFFS Glen and schedule[nurse][day] == "" and can_work_shift(permissions[nurse], "E"):
                    if nurse not in candidates:
                        candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (1 if (day < len(requests[x]) and requests[x][day] == "R") else 0, night_count[x], work_count[x]))

        for nurse in candidates[:need_e]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 4: 白班 (D) 分配
    for day in range(num_days):
        req_d_min = manpower_req[day]["D_min"]
        current_d = sum(1 for n in names if schedule[n][day] == "D")
        need_d = req_d_min - current_d
        if need_d <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse in PART_TIME_STAFFS: 
                continue
            if schedule[nurse][day] != "":
                continue
            if not can_work_shift(permissions[nurse], "D"):
                continue
            if day > 0 and day - 1 < len(schedule[nurse]) and schedule[nurse][day - 1] == "N":
                continue 
            if day > 1 and day - 2 < len(schedule[nurse]) and schedule[nurse][day - 2] == "N":
                continue 
            candidates.append(nurse)

        if len(candidates) < need_d:
            for nurse in names:
                if nurse not in PART_TIME_STAFFS and schedule[nurse][day] == "" and can_work_shift(permissions[nurse], "D"):
                    if day > 0 and day - 1 < len(schedule[nurse]) and schedule[nurse][day - 1] == "N":
                        continue
                    if nurse not in candidates:
                        candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (1 if (day < len(requests[x]) and requests[x][day] == "R") else 0, work_count[x]))

        for nurse in candidates[:need_d]:
            schedule[nurse][day] = "D"
            work_count[nurse] += 1

    # STEP 5: 半職郭珍君智慧補洞
    for nurse in PART_TIME_STAFFS:
        if nurse in names:
            allocated_days = 0
            for loop in range(10): 
                shortage_days = []
                for d in range(num_days):
                    is_meeting = (d < len(requests[nurse]) and requests[nurse][d] == "M")
                    if schedule[nurse][d] == "" and not is_meeting:
                        current_d_count = sum(1 for n in names if schedule[n][d] == "D")
                        shortage = current_d_count - manpower_req[d]["D_min"]
                        if shortage < 0:
                            shortage_days.append((d, shortage))
                
                if not shortage_days:
                    break
                
                shortage_days.sort(key=lambda x: x[1]) 
                target_day = shortage_days[0][0]
                schedule[nurse][target_day] = "D"
                allocated_days += 1

            if allocated_days < 10:
                blank_days = [d for d in range(num_days) if schedule[nurse][d] == "" and not (d < len(requests[nurse]) and requests[nurse][d] == "M")]
                random.shuffle(blank_days)
                for d in blank_days[:10 - allocated_days]:
                    schedule[nurse][d] = "D"

    # STEP 6: 剩餘空格全部補 off
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "":
                if d < len(requests[nurse]) and requests[nurse][d] == "R":
                    schedule[nurse][d] = "R"
                else:
                    schedule[nurse][d] = "off"

    # STEP 7: 法定休假天數多退少補
    for nurse in names:
        if nurse in PART_TIME_STAFFS:
            continue
        holiday_count = sum(1 for x in schedule[nurse] if x in ["off", "R"])
        if holiday_count < 8:
            need = 8 - holiday_count
            for d in range(num_days):
                if need <= 0:
                    break
                is_req = (d < len(requests[nurse]) and requests[nurse][d] != "")
                if schedule[nurse][d] == "D" and not is_req:
                    schedule[nurse][d] = "off"
                    need -= 1

    # STEP 8: 每週一休與連 5 防呆
    for nurse in names:
        for start in range(0, num_days, 7):
            end = min(start + 7, num_days)
            week = schedule[nurse][start:end]
            has_rest = any(x in ["off", "R"] for x in week)
            if not has_rest and (end - 1) < num_days:
                if (end - 1) < len(requests[nurse]) and requests[nurse][end - 1] not in ["M", "R"]:
                    schedule[nurse][end - 1] = "off"

    for nurse in names:
        streak = history_streak.get(nurse, 0)
        for d in range(num_days):
            if schedule[nurse][d] in ["D", "E", "N"]:
                streak += 1
            else:
                streak = 0
            if streak > 5:
                if d < len(requests[nurse]) and requests[nurse][d] not in ["R", "M"]:
                    schedule[nurse][d] = "off"
                streak = 0

    return schedule

def can_work_shift(permission, shift):
    if shift in ["R", "off", "M"]:
        return True
    return shift in permission

# =====================================
# 主程式
# =====================================

if file_a and file_b:
    try:
        num_days = (end_date - start_date).days + 1
        
        requests, extracted_permissions = load_request_and_permissions(file_b, CORE_STAFF_NAMES, num_days)
        history_shift, history_streak = load_history_only(file_a, CORE_STAFF_NAMES)
        names = CORE_STAFF_NAMES

        date_headers = []
        manpower_setup_rows = []

        for i in range(num_days):
            curr = start_date + datetime.timedelta(days=i)
            w = WEEKDAYS_CHINESE[curr.weekday()]
            date_str = curr.strftime('%m/%d')
            full_header = f"{date_str}({w})"
            date_headers.append(full_header)
            
            if curr.weekday() in [5, 6]:
                manpower_setup_rows.append({
                    "日期": full_header, "白班最低(D)": 3, "小夜最低(E)": 2, "大夜最低(N)": 2
                })
            else:
                manpower_setup_rows.append({
                    "日期": full_header, "白班最低(D)": 4, "小夜最低(E)": 3, "大夜最低(N)": 2
                })

        col1, col2 = st.columns([1, 1.2])
        
        with col1:
            st.subheader("👥 1. 人員初始狀態確認")
            config_rows = []
            for nurse in names:
                config_rows.append({
                    "姓名": nurse,
                    "權限": extracted_permissions[nurse], 
                    "上月最後班": history_shift[nurse],
                    "已連上天數": history_streak[nurse]
                })
            config_df = st.data_editor(pd.DataFrame(config_rows), use_container_width=True, num_rows="fixed")

        with col2:
            st.subheader("📊 2. 自訂每日最低人力需求")
            manpower_editor_df = st.data_editor(pd.DataFrame(manpower_setup_rows), use_container_width=True, num_rows="fixed")

        manpower_req_list = []
        for _, row in manpower_editor_df.iterrows():
            manpower_req_list.append({
                "D_min": int(row["白班最低(D)"]),
                "E_min": int(row["小夜最低(E)"]),
                "N_min": int(row["大夜最低(N)"])
            })

        permissions = {}
        history_shift_final = {}
        history_streak_final = {}
        for _, row in config_df.iterrows():
            nurse = row["姓名"]
            permissions[nurse] = str(row["權限"]).upper()
            history_shift
