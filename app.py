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
    page_title="2F護理排班系統 (動態人力版)",
    layout="wide"
)

st.title("🏥 2F護理排班系統 (動態人力版)")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇"
]

def load_base_schedule(upload_file):
    df = pd.read_excel(upload_file, header=None)
    staffs = {}
    for r in range(len(df)):
        row = [str(x).strip() for x in df.iloc[r].values]
        row_text = "".join(row)
        for nurse in CORE_STAFF_NAMES:
            if nurse in row_text:
                permission = "DEN"
                for cell in row:
                    cell = str(cell).upper()
                    if cell in ["D", "E", "N", "DE", "DN", "EN", "DEN"]:
                        permission = cell
                staffs[nurse] = {
                    "permission": permission,
                    "last_shift": "off",
                    "last_streak": 0,
                    "part_time": (nurse == "郭珍君")
                }
    return staffs

def can_work_shift(permission, shift):
    if shift in ["R", "off", "M"]:
        return True
    return shift in permission

def load_history_from_base_schedule(upload_file, staffs):
    df = pd.read_excel(upload_file, header=None)
    for r in range(len(df)):
        row = [str(x).strip() for x in df.iloc[r].values]
        row_text = "".join(row)
        target = None
        for nurse in staffs.keys():
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
        staffs[target]["last_shift"] = shifts[-1]
        streak = 0
        for s in reversed(shifts):
            if s in ["D", "E", "N"]:
                streak += 1
            else:
                break
        staffs[target]["last_streak"] = streak
    return staffs

def load_request_table(upload_file, names, num_days):
    """
    精準抓取預排休表內容
    names: 系統核心人員名單 (CORE_STAFF_NAMES)
    num_days: 當月總天數 (例如 6 月就是 30 天)
    """
    # 初始化回傳結果，預設每個人每天都是空字串
    result = {n: [""] * num_days for n in names}
    
    # 讀取 Excel 檔案的第一張工作表 (通常就是複製出來的那張預排表)
    xl = pd.ExcelFile(upload_file)
    sheet_name = xl.sheet_names[0]
    
    # 為了防範 Excel 前面有 1~2 行的空白或大標題，我們不指定 header，由程式自己找
    df = pd.read_excel(upload_file, sheet_name=sheet_name, header=None)
    
    # --- 步驟 1：自動尋找「表頭行」與「姓名欄」 ---
    header_row_idx = 0
    name_col_idx = 1 # 預設安全牌
    
    for idx, row in df.iterrows():
        row_str = [str(x) for x in row.values]
        # 尋找哪一行同時出現了 "姓名" 或類似護理排班的關鍵字
        if any("姓名" in s or "人員" in s or "稱" in s for s in row_str):
            header_row_idx = idx
            # 抓出「姓名」具體在哪一欄
            for col_idx, cell_value in enumerate(row_str):
                if "姓名" in cell_value or "人員" in cell_value:
                    name_col_idx = col_idx
                    break
            break

    # --- 步驟 2：重新設定 DataFrame 的表頭 ---
    # 將找到的那一行作為欄位名稱，並切除前面的無用大標題行
    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1 :].reset_index(drop=True)
    
    # --- 步驟 3：開始逐行掃描同仁的預排內容 ---
    for _, row in df.iterrows():
        # 取得當前橫列的同仁姓名
        raw_name = str(row.iloc[name_col_idx]).strip()
        
        # 檢查這個名字有沒有在我們的主系統名單 (names) 裡面
        target_nurse = None
        for n in names:
            if n in raw_name:
                target_nurse = n
                break
                
        # 如果這一行不是我們要排班的護理同仁（可能是空白行或合計行），就跳過
        if not target_nurse:
            continue
            
        # --- 步驟 4：精準抓取第 1 天到第 num_days 天的格子 ---
        # 姓名欄後面通常緊接著就是 1 號、2 號... 的排班格子
        start_data_col = name_col_idx + 1
        
        for d in range(num_days):
            current_col_idx = start_data_col + d
            
            # 安全防呆：防範日期超出 Excel 的欄位右邊界
            if current_col_idx >= len(df.columns):
                continue
                
            # 抓取該格子的原始數值
            cell_value = str(row.iloc[current_col_idx]).strip()
            
            # 排除無意義的 NaN 或空值
            if cell_value == "nan" or cell_value == "":
                continue
                
            # 轉成大寫進行比對
            cell_value_upper = cell_value.upper()
            
            # 判定假別與開會狀態
            if cell_value_upper in ["R", "D", "E", "N"]:
                result[target_nurse][d] = cell_value_upper
            elif "開會" in cell_value or cell_value_upper == "M":
                result[target_nurse][d] = "M"
            elif "休" in cell_value:
                result[target_nurse][d] = "R"  # 有些人習慣打中文「休」，自動轉成 R
                
    return result

# =====================================
# 側邊設定 (僅保留日期與上傳)
# =====================================

with st.sidebar:
    st.header("📅 日期與檔案設定")
    start_date = st.date_input("開始日期", datetime.date.today().replace(day=1))
    end_date = st.date_input("結束日期", datetime.date.today())
    st.markdown("---")
    file_a = st.file_uploader("基本班表", type=["xlsx"])
    file_b = st.file_uploader("預排休表", type=["xlsx"])

# =====================================
# 動態排班主引擎
# =====================================

def generate_schedule(names, permissions, requests, num_days, manpower_req, history_shift, history_streak):
    """
    manpower_req: 傳入一個 List[Dict]，包含每天各自的 D_min, E_min, N_min
    """
    schedule = {n: [""] * num_days for n in names}
    night_count = {n: 0 for n in names}
    work_count = {n: 0 for n in names}

    # STEP 1: 複製預排班
    for nurse in names:
        for d in range(num_days):
            if requests[nurse][d] != "":
                schedule[nurse][d] = requests[nurse][d]
                if requests[nurse][d] in ["D", "E", "N"]:
                    work_count[nurse] += 1
                    if requests[nurse][d] in ["E", "N"]:
                        night_count[nurse] += 1

    # STEP 2: 動態大夜班 (N)
    for day in range(num_days):
        req_n_min = manpower_req[day]["N_min"]  # 讀取該日期特定的大夜最低人數
        current_n = sum(1 for n in names if schedule[n][day] == "N")
        need_n = req_n_min - current_n
        if need_n <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse == "郭珍君":
                continue
            if schedule[nurse][day] != "":
                continue
            if not can_work_shift(permissions[nurse], "N"):
                continue
            if day == 0 and history_shift.get(nurse) == "N":
                continue
            if day > 0 and schedule[nurse][day - 1] == "N":
                continue
            candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (night_count[x], work_count[x]))

        for nurse in candidates[:need_n]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1
            if day + 1 < num_days and schedule[nurse][day + 1] == "":
                schedule[nurse][day + 1] = "off"
            if day + 2 < num_days and schedule[nurse][day + 2] == "":
                schedule[nurse][day + 2] = "off"

    # STEP 3: 動態小夜班 (E)
    for day in range(num_days):
        req_e_min = manpower_req[day]["E_min"]  # 讀取該日期特定的小夜最低人數
        current_e = sum(1 for n in names if schedule[n][day] == "E")
        need_e = req_e_min - current_e
        if need_e <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse == "郭珍君":
                continue
            if schedule[nurse][day] != "":
                continue
            if not can_work_shift(permissions[nurse], "E"):
                continue
            candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: (night_count[x], work_count[x]))

        for nurse in candidates[:need_e]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # STEP 4: 動態白班 (D)
    for day in range(num_days):
        req_d_min = manpower_req[day]["D_min"]  # 讀取該日期特定的白班最低人數
        current_d = sum(1 for n in names if schedule[n][day] == "D")
        need_d = req_d_min - current_d
        if need_d <= 0:
            continue

        candidates = []
        for nurse in names:
            if schedule[nurse][day] != "":
                continue
            if not can_work_shift(permissions[nurse], "D"):
                continue
            candidates.append(nurse)

        random.shuffle(candidates)
        candidates.sort(key=lambda x: work_count[x])

        for nurse in candidates[:need_d]:
            schedule[nurse][day] = "D"
            work_count[nurse] += 1

    # STEP 5至9：其餘勞基法常規限制維持（包含郭珍君10天白班規則）
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "":
                schedule[nurse][d] = "off"

    if "郭珍君" in names:
        nurse = "郭珍君"
        work_days = [d for d in range(num_days) if schedule[nurse][d] == "D"]
        if len(work_days) > 10:
            extra = len(work_days) - 10
            for idx in work_days[-extra:]:
                if requests[nurse][idx] != "M":
                    schedule[nurse][idx] = "off"

    for nurse in names:
        if nurse == "郭珍君":
            continue
        holiday_count = sum(1 for x in schedule[nurse] if x in ["off", "R"])
        if holiday_count >= 8:
            continue
        need = 8 - holiday_count
        for d in range(num_days):
            if need <= 0:
                break
            if schedule[nurse][d] == "D" and requests[nurse][d] == "":
                schedule[nurse][d] = "off"
                need -= 1

    for nurse in names:
        for start in range(0, num_days, 7):
            end = min(start + 7, num_days)
            week = schedule[nurse][start:end]
            has_rest = any(x in ["off", "R"] for x in week)
            if not has_rest and (end - 1) < num_days:
                if schedule[nurse][end - 1] not in ["M", "R"]:
                    schedule[nurse][end - 1] = "off"

    for nurse in names:
        streak = history_streak.get(nurse, 0)
        for d in range(num_days):
            if schedule[nurse][d] in ["D", "E", "N"]:
                streak += 1
            else:
                streak = 0
            if streak > 5:
                if schedule[nurse][d] not in ["R", "M"]:
                    schedule[nurse][d] = "off"
                streak = 0

    return schedule

# =====================================
# 主程式
# =====================================

if file_a and file_b:
    try:
        staffs = load_base_schedule(file_a)
        staffs = load_history_from_base_schedule(file_a, staffs)
        names = list(staffs.keys())

        # 1. 計算日期區間並產出格式化標頭
        num_days = (end_date - start_date).days + 1
        date_headers = []
        manpower_setup_rows = []

        for i in range(num_days):
            curr = start_date + datetime.timedelta(days=i)
            w = WEEKDAYS_CHINESE[curr.weekday()]
            date_str = curr.strftime('%m/%d')
            full_header = f"{date_str}({w})"
            date_headers.append(full_header)
            
            # 預設值設定：如果是週六(5)或週日(6)，自動調降預設人力，平日維持原預設
            if curr.weekday() in [5, 6]:
                manpower_setup_rows.append({
                    "日期": full_header, "白班最低(D)": 3, "小夜最低(E)": 2, "大夜最低(N)": 2
                })
            else:
                manpower_setup_rows.append({
                    "日期": full_header, "白班最低(D)": 4, "小夜最低(E)": 3, "大夜最低(N)": 2
                })

        # --- 畫面佈局：左邊確認同仁，右邊自訂每天人數 ---
        col1, col2 = st.columns([1, 1.2])
        
        with col1:
            st.subheader("👥 1. 人員初始狀態確認")
            config_rows = []
            for nurse in names:
                config_rows.append({
                    "姓名": nurse,
                    "權限": staffs[nurse]["permission"],
                    "上月最後班": staffs[nurse]["last_shift"],
                    "已連上天數": staffs[nurse]["last_streak"]
                })
            config_df = st.data_editor(pd.DataFrame(config_rows), use_container_width=True, num_rows="fixed")

        with col2:
            st.subheader("📊 2. 自訂每日最低人力需求")
            st.caption("💡 你可以直接點擊下方表格，自由修改特定日期的排班人數需求（例如將跨年或特定假日調低）。")
            manpower_editor_df = st.data_editor(pd.DataFrame(manpower_setup_rows), use_container_width=True, num_rows="fixed")

        # 解析使用者自訂的每日人力
        manpower_req_list = []
        for _, row in manpower_editor_df.iterrows():
            manpower_req_list.append({
                "D_min": int(row["白班最低(D)"]),
                "E_min": int(row["小夜最低(E)"]),
                "N_min": int(row["大夜最低(N)"])
            })

        # 解析同仁權限與歷史狀態
        permissions = {}
        history_shift = {}
        history_streak = {}
        for _, row in config_df.iterrows():
            nurse = row["姓名"]
            permissions[nurse] = str(row["權限"]).upper()
            history_shift[nurse] = str(row["上月最後班"])
            history_streak[nurse] = int(row["已連上天數"])

        requests = load_request_table(file_b, names, num_days)

        st.markdown("---")
        
        # 啟動排班按鈕
        if st.button("🚀 依照自訂每日人力啟動自動排班", type="primary", use_container_width=True):
            with st.spinner("系統正在讀取您的每日自訂人力，並計算最合適的護理班表..."):
                result = generate_schedule(
                    names, permissions, requests, num_days,
                    manpower_req_list, history_shift, history_streak
                )
            st.success("🎉 班表排定完成！")

            tabs = st.tabs(["📅 最終班表", "📊 每日實際人力", "🏖️ 休假統計", "🌙 夜班統計", "🔍 規則檢查"])

            # TAB1: 最終班表呈現
            with tabs[0]:
                schedule_df = pd.DataFrame(result).T
                schedule_df.columns = date_headers
                schedule_df.insert(0, "班別權限", [permissions[n] for n in schedule_df.index])
                st.dataframe(schedule_df, use_container_width=True, height=500)

            # TAB2: 每日實際人力
            with tabs[1]:
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
                st.dataframe(manpower_df, use_container_width=True)

            # TAB3: 休假統計
            with tabs[2]:
                holiday_rows = []
                for nurse in names:
                    r_count = sum(1 for x in result[nurse] if x == "R")
                    off_count = sum(1 for x in result[nurse] if x == "off")
                    holiday_rows.append([nurse, r_count, off_count, r_count + off_count])
                holiday_df = pd.DataFrame(holiday_rows, columns=["姓名", "預排休(R)", "常規OFF", "總休假天數"])
                st.dataframe(holiday_df, use_container_width=True)

            # TAB4: 夜班統計
            with tabs[3]:
                night_rows = []
                for nurse in names:
                    e_count = sum(1 for x in result[nurse] if x == "E")
                    n_count = sum(1 for x in result[nurse] if x == "N")
                    night_rows.append([nurse, e_count, n_count, e_count + n_count])
                night_df = pd.DataFrame(night_rows, columns=["姓名", "小夜(E)", "大夜(N)", "夜班總計"])
                st.dataframe(night_df, use_container_width=True)

            # TAB5: 規則檢查
            with tabs[4]:
                issues = []
                for nurse in names:
                    if nurse != "郭珍君":
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
                    if nurse == "郭珍君":
                        d_count = sum(1 for x in result[nurse] if x == "D")
                        if d_count > 10:
                            issues.append([nurse, f"兼職人員排班限制：白班超過 10 天 ({d_count}天)"])
                        if any(x in ["E", "N"] for x in result[nurse]):
                            issues.append([nurse, "兼職人員排班錯誤：出現非白班(E/N班)"])

                if len(issues) == 0:
                    st.success("🎉 太棒了！在您指定的每日人力配置下，排班皆完美符合內部規則與勞基法！")
                else:
                    issue_df = pd.DataFrame(issues, columns=["姓名", "異常說明"])
                    st.warning("⚠️ 在目前自訂的人力配置下，部分規則產生衝突，請手動進行微調：")
                    st.dataframe(issue_df, use_container_width=True)

            # 下載 Excel
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                schedule_df.to_excel(writer, sheet_name="班表")
                manpower_df.to_excel(writer, sheet_name="每日實際人力", index=False)
                holiday_df.to_excel(writer, sheet_name="休假統計", index=False)
                night_df.to_excel(writer, sheet_name="夜班統計", index=False)
            st.download_button(
                label="📥 下載彈性排班結果 Excel",
                data=output.getvalue(),
                file_name=f"2F護理排班結果_自訂人力_{start_date.strftime('%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"系統執行時發生錯誤：{str(e)}")
else:
    st.info("💡 請同時在上方的側邊欄上傳【基本班表】與【預排休表】Excel 檔案以開啟彈性排班面板。")
