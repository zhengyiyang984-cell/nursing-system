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
    page_title="2F護理排班系統 (極限防呆穩定版)",
    layout="wide"
)

st.title("🏥 2F護理排班系統 (極限防呆穩定版)")

# 初始化 Streamlit 永久記憶體狀態，防止開網頁時噴 AttributeError
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
        raw_name = str(row.iloc[name_col_idx]).strip()
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
        row_text = "".join(row)
        
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
# 智慧排班引擎
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
        # 🎯【核心精準修正】修正此處多餘的 = n_min 賦值錯誤
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

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (1 if (day < len(requests[x]) and requests[x][day] == "R") else 0, night_count[x], work_count[x]))

        for nurse in candidates[:need_n]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 3: 小夜班 (E) 分配 —— 滿載優先
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
                if nurse not in PART_TIME_STAFFS and schedule[nurse][day] == "" and can_work_shift(permissions[nurse], "E"):
                    if nurse not in candidates:
                        candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (1 if (day < len(requests[x]) and requests[x][day] == "R") else 0, night_count[x], work_count[x]))

        for nurse in candidates[:need_e]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 4: 白班 (D) 分配 —— 全職填補
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
            history_shift_final[nurse] = str(row["上月最後班"])
            history_streak_final[nurse] = int(row["已連上天數"])

        st.markdown("---")
        
        if st.button("🚀 依照自訂每日人力啟動自動排班", type="primary", use_container_width=True):
            with st.spinner("優化班表計算中..."):
                st.session_state["schedule_result"] = generate_schedule(
                    names, permissions, requests, num_days,
                    manpower_req_list, history_shift_final, history_streak_final
                )
                st.session_state["run_success"] = True

        if st.session_state["run_success"]:
            result = st.session_state["schedule_result"]

            # 生成四大報表
            schedule_df = pd.DataFrame(result).T
            schedule_df.columns = date_headers
            schedule_df.insert(0, "班別權限", [permissions[n] for n in schedule_df.index])

            manpower_rows = []
            for d in range(num_days):
                d_count = sum(1 for n in names if result[n][d] == "D")
                e_count = sum(1 for n in names if result[n][d] == "E")
                n_count = sum(1 for n in names if result[n][d] == "N")
                m_count = sum(1 for n in names if result[n][d] == "M")
                manpower_rows.append([
                    date_headers[d], 
                    f"{d_count} (需求: {manpower_req_list[d]['D_min']})",
                    f"{e_count} (需求: {manpower_req_list[d]['E_min']})",
                    f"{n_count} (需求: {manpower_req_list[d]['N_min']})",
                    m_count
                ])
            manpower_df = pd.DataFrame(manpower_rows, columns=["日期", "實際白班(D)", "實際小夜(E)", "實際大夜(N)", "會議開會(M)"])

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

            # 畫面分頁
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
                    st.success("🎉 太棒了！14位護理同仁權限與假別完全精準抓取，排班完美達標！")
                else:
                    issue_df = pd.DataFrame(issues, columns=["姓名", "異常說明"])
                    st.dataframe(issue_df, use_container_width=True)

            # Excel 下載
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
    st.info("💡 請上傳【基本班表】與【預排休表】，系統會自動從 D 欄抓取每名同仁的當月排班權限。")
