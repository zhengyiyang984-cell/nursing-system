import streamlit as st
import pandas as pd
import datetime
import random
from io import BytesIO

# =====================================
# 1. 基礎設定與對齊真實名單
# =====================================
st.set_page_config(page_title="2F護理排班系統", layout="wide")
st.title("🏥 2F護理排班系統 (名單完全對齊・休假保底完全體)")

# 🎯 真實名單：移除陳威宇，對齊檔案
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡微", "溫鈺羚"
]
PART_TIME_STAFFS = ["郭珍君"] 

# =====================================
# 2. 排班核心邏輯
# =====================================
def generate_schedule(names, permissions, requests, num_days, manpower_req, history_shift, history_streak):
    schedule = {n: [""] * num_days for n in names}
    work_count = {n: 0 for n in names}

    # 填入預排與會議
    for nurse in names:
        for d in range(num_days):
            if requests[nurse][d] in ["D", "E", "N", "M"]:
                schedule[nurse][d] = requests[nurse][d]
                work_count[nurse] += 1

    # 滿足最低人力需求
    for day in range(num_days):
        for s in ["N", "E", "D"]:
            min_req = manpower_req[day][f"{s}_min"]
            current = sum(1 for n in names if schedule[n][day] == s)
            candidates = [n for n in names if schedule[n][day] == "" and (s in permissions.get(n, "DEN"))]
            for n in candidates[:max(0, min_req - current)]:
                schedule[n][day] = s
                work_count[n] += 1

    # 🎯【核心優化】：強制確保休假天數 >= 8 天
    for nurse in names:
        if nurse not in PART_TIME_STAFFS:
            off_days = sum(1 for d in range(num_days) if schedule[nurse][d] in ["", "off", "R"])
            # 若少於 8 天，強行銷班還假
            while off_days < 8:
                for d in range(num_days):
                    if schedule[nurse][d] in ["D", "E", "N"]:
                        schedule[nurse][d] = "off"
                        off_days += 1
                        break
                else: break

    # 補滿空格
    for n in names:
        for d in range(num_days):
            if schedule[n][d] == "": schedule[n][d] = "off"
    return schedule

# =====================================
# 3. Streamlit UI 流程 (請保留您原有的上傳元件)
# =====================================
# (確保您的檔案讀取部分使用了 CORE_STAFF_NAMES)
# =====================================
# 2. 資料讀取函式
# =====================================
def load_request_and_permissions(upload_file, names, num_days):
    requests_dict = {n: [""] * num_days for n in names}
    permissions_dict = {n: "DEN" for n in names}
    df = pd.read_excel(upload_file, header=None)
    header_row_idx = 0
    name_col_idx = 1
    # 簡化讀取邏輯
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    for _, row in df.iterrows():
        name = str(row.iloc[name_col_idx]).strip()
        target = next((n for n in names if n in name), None)
        if target:
            requests_dict[target] = [str(x) if pd.notna(x) else "" for x in row.iloc[name_col_idx+3:name_col_idx+3+num_days]]
    return requests_dict, permissions_dict

# =====================================
# 3. 排班運算核心
# =====================================
def generate_schedule(names, permissions, requests, num_days, manpower_req, history_shift, history_streak):
    schedule = {n: [""] * num_days for n in names}
    work_count = {n: 0 for n in names}

    # 基礎填充
    for nurse in names:
        for d in range(num_days):
            if requests[nurse][d] in ["D", "E", "N", "M"]:
                schedule[nurse][d] = requests[nurse][d]
                work_count[nurse] += 1

    # 簡單的人力補足 (滿足最低人力)
    for day in range(num_days):
        for s in ["N", "E", "D"]:
            min_req = manpower_req[day][f"{s}_min"]
            current = sum(1 for n in names if schedule[n][day] == s)
            candidates = [n for n in names if schedule[n][day] == ""]
            for n in candidates[:max(0, min_req - current)]:
                schedule[n][day] = s
                work_count[n] += 1

    # 4. 休假天數調整 (滿足 8 天底線)
    for nurse in names:
        if nurse not in PART_TIME_STAFFS:
            off_count = sum(1 for d in range(num_days) if schedule[nurse][d] in ["", "R", "off"])
            while off_count < 8:
                # 強制騰出空間變 off
                for d in range(num_days):
                    if schedule[nurse][d] in ["D", "E", "N"]:
                        schedule[nurse][d] = "off"
                        off_count += 1
                        break
    
    # 5. 補滿空格
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "": schedule[nurse][d] = "off"
            
    return schedule

# =====================================
# 4. Streamlit UI 流程
# =====================================
file_a = st.sidebar.file_uploader("上傳舊班表", type=["xlsx"])
file_b = st.sidebar.file_uploader("上傳預排休表", type=["xlsx"])

if file_b:
    num_days = 30 # 假設為 30 天
    requests, perms = load_request_and_permissions(file_b, CORE_STAFF_NAMES, num_days)
    history_shift, history_streak = load_history_only(file_a, CORE_STAFF_NAMES)
    
    # 預設人力需求
    manpower_req = [{"D_min": 4, "E_min": 3, "N_min": 2} for _ in range(num_days)]
    
    if st.button("🚀 執行排班"):
        result = generate_schedule(CORE_STAFF_NAMES, perms, requests, num_days, manpower_req, history_shift, history_streak)
        st.dataframe(pd.DataFrame(result).T)
        
        # 休假檢查
        issues = []
        for n in CORE_STAFF_NAMES:
            if n not in PART_TIME_STAFFS:
                off_days = sum(1 for x in result[n] if x == "off")
                if off_days < 8:
                    issues.append({"姓名": n, "優化提醒": f"休假不足 8 天 (僅 {off_days} 天)"})
        if issues:
            st.warning("⚠️ 部分同仁休假不足")
            st.table(pd.DataFrame(issues))

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
        candidates.sort(key=lambda x: (25 if (day > 0 and schedule[x][day-1] == "N") or (day == 0 and history_shift.get(x) == "N") else 0, get_work_continuation_weight(x, day), -work_count[x], night_count[x]), reverse=True)
        
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
        candidates.sort(key=lambda x: (get_work_continuation_weight(x, day), -work_count[x], night_count[x]), reverse=True)
        
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

    # STEP 5: 半職郭珍君精準 10 天塊狀限制
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

    # STEP 5.5:【全班別交叉救火 - 常規與終極破鎖大腦整合防線】
    for day in range(num_days):
        for shift_type in ["N", "E", "D"]:
            min_req = manpower_req[day][f"{shift_type}_min"]
            current_count = sum(1 for n in names if schedule[n][day] == shift_type)
            
            while current_count < min_req:
                possible_rescuers = []
                for nurse in names:
                    if nurse in PART_TIME_STAFFS: continue 
                    if schedule[nurse][day] != "": continue
                    if not is_shift_safe(nurse, day, shift_type): continue
                    
                    has_neighbor = False
                    if day > 0 and schedule[nurse][day-1] in ["D", "E", "N"]: has_neighbor = True
                    if day < num_days - 1 and schedule[nurse][day+1] in ["D", "E", "N"]: has_neighbor = True
                    if day == 0 and history_shift.get(nurse) in ["D", "E", "N"]: has_neighbor = True
                    
                    possible_rescuers.append((nurse, has_neighbor))
                    
                if not possible_rescuers: 
                    # 啟動極限破鎖
                    for nurse in names:
                        if nurse in PART_TIME_STAFFS or schedule[nurse][day] != "": continue
                        iron_safe = True
                        if shift_type == "D" and day > 0 and schedule[nurse][day-1] in ["N", "E"]: iron_safe = False
                        if shift_type == "E" and day > 0 and schedule[nurse][day-1] == "N": iron_safe = False
                        if shift_type == "N" and day > 0 and schedule[nurse][day-1] in ["D", "E"]: iron_safe = False
                        if iron_safe: possible_rescuers.append((nurse, False))
                    if not possible_rescuers: break
                
                possible_rescuers.sort(key=lambda x: (1 if x[1] else 0, -sum(1 for s in schedule[x[0]] if s in ["D", "E", "N"])), reverse=True)
                chosen_nurse = possible_rescuers[0][0]
                schedule[chosen_nurse][day] = shift_type
                
                # 自動連帶補班防碎班
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

    # 🎯 STEP 7:【全職休假均勻平衡與全自動 1 天碎班清除引擎】
    full_time_nurses = [n for n in names if n not in PART_TIME_STAFFS]
    
    # 大平準校正：拉高休假平準化循環次數，並導入跨人班別轉移，死守 3 人休假
    for loop in range(15):
        current_holidays = {n: sum(1 for x in schedule[n] if x in ["off", "R"]) for n in full_time_nurses}
        under_rest = [n for n in full_time_nurses if current_holidays[n] < 8]
        if not under_rest: break
            
        for d in range(num_days):
            for shift_type in ["D", "E", "N"]:
                c_count = sum(1 for n in names if schedule[n][d] == shift_type)
                
                # 策略 A：如果當天原本的人數大於最低限度，直接無痛退班變 off！
                if c_count > manpower_req[d][f"{shift_type}_min"]:
                    under_rest.sort(key=lambda x: current_holidays[x])
                    for target_nurse in under_rest:
                        if schedule[target_nurse][d] == shift_type and (d < len(requests[target_nurse]) and requests[target_nurse][d] == ""):
                            schedule[target_nurse][d] = "off"
                            current_holidays[target_nurse] += 1
                            break
                    break
                
                # 策略 B：如果人數「剛好壓在最低限制」，則尋找有沒有假很多的人（休假天數 >= 9天）出來交叉頂替！
                elif c_count == manpower_req[d][f"{shift_type}_min"]:
                    under_rest.sort(key=lambda x: current_holidays[x])
                    for target_nurse in under_rest:
                        if schedule[target_nurse][d] == shift_type and (d < len(requests[target_nurse]) and requests[target_nurse][d] == ""):
                            helpers = [n for n in full_time_nurses if schedule[n][d] == "off" and current_holidays[n] >= 9 and can_work_shift(permissions[n], shift_type) and is_shift_safe(n, d, shift_type)]
                            if helpers:
                                chosen_helper = random.choice(helpers)
                                schedule[target_nurse][d] = "off"
                                schedule[chosen_helper][d] = shift_type
                                current_holidays[target_nurse] += 1
                                current_holidays[chosen_helper] -= 1
                                break
                    break

    # 階段二：全自動碎班相連抹除器（1天班自動抹平或靠攏串聯）
    for n in full_time_nurses:
        for d in range(num_days):
            if schedule[n][d] in ["D", "E", "N"]:
                is_left_off = (d == 0 and history_shift.get(n) in ["off", "R"]) or (d > 0 and schedule[n][d-1] in ["off", "R"])
                is_right_off = (d == num_days - 1) or (d < num_days - 1 and schedule[n][d+1] in ["off", "R"])
                
                if is_left_off and is_right_off: 
                    curr_shift = schedule[n][d]
                    d_count = sum(1 for name in names if schedule[name][d] == curr_shift)
                    if d_count > manpower_req[d][f"{curr_shift}_min"] and (d < len(requests[n]) and requests[n][d] == ""):
                        schedule[n][d] = "off"
                    else:
                        if d < num_days - 1 and (d+1 < len(requests[n]) and requests[n][d+1] == "") and is_shift_safe(n, d+1, curr_shift):
                            schedule[n][d+1] = curr_shift
                        elif d > 0 and (d-1 < len(requests[n]) and requests[n][d-1] == "") and is_shift_safe(n, d-1, curr_shift):
                            schedule[n][d-1] = curr_shift
    return schedule

# =====================================
# Streamlit 主程式介面
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
            sub_df = manpower_editor_df[manpower_editor_df["week_id"] == d_info["week_label"]]
            match_row = sub_df[sub_df["is_we"] == d_info["is_weekend"]].iloc[0]
            
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
        if st.button("🚀 啟動全智慧臨床優化平衡排班系統", type="primary", use_container_width=True):
            with st.spinner("正在執行大數據平衡，還回林欣蓓、陳萱芸、林怡微的法定休假中..."):
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
                # 🎯【精準修復語法】：將上一版打錯的 1_count 徹底抹除，回歸最標準健康的 Pandas 人力統計
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
            # 每日人力要求規格核查
            for d in range(num_days):
                d_count = sum(1 for n in names if result[n][d] == "D")
                e_count = sum(1 for n in names if result[n][d] == "E")
                n_count = sum(1 for n in names if result[n][d] == "N")
                
                if d_count < manpower_req_list[d]['D_min']:
                    issues.append(["🚨 每日人力未滿", f"【{date_headers[d]}】白班(D)目前僅有 {d_count} 人，未達最低要求 {manpower_req_list[d]['D_min']} 人！"])
                if e_count < manpower_req_list[d]['E_min']:
                    issues.append(["🚨 每日人力未滿", f"【{date_headers[d]}】小夜班(E)目前僅有 {e_count} 人，未達最低要求 {manpower_req_list[d]['E_min']} 人！"])
                if n_count < manpower_req_list[d]['N_min']:
                    issues.append(["🚨 每日人力未滿", f"【{date_headers[d]}】大夜班(N)目前僅有 {n_count} 人，未達最低要求 {manpower_req_list[d]['N_min']} 人！"])

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

            tabs = st.tabs(["📅 最終班表", "📊 每日實際人力", "🏖️ 休假統計", "🌙 夜班統計", "🔍 班表檢查與急救警報"])
            with tabs[0]: st.dataframe(schedule_df, use_container_width=True, height=500)
            with tabs[1]: st.dataframe(manpower_df, use_container_width=True)
            with tabs[2]: st.dataframe(holiday_df, use_container_width=True)
            with tabs[3]: st.dataframe(night_df, use_container_width=True)
            with tabs[4]:
                if not issues: st.success("🎉 終極保底平衡成功！林欣蓓、陳萱芸、林怡微休假全數安全重回大於等於 8 天，全月無碎班、人力 100% 滿足！")
                else: st.dataframe(pd.DataFrame(issues, columns=["對象 / 類別", "優化與急救警報提醒"]), use_container_width=True)

            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                schedule_df.to_excel(writer, sheet_name="班表")
                manpower_df.to_excel(writer, sheet_name="每日實際人力", index=False)
                holiday_df.to_excel(writer, sheet_name="休假統計", index=False)
                night_df.to_excel(writer, sheet_name="夜班統計", index=False)
                
            st.markdown("---")
            st.download_button(label="📥 下載Excel", data=output.getvalue(), file_name=f"2F護理完美排班_{start_date.strftime('%m%d')}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)
    except Exception as e:
        st.error(f"系統執行錯誤：{str(e)}")
else:
    st.info("💡 請上傳當月【預排休表】以啟動系統。")
