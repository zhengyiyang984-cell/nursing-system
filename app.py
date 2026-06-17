import streamlit as st
import pandas as pd
import datetime
import random
from io import BytesIO

# =====================================
# 基本設定
# =====================================

st.set_page_config(
    page_title="2F護理排班系統 (全班別交叉救火完全體)",
    layout="wide"
)

st.title("🏥 2F護理排班系統 (全班別交叉救火・每日人力100%死守版)")

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

def can_work_shift(permission, shift):
    if shift in ["R", "off", "M"]:
        return True
    return shift in permission or "DEN" in permission

# =====================================
# 智慧排班引擎 (全班別交叉救火完全體)
# =====================================
def generate_schedule(names, permissions, requests, num_days, manpower_req, history_shift, history_streak):
    schedule = {n: [""] * num_days for n in names}
    night_count = {n: 0 for n in names}
    work_count = {n: 0 for n in names}

    # 填入自行預排與會議
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

    def is_shift_safe(nurse, day, shift_type):
        if get_current_streak(nurse, day) >= 5: return False
        if shift_type == "D":
            if day == 0 and history_shift.get(nurse) in ["N", "E"]: return False
            if day == 1 and (schedule[nurse][0] in ["N", "E"] or history_shift.get(nurse) == "N"): return False
            if day > 1 and (schedule[nurse][day-1] in ["N", "E"] or schedule[nurse][day-2] == "N"): return False
        elif shift_type == "E":
            if day == 0 and history_shift.get(nurse) == "N": return False
            if day == 1 and (schedule[nurse][0] == "N" or history_shift.get(nurse) == "N"): return False
            if day > 1 and (schedule[nurse][day-1] == "N" or schedule[nurse][day-2] == "N"): return False
        elif shift_type == "N":
            if day == 0 and history_shift.get(nurse) in ["D", "E"]: return False
            if day > 0 and schedule[nurse][day-1] in ["D", "E"]: return False
        return True

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

    # STEP 2: 大夜班 (N) 常規輪派
    for day in range(num_days):
        req_n_min = manpower_req[day]["N_min"]
        req_n_max = manpower_req[day]["N_max"]
        current_n = sum(1 for n in names if schedule[n][day] == "N")
        if current_n >= req_n_max: continue
        need_n = req_n_min - current_n
        if need_n <= 0: continue

        candidates = [n for n in names if n not in PART_TIME_STAFFS and schedule[n][day] == "" and can_work_shift(permissions[n], "N") and is_shift_safe(n, day, "N")]
        random.shuffle(candidates)
        candidates.sort(key=lambda x: (25 if (day > 0 and schedule[x][day-1] == "N") or (day == 0 and history_shift.get(x) == "N") else 0, get_work_continuation_weight(x, day), -work_count[x]), reverse=True)
        
        for nurse in candidates[:min(need_n, req_n_max - current_n)]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 3: 小夜班 (E) 常規輪派
    for day in range(num_days):
        req_e_min = manpower_req[day]["E_min"]
        req_e_max = manpower_req[day]["E_max"]
        current_e = sum(1 for n in names if schedule[n][day] == "E")
        if current_e >= req_e_max: continue
        need_e = req_e_min - current_e
        if need_e <= 0: continue

        candidates = [n for n in names if n not in PART_TIME_STAFFS and schedule[n][day] == "" and can_work_shift(permissions[n], "E") and is_shift_safe(n, day, "E")]
        random.shuffle(candidates)
        candidates.sort(key=lambda x: (get_work_continuation_weight(x, day), -work_count[x]), reverse=True)
        
        for nurse in candidates[:min(need_e, req_e_max - current_e)]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 4: 白班 (D) 常規輪派
    for day in range(num_days):
        req_d_min = manpower_req[day]["D_min"]
        req_d_max = manpower_req[day]["D_max"]
        current_d = sum(1 for n in names if schedule[n][day] == "D")
        if current_d >= req_d_max: continue
        need_d = req_d_min - current_d
        if need_d <= 0: continue

        candidates = [n for n in names if n not in PART_TIME_STAFFS and schedule[n][day] == "" and can_work_shift(permissions[n], "D") and is_shift_safe(n, day, "D") and not (day < len(requests[n]) and requests[n][day] == "R")]
        random.shuffle(candidates)
        candidates.sort(key=lambda x: (get_work_continuation_weight(x, day), -work_count[x]), reverse=True)
        
        for nurse in candidates[:min(need_d, req_d_max - current_d)]:
            schedule[nurse][day] = "D"
            work_count[nurse] += 1

    # STEP 5: 半職郭珍君精準 10 天塊狀限制鎖定段
    for nurse in PART_TIME_STAFFS:
        if nurse in names:
            target_blocks = [3, 3, 2, 2]
            random.shuffle(target_blocks)
            allocated_days_indices = set()
            for b_len in target_blocks:
                valid_starts = []
                for start_d in range(num_days - b_len + 1):
                    if start_d > 0 and (start_d - 1) in allocated_days_indices: continue
                    if (start_d + b_len) < num_days and (start_d + b_len) in allocated_days_indices: continue
                    block_ok = True
                    for offset in range(b_len):
                        curr_day = start_d + offset
                        if schedule[nurse][curr_day] != "" or curr_day in allocated_days_indices:
                            block_ok = False
                            break
                        if curr_day < len(requests[nurse]) and requests[nurse][curr_day] == "M":
                            block_ok = False
                            break
                    if block_ok:
                        valid_starts.append(start_d)
                if valid_starts:
                    best_start = random.choice(valid_starts)
                    for offset in range(b_len):
                        target_day = best_start + offset
                        schedule[nurse][target_day] = "D"
                        allocated_days_indices.add(target_day)

    # 🎯 STEP 5.5:【全班別大局交叉救火調節令】
    # 全面打通白、小、大夜！只要當天任何人手少於最低需求，全面調配所有當天空格且符合安全規範的全職人員補滿！
    for day in range(num_days):
        for shift_type in ["N", "E", "D"]:
            min_req = manpower_req[day][f"{shift_type}_min"]
            current_count = sum(1 for n in names if schedule[n][day] == shift_type)
            
            while current_count < min_req:
                possible_rescuers = []
                for nurse in names:
                    if nurse in PART_TIME_STAFFS: continue 
                    if schedule[nurse][day] != "": continue # 必須是空格
                    
                    # 🚀 解鎖所有全職同仁（包含DEN大局權限者）交叉互相救火
                    if not is_shift_safe(nurse, day, shift_type): continue
                    
                    has_neighbor = False
                    if day > 0 and schedule[nurse][day-1] in ["D", "E", "N"]: has_neighbor = True
                    if day < num_days - 1 and schedule[nurse][day+1] in ["D", "E", "N"]: has_neighbor = True
                    if day == 0 and history_shift.get(nurse) in ["D", "E", "N"]: has_neighbor = True
                    
                    possible_rescuers.append((nurse, has_neighbor))
                    
                if not possible_rescuers: break
                
                # 優先挑選可以串聯成連續班的人，避免製造碎班
                possible_rescuers.sort(key=lambda x: (1 if x[1] else 0, -sum(1 for s in schedule[x[0]] if s in ["D", "E", "N"])), reverse=True)
                chosen_nurse = possible_rescuers[0][0]
                schedule[chosen_nurse][day] = shift_type
                
                # 🚀 連帶補班防碎班：如果是跨班被抓過來上班，幫他前後看能不能連著上，消滅1天碎班
                if day < num_days - 1 and schedule[chosen_nurse][day+1] == "" and is_shift_safe(chosen_nurse, day+1, shift_type):
                    schedule[chosen_nurse][day+1] = shift_type
                elif day > 0 and schedule[chosen_nurse][day-1] == "" and is_shift_safe(chosen_nurse, day-1, shift_type):
                    schedule[chosen_nurse][day-1] = shift_type
                        
                current_count = sum(1 for n in names if schedule[n][day] == shift_type)

    # STEP 6: 空格補 off
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "":
                if d < len(requests[nurse]) and requests[nurse][d] == "R":
                    schedule[nurse][d] = "R"
                else:
                    schedule[nurse][d] = "off"

    # STEP 7: 大局強制均勻平衡調節令（死守全職 8 天休假底線）
    full_time_nurses = [n for n in names if n not in PART_TIME_STAFFS]
    for loop in range(5):
        current_works = {n: sum(1 for x in schedule[n] if x in ["D", "E", "N"]) for n in full_time_nurses}
        overworked = [n for n in full_time_nurses if current_works[n] > 22] # 上超過 22 天代表假不足 8 天
        
        if not overworked:
            break
            
        for d in range(num_days):
            for shift_type in ["D", "E", "N"]:
                c_count = sum(1 for n in names if schedule[n][d] == shift_type)
                if c_count > manpower_req[d][f"{shift_type}_min"]:
                    overworked.sort(key=lambda x: current_works[x], reverse=True)
                    for o_nurse in overworked:
                        if schedule[o_nurse][d] == shift_type and (d < len(requests[o_nurse]) and requests[o_nurse][d] == ""):
                            is_safe_to_remove = True
                            if d > 0 and d < num_days - 1:
                                if schedule[o_nurse][d-1] in ["D","E","N"] and schedule[o_nurse][d+1] == "off":
                                    if d > 1 and schedule[o_nurse][d-2] == "off": is_safe_to_remove = False
                            if is_safe_to_remove:
                                schedule[o_nurse][d] = "off"
                                current_works[o_nurse] -= 1
                                break
    return schedule

# =====================================
# Streamlit 主流程
# =====================================

with st.sidebar:
    st.header("📅 日期與檔案設定")
    start_date = st.date_input("開始日期", datetime.date.today().replace(day=1))
    end_date = st.date_input("結束日期", datetime.date.today())
    st.markdown("---")
    file_a = st.file_uploader("上傳【基本班表（上月舊班表）】", type=["xlsx"])
    file_b = st.file_uploader("上傳當月【預排休表】", type=["xlsx"])

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
            
            weeks_map[i] = {"week_label": week_label, "is_weekend": is_weekend}
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
            config_rows = [{"姓名": nurse, "權限": extracted_permissions[nurse], "上月最後班": history_shift[nurse], "已連上天數": history_streak[nurse]} for nurse in names]
            config_df = st.data_editor(
                pd.DataFrame(config_rows), use_container_width=True, num_rows="fixed",
                column_config={
                    "姓名": st.column_config.TextColumn("姓名", disabled=True), 
                    "權限": st.column_config.SelectboxColumn("權限", options=["DEN", "DE", "DN", "EN", "D", "E", "N"], required=True),
                    "上月最後班": st.column_config.SelectboxColumn("上月最後班", options=["D", "E", "N", "off", "R", "M"], required=True),
                    "已連上天數": st.column_config.NumberColumn("已連上天數", min_value=0, max_value=5, step=1)
                }
            )

        with col2:
            st.subheader("📊 2. 按週智慧自訂平假日人數上下限")
            manpower_editor_df = st.data_editor(pd.DataFrame(weeks_setup_data), use_container_width=True, num_rows="fixed", column_config={"週別與平假日": st.column_config.TextColumn("週別與平假日", disabled=True)})

        manpower_req_list = []
        for d_idx in range(num_days):
            d_info = weeks_map[d_idx]
            match_row = manpower_editor_df[(manpower_editor_df["week_id"] == d_info["week_label"]) & (manpower_editor_df["is_we"] == d_info["is_weekend"])].iloc[0]
            manpower_req_list.append({
                "D_min": int(match_row["白班最低(D Min)"]), "D_max": int(match_row["白班最高(D Max)"]),
                "E_min": int(match_row["小夜最低(E Min)"]), "E_max": int(match_row["小夜最高(E Max)"]),
                "N_min": int(match_row["大夜最低(N)"]), "N_max": int(match_row["大夜最高(N Max)"])
            })

        permissions = {}
        history_shift_final = {}
        history_streak_final = {}
        for idx in range(len(config_df)):
            raw_name = str(config_df.iloc[idx]["姓名"]).strip()
            permissions[raw_name] = str(config_df.iloc[idx]["權限"]).upper().strip()
            history_shift_final[raw_name] = str(config_df.iloc[idx]["上月最後班"]).strip()
            history_streak_final[raw_name] = int(config_df.iloc[idx]["已連上天數"])

        st.markdown("---")
        if st.button("🚀 啟動終極平衡自動排班系統", type="primary", use_container_width=True):
            with st.spinner("全班別交叉救火優化中..."):
                st.session_state["schedule_result"] = generate_schedule(names, permissions, requests, num_days, manpower_req_list, history_shift_final, history_streak_final)
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

            holiday_df = pd.DataFrame([[n, sum(1 for x in result[n] if x == "R"), sum(1 for x in result[n] if x == "off"), sum(1 for x in result[n] if x in ["R", "off"])] for n in names], columns=["姓名", "預排休(R)", "常規OFF", "總休假天數"])
            night_df = pd.DataFrame([[n, sum(1 for x in result[n] if x == "E"), sum(1 for x in result[n] if x == "N"), sum(1 for x in result[n] if x in ["E", "N"])] for n in names], columns=["姓名", "小夜(E)", "大夜(N)", "夜班總計"])

            issues = []
            for nurse in names:
                if nurse not in PART_TIME_STAFFS:
                    tot_holiday = sum(1 for x in result[nurse] if x in ["off", "R"])
                    if tot_holiday < 8:
                        issues.append([nurse, f"當月總休假天數不足 8 天 (目前僅有 {tot_holiday} 天)"])
                if nurse in PART_TIME_STAFFS:
                    d_count = sum(1 for x in result[nurse] if x == "D")
                    if d_count != 10:
                        issues.append([nurse, f"兼職天數錯誤：必須剛好 10 天，目前排了 {d_count} 天"])
                
                streak = 0
                for d in range(num_days):
                    if result[nurse][d] in ["D", "E", "N"]: streak += 1
                    else:
                        if streak == 1:
                            issues.append([nurse, f"於 {date_headers[d-1]} 出現 1 天碎班（不符連續要求）"])
                        streak = 0

            tabs = st.tabs(["📅 最終班表", "📊 每日實際人力", "🏖️ 休假統計", "🌙 夜班統計", "🔍 班表檢查"])
            with tabs[0]: st.dataframe(schedule_df, use_container_width=True, height=500)
            with tabs[1]: st.dataframe(manpower_df, use_container_width=True)
            with tabs[2]: st.dataframe(holiday_df, use_container_width=True)
            with tabs[3]: st.dataframe(night_df, use_container_width=True)
            with tabs[4]:
                if not issues: st.success("🎉 太棒了！全班別全面完成交叉自動調度，每日實際人力 100% 完美滿足！")
                else: st.dataframe(pd.DataFrame(issues, columns=["姓名", "優化提醒"]), use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                schedule_df.to_excel(writer, sheet_name="班表")
                manpower_df.to_excel(writer, sheet_name="每日實際人力", index=False)
                holiday_df.to_excel(writer, sheet_name="休假統計", index=False)
                night_df.to_excel(writer, sheet_name="夜班統計", index=False)
                
            st.markdown("---")
            st.download_button(label="📥 下載兼職雙鎖定・終極完美 Excel", data=output.getvalue(), file_name=f"2F護理完美排班_{start_date.strftime('%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    except Exception as e:
        st.error(f"系統執行錯誤：{str(e)}")
else:
    st.info("💡 請上傳當月【預排休表】以啟動系統。")
