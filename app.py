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
    page_title="2F護理排班系統",
    layout="wide"
)

st.title("🏥 2F護理排班系統")

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

# =====================================
# 權限檢查
# =====================================

def can_work_shift(permission, shift):
    if shift in ["R", "off", "M"]:
        return True
    return shift in permission

# =====================================
# 讀取歷史班表狀態
# =====================================

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

# =====================================
# 讀取預排休表
# =====================================

def load_request_table(upload_file, names, num_days):
    result = {n: [""] * num_days for n in names}
    xl = pd.ExcelFile(upload_file)
    sheet_name = xl.sheet_names[0]
    df = pd.read_excel(upload_file, sheet_name=sheet_name)

    for _, row in df.iterrows():
        person = str(row.iloc[1]).strip()
        target = None
        for n in names:
            if n in person:
                target = n
                break

        if not target:
            continue

        for d in range(num_days):
            col = d + 2
            if col >= len(df.columns):
                continue

            value = str(row.iloc[col]).strip()
            if value == "nan" or value == "":
                continue

            value = value.upper()
            if value == "R":
                result[target][d] = "R"
            elif value == "D":
                result[target][d] = "D"
            elif value == "E":
                result[target][d] = "E"
            elif value == "N":
                result[target][d] = "N"
            elif "開會" in value or value == "M":
                result[target][d] = "M"

    return result

# =====================================
# 側邊設定
# =====================================

with st.sidebar:
    st.header("排班設定")
    
    start_date = st.date_input(
        "開始日期",
        datetime.date.today().replace(day=1)
    )
    end_date = st.date_input(
        "結束日期",
        datetime.date.today()
    )

    st.markdown("---")
    d_min = st.number_input("白班最低人數", value=4)
    d_max = st.number_input("白班最高人數", value=5)
    e_min = st.number_input("小夜最低人數", value=3)
    e_max = st.number_input("小夜最高人數", value=3)
    n_min = st.number_input("大夜最低人數", value=2)
    n_max = st.number_input("大夜最高人數", value=2)

    st.markdown("---")
    file_a = st.file_uploader("基本班表", type=["xlsx"])
    file_b = st.file_uploader("預排休表", type=["xlsx"])

# =====================================
# 排班主引擎
# =====================================
def generate_schedule(names, permissions, requests, num_days, d_min, e_min, n_min, history_shift, history_streak):
    schedule = {n: [""] * num_days for n in names}
    night_count = {n: 0 for n in names}  # 記錄夜班(E+N)總數
    work_count = {n: 0 for n in names}   # 記錄總工作天數

    # -----------------------------
    # STEP 1: 優先複製預排班（R、M、特定指定班）
    # -----------------------------
    for nurse in names:
        for d in range(num_days):
            if requests[nurse][d] != "":
                schedule[nurse][d] = requests[nurse][d]
                if requests[nurse][d] in ["D", "E", "N"]:
                    work_count[nurse] += 1
                    if requests[nurse][d] in ["E", "N"]:
                        night_count[nurse] += 1

    # -----------------------------
    # STEP 2: 大夜班 (N) 分配
    # -----------------------------
    for day in range(num_days):
        current_n = sum(1 for n in names if schedule[n][day] == "N")
        need_n = n_min - current_n
        if need_n <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse == "郭珍君":  # 兼職不排大夜
                continue
            if schedule[nurse][day] != "":  # 當天已有安排(包含R、M、D、E)則跳過
                continue
            if not can_work_shift(permissions[nurse], "N"):  # 無大夜權限跳過
                continue
            # 昨天下大夜，今天不能連上大夜（符合常規，除非歷史班表有寫）
            if day == 0 and history_shift.get(nurse) == "N":
                continue
            if day > 0 and schedule[nurse][day - 1] == "N":
                continue
                
            candidates.append(nurse)

        # 核心優化：先隨機打散，再依照夜班累計次數排序，確保公平性
        random.shuffle(candidates)
        candidates.sort(key=lambda x: (night_count[x], work_count[x]))

        for nurse in candidates[:need_n]:
            schedule[nurse][day] = "N"
            night_count[nurse] += 1
            work_count[nurse] += 1

            # N後固定休兩天 (若後面已有預排R或M則不強行覆蓋，其餘留白處強制off)
            if day + 1 < num_days and schedule[nurse][day + 1] == "":
                schedule[nurse][day + 1] = "off"
            if day + 2 < num_days and schedule[nurse][day + 2] == "":
                schedule[nurse][day + 2] = "off"

    # -----------------------------
    # STEP 3: 小夜班 (E) 分配
    # -----------------------------
    for day in range(num_days):
        current_e = sum(1 for n in names if schedule[n][day] == "E")
        need_e = e_min - current_e
        if need_e <= 0:
            continue

        candidates = []
        for nurse in names:
            if nurse == "郭珍君":  # 兼職不排小夜
                continue
            if schedule[nurse][day] != "":  # 當天已有安排(包含R、M、D、N、或大夜後的off)則跳過
                continue
            if not can_work_shift(permissions[nurse], "E"):  # 無小夜權限跳過
                continue
            candidates.append(nurse)

        # 核心優化：隨機打散後排序，防止特定人員被連續集火
        random.shuffle(candidates)
        candidates.sort(key=lambda x: (night_count[x], work_count[x]))

        for nurse in candidates[:need_e]:
            schedule[nurse][day] = "E"
            night_count[nurse] += 1
            work_count[nurse] += 1

    # -----------------------------
    # STEP 4: 白班 (D) 分配
    # -----------------------------
    for day in range(num_days):
        current_d = sum(1 for n in names if schedule[n][day] == "D")
        need_d = d_min - current_d
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
        candidates.sort(key=lambda x: work_count[x])  # 讓總班數少的人優先上白班

        for nurse in candidates[:need_d]:
            schedule[nurse][day] = "D"
            work_count[nurse] += 1

    # -----------------------------
    # STEP 5: 剩餘空格補 off
    # -----------------------------
    for nurse in names:
        for d in range(num_days):
            if schedule[nurse][d] == "":
                schedule[nurse][d] = "off"

    # -----------------------------
    # STEP 6: 郭珍君 (固定最多10天白班)
    # -----------------------------
    if "郭珍君" in names:
        nurse = "郭珍君"
        work_days = [d for d in range(num_days) if schedule[nurse][d] == "D"]
        if len(work_days) > 10:
            extra = len(work_days) - 10
            for idx in work_days[-extra:]:
                # 除非原本是預排會議 M，否則超過的白班變 off
                if requests[nurse][idx] != "M":
                    schedule[nurse][idx] = "off"

    # -----------------------------
    # STEP 7: 四週至少8天休 (郭珍君除外)
    # -----------------------------
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
            # 只拿非預排的常規白班來犧牲改成 off
            if schedule[nurse][d] == "D" and requests[nurse][d] == "":
                schedule[nurse][d] = "off"
                need -= 1

    # -----------------------------
    # STEP 8: 每週至少一天休
    # -----------------------------
    for nurse in names:
        for start in range(0, num_days, 7):
            end = min(start + 7, num_days)
            week = schedule[nurse][start:end]
            has_rest = any(x in ["off", "R"] for x in week)
            if not has_rest and (end - 1) < num_days:
                if schedule[nurse][end - 1] not in ["M", "R"]:
                    schedule[nurse][end - 1] = "off"

    # -----------------------------
    # STEP 9: 連續上班最多5天限制
    # -----------------------------
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

        # 生成日期標頭與星期
        num_days = (end_date - start_date).days + 1
        date_headers = []
        for i in range(num_days):
            curr = start_date + datetime.timedelta(days=i)
            w = WEEKDAYS_CHINESE[curr.weekday()]
            date_headers.append(f"{curr.strftime('%m/%d')}({w})")

        # 讀取預排班資料
        requests = load_request_table(file_b, names, num_days)

        st.subheader("👥 人員初始狀態確認與編輯")
        config_rows = []
        for nurse in names:
            config_rows.append({
                "姓名": nurse,
                "權限": staffs[nurse]["permission"],
                "上月最後班": staffs[nurse]["last_shift"],
                "已連上天數": staffs[nurse]["last_streak"]
            })

        config_df = st.data_editor(
            pd.DataFrame(config_rows),
            use_container_width=True,
            num_rows="fixed"
        )

        permissions = {}
        history_shift = {}
        history_streak = {}

        for _, row in config_df.iterrows():
            nurse = row["姓名"]
            permissions[nurse] = str(row["權限"]).upper()
            history_shift[nurse] = str(row["上月最後班"])
            history_streak[nurse] = int(row["已連上天數"])

        st.markdown("---")
        
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            with st.spinner("系統正在計算最適班表..."):
                result = generate_schedule(
                    names, permissions, requests, num_days,
                    d_min, e_min, n_min, history_shift, history_streak
                )
            st.success("🎉 班表排定完成！")

            tabs = st.tabs(["📅 最終班表", "📊 每日人力", "🏖️ 休假統計", "🌙 夜班統計", "🔍 規則檢查"])

            # =====================
            # TAB1 班表
            # =====================
            with tabs[0]:
                schedule_df = pd.DataFrame(result).T
                schedule_df.columns = date_headers
                schedule_df.insert(0, "班別權限", [permissions[n] for n in schedule_df.index])
                st.dataframe(schedule_df, use_container_width=True, height=500)

            # =====================
            # TAB2 每日人力
            # =====================
            with tabs[1]:
                manpower_rows = []
                for d in range(num_days):
                    d_count = sum(1 for n in names if result[n][d] == "D")
                    e_count = sum(1 for n in names if result[n][d] == "E")
                    n_count = sum(1 for n in names if result[n][d] == "N")
                    m_count = sum(1 for n in names if result[n][d] == "M")
                    manpower_rows.append([date_headers[d], d_count, e_count, n_count, m_count])

                manpower_df = pd.DataFrame(
                    manpower_rows, 
                    columns=["日期", "白班(D)", "小夜(E)", "大夜(N)", "會議/開會(M)"]
                )
                st.dataframe(manpower_df, use_container_width=True)

            # =====================
            # TAB3 休假統計
            # =====================
            with tabs[2]:
                holiday_rows = []
                for nurse in names:
                    r_count = sum(1 for x in result[nurse] if x == "R")
                    off_count = sum(1 for x in result[nurse] if x == "off")
                    holiday_rows.append([nurse, r_count, off_count, r_count + off_count])

                holiday_df = pd.DataFrame(holiday_rows, columns=["姓名", "預排休(R)", "常規OFF", "總休假天數"])
                st.dataframe(holiday_df, use_container_width=True)

            # =====================
            # TAB4 夜班統計
            # =====================
            with tabs[3]:
                night_rows = []
                for nurse in names:
                    e_count = sum(1 for x in result[nurse] if x == "E")
                    n_count = sum(1 for x in result[nurse] if x == "N")
                    night_rows.append([nurse, e_count, n_count, e_count + n_count])

                night_df = pd.DataFrame(night_rows, columns=["姓名", "小夜(E)", "大夜(N)", "夜班總計"])
                st.dataframe(night_df, use_container_width=True)

            # =====================
            # TAB5 規則檢查
            # =====================
            with tabs[4]:
                issues = []
                for nurse in names:
                    # 全職人員休假檢查
                    if nurse != "郭珍君":
                        total_rest = sum(1 for x in result[nurse] if x in ["off", "R"])
                        if total_rest < 8:
                            issues.append([nurse, f"符合勞基法排班不符：當月總休假不足 8 天 ({total_rest}天)"])

                    # 連續上班檢查
                    streak = 0
                    for shift in result[nurse]:
                        if shift in ["D", "E", "N"]:
                            streak += 1
                        else:
                            streak = 0
                        if streak > 5:
                            issues.append([nurse, "違反連續上班上限：連續工作超過 5 天"])
                            break

                    # 兼職郭珍君專屬檢查
                    if nurse == "郭珍君":
                        d_count = sum(1 for x in result[nurse] if x == "D")
                        if d_count > 10:
                            issues.append([nurse, f"兼職人員排班限制：白班超過 10 天 ({d_count}天)"])
                        if any(x in ["E", "N"] for x in result[nurse]):
                            issues.append([nurse, "兼職人員排班錯誤：出現非白班(E/N班)"])

                if len(issues) == 0:
                    st.success("🎉 太棒了！所有排班皆完美符合勞基法與內部規則！")
                else:
                    issue_df = pd.DataFrame(issues, columns=["姓名", "異常說明"])
                    st.warning("⚠️ 發現部分排班衝突，請參考下方提示手動微調：")
                    st.dataframe(issue_df, use_container_width=True)

            # =====================
            # Excel 匯出下載
            # =====================
            st.markdown("---")
            output = BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                schedule_df.to_excel(writer, sheet_name="班表")
                manpower_df.to_excel(writer, sheet_name="每日人力", index=False)
                holiday_df.to_excel(writer, sheet_name="休假統計", index=False)
                night_df.to_excel(writer, sheet_name="夜班統計", index=False)
                if len(issues) > 0:
                    pd.DataFrame(issues, columns=["姓名", "異常說明"]).to_excel(writer, sheet_name="規則檢查", index=False)

            st.download_button(
                label="📥 下載排班結果 Excel 檔案",
                data=output.getvalue(),
                file_name=f"2F護理排班結果_{start_date.strftime('%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:
        st.error(f"系統執行時發生錯誤：{str(e)}")
else:
    st.info("💡 請同時在上方的側邊欄上傳【基本班表】與【預排休表】Excel 檔案以啟動系統。")
