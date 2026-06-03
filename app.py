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

WEEKDAYS_CHINESE = [
    "一", "二", "三", "四", "五", "六", "日"
]

CORE_STAFF_NAMES = [
    "郭珍君",
    "李雅慧",
    "蔡靜如",
    "陳慧屏",
    "劉榆琳",
    "黃家靜",
    "許雅雯",
    "陳義樺",
    "林欣蓓",
    "陳萱芸",
    "汪家容",
    "林欣儀",
    "林怡薇"
]
# =====================================
# 權限解析
# =====================================

def parse_permission(text):

    text = str(text).upper().strip()

    if "DEN" in text:
        return "DEN"

    if "DE" in text:
        return "DE"

    if "DN" in text:
        return "DN"

    if "EN" in text:
        return "EN"

    if text == "D":
        return "D"

    if text == "E":
        return "E"

    if text == "N":
        return "N"

    return None
    # =====================================
# 權限檢查
# =====================================

def can_work_shift(permission, shift):

    if shift in ["R", "off", "M"]:
        return True

    return shift in permission
    # =====================================
# 讀取基本班表
# =====================================

def load_base_schedule(upload_file):

    df = pd.read_excel(
        upload_file,
        header=None
    )

    for r in range(len(df)):

        row = [
            str(x).strip()
            for x in df.iloc[r].values
        ]

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

            if cell in [
                "D",
                "E",
                "N",
                "OFF",
                "R",
                "M"
            ]:

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

def load_request_table(
    upload_file,
    names,
    num_days
):

    result = {
        n: [""] * num_days
        for n in names
    }

    xl = pd.ExcelFile(upload_file)

    sheet_name = xl.sheet_names[0]

    df = pd.read_excel(
        upload_file,
        sheet_name=sheet_name
    )

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

            value = str(
                row.iloc[col]
            ).strip()

            if value == "nan":
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

            elif "開會" in value:
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

    d_min = st.number_input(
        "白班最低人數",
        value=4
    )

    d_max = st.number_input(
        "白班最高人數",
        value=5
    )

    e_min = st.number_input(
        "小夜最低人數",
        value=3
    )

    e_max = st.number_input(
        "小夜最高人數",
        value=3
    )

    n_min = st.number_input(
        "大夜最低人數",
        value=2
    )

    n_max = st.number_input(
        "大夜最高人數",
        value=2
    )

    st.markdown("---")

    file_a = st.file_uploader(
        "基本班表",
        type=["xlsx"]
    )

    file_b = st.file_uploader(
        "預排休表",
        type=["xlsx"]
    )
    # =====================================
# 排班主引擎
# =====================================

def generate_schedule(
    names,
    permissions,
    requests,
    num_days,
    d_min,
    e_min,
    n_min,
    history_shift,
    history_streak
):

    schedule = {
        n: [""] * num_days
        for n in names
    }

    night_count = {
        n: 0
        for n in names
    }

    work_count = {
        n: 0
        for n in names
    }

    # -----------------------------
    # STEP1
    # 複製預排班
    # -----------------------------

    for nurse in names:

        for d in range(num_days):

            if requests[nurse][d] != "":

                schedule[nurse][d] = requests[nurse][d]

                if requests[nurse][d] in [
                    "D",
                    "E",
                    "N"
                ]:
                    work_count[nurse] += 1

    # -----------------------------
    # STEP2
    # 大夜班
    # -----------------------------

    for day in range(num_days):

        current_n = sum(
            1
            for n in names
            if schedule[n][day] == "N"
        )

        need_n = n_min - current_n

        if need_n <= 0:
            continue

        candidates = []

        for nurse in names:

            if day == 0:

                if history_shift.get(nurse) == "N":

                    continue
        
            if nurse == "郭珍君":
                continue

            if schedule[nurse][day] != "":
                continue

            if not can_work_shift(
                permissions[nurse],
                "N"
            ):
                continue

            candidates.append(nurse)

        candidates.sort(
            key=lambda x: night_count[x]
        )

        for nurse in candidates[:need_n]:

            schedule[nurse][day] = "N"

            night_count[nurse] += 1
            work_count[nurse] += 1

            # N後固定休兩天

            if day + 1 < num_days:

                if schedule[nurse][day + 1] == "":
                    schedule[nurse][day + 1] = "off"

            if day + 2 < num_days:

                if schedule[nurse][day + 2] == "":
                    schedule[nurse][day + 2] = "off"

    # -----------------------------
    # STEP3
    # 小夜
    # -----------------------------

    for day in range(num_days):

        current_e = sum(
            1
            for n in names
            if schedule[n][day] == "E"
        )

        need_e = e_min - current_e

        if need_e <= 0:
            continue

        candidates = []

        for nurse in names:

            if schedule[nurse][day] != "":
                continue

            if not can_work_shift(
                permissions[nurse],
                "E"
            ):
                continue

            candidates.append(nurse)

        candidates.sort(
            key=lambda x: night_count[x]
        )

        for nurse in candidates[:need_e]:

            schedule[nurse][day] = "E"

            night_count[nurse] += 1
            work_count[nurse] += 1

    # -----------------------------
    # STEP4
    # 白班
    # -----------------------------

    for day in range(num_days):

        current_d = sum(
            1
            for n in names
            if schedule[n][day] == "D"
        )

        need_d = d_min - current_d

        if need_d <= 0:
            continue

        candidates = []

        for nurse in names:

            if schedule[nurse][day] != "":
                continue

            if not can_work_shift(
                permissions[nurse],
                "D"
            ):
                continue

            candidates.append(nurse)

        random.shuffle(candidates)

        for nurse in candidates[:need_d]:

            schedule[nurse][day] = "D"

            work_count[nurse] += 1

    # -----------------------------
    # STEP5
    # 剩餘補off
    # -----------------------------

    for nurse in names:

        for d in range(num_days):

            if schedule[nurse][d] == "":

                schedule[nurse][d] = "off"

    # -----------------------------
    # STEP6
    # 郭珍君
    # 固定10天
    # 只能白班
    # -----------------------------

    if "郭珍君" in names:

        nurse = "郭珍君"

        work_days = []

        for d in range(num_days):

            if schedule[nurse][d] == "D":

                work_days.append(d)

        if len(work_days) > 10:

            extra = len(work_days) - 10

            for idx in work_days[-extra:]:

                schedule[nurse][idx] = "off"

        for d in range(num_days):

            if schedule[nurse][d] == "E":
                schedule[nurse][d] = "off"

            if schedule[nurse][d] == "N":
                schedule[nurse][d] = "off"

    # -----------------------------
    # STEP7
    # 四週至少8天休
    # -----------------------------

    for nurse in names:

        holiday_count = sum(
            1
            for x in schedule[nurse]
            if x in [
                "off",
                "R"
            ]
        )

        if holiday_count >= 8:
            continue

        need = 8 - holiday_count

        for d in range(num_days):

            if need <= 0:
                break

            if schedule[nurse][d] == "D":

                schedule[nurse][d] = "off"

                need -= 1

    # -----------------------------
    # STEP8
    # 每週至少一天休
    # -----------------------------

    for nurse in names:

        for start in range(
            0,
            num_days,
            7
        ):

            end = min(
                start + 7,
                num_days
            )

            week = schedule[nurse][start:end]

            has_rest = any(
                x in [
                    "off",
                    "R"
                ]
                for x in week
            )

            if not has_rest:

                schedule[nurse][end - 1] = "off"

    # -----------------------------
    # STEP9
    # 連續上班最多5天
    # -----------------------------

    for nurse in names:

        streak = history_streak.get(
            nurse,
            0
        )

        for d in range(num_days):

            if schedule[nurse][d] in [
                "D",
                "E",
                "N"
            ]:

                streak += 1

            else:

                streak = 0

            if streak > 5:

                schedule[nurse][d] = "off"

                streak = 0

    return schedule
    # =====================================
# 主程式
# =====================================

if file_a and file_b:

    try:

        staffs = load_base_schedule(file_a)

        staffs = load_history_from_base_schedule(
            file_a,
            staffs
        )

        names = list(staffs.keys())

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

            permissions[nurse] = str(
                row["權限"]
            ).upper()

            history_shift[nurse] = str(
                row["上月最後班"]
            )

            history_streak[nurse] = int(
                row["已連上天數"]
            )

        num_days = (
            end_date - start_date
        ).days + 1

        # 後面繼續你的 date_headers...
except Exception as e:
    st.error(f"系統錯誤：{e}")


        if st.button(
            "🚀 啟動排班",
            type="primary",
            use_container_width=True
        ):

            result = generate_schedule(
                names,
                permissions,
                requests,
                num_days,
                d_min,
                e_min,
                n_min,
                history_shift,
                history_streak
            )

            st.success("排班完成")

            tabs = st.tabs([
                "班表",
                "每日人力",
                "休假統計",
                "夜班統計",
                "規則檢查"
            ])

            # =====================
            # TAB1 班表
            # =====================

            with tabs[0]:

                schedule_df = pd.DataFrame(
                    result
                ).T

                schedule_df.columns = date_headers

                schedule_df.insert(
                    0,
                    "權限",
                    [
                        permissions[n]
                        for n in schedule_df.index
                    ]
                )

                st.dataframe(
                    schedule_df,
                    use_container_width=True,
                    height=600
                )

            # =====================
            # TAB2 每日人力
            # =====================

            with tabs[1]:

                manpower_rows = []

                for d in range(num_days):

                    d_count = 0
                    e_count = 0
                    n_count = 0
                    m_count = 0

                    for nurse in names:

                        shift = result[nurse][d]

                        if shift == "D":
                            d_count += 1

                        elif shift == "E":
                            e_count += 1

                        elif shift == "N":
                            n_count += 1

                        elif shift == "M":
                            m_count += 1

                    manpower_rows.append([
                        date_headers[d],
                        d_count,
                        e_count,
                        n_count,
                        m_count
                    ])

                manpower_df = pd.DataFrame(
                    manpower_rows,
                    columns=[
                        "日期",
                        "白班(D)",
                        "小夜(E)",
                        "大夜(N)",
                        "開會(M)"
                    ]
                )

                st.dataframe(
                    manpower_df,
                    use_container_width=True
                )

            # =====================
            # TAB3 休假統計
            # =====================

            with tabs[2]:

                holiday_rows = []

                for nurse in names:

                    r_count = sum(
                        1
                        for x in result[nurse]
                        if x == "R"
                    )

                    off_count = sum(
                        1
                        for x in result[nurse]
                        if x == "off"
                    )

                    holiday_rows.append([
                        nurse,
                        r_count,
                        off_count,
                        r_count + off_count
                    ])

                holiday_df = pd.DataFrame(
                    holiday_rows,
                    columns=[
                        "姓名",
                        "預排休(R)",
                        "OFF",
                        "總休假"
                    ]
                )

                st.dataframe(
                    holiday_df,
                    use_container_width=True
                )

            # =====================
            # TAB4 夜班統計
            # =====================

            with tabs[3]:

                night_rows = []

                for nurse in names:

                    e_count = sum(
                        1
                        for x in result[nurse]
                        if x == "E"
                    )

                    n_count = sum(
                        1
                        for x in result[nurse]
                        if x == "N"
                    )

                    night_rows.append([
                        nurse,
                        e_count,
                        n_count,
                        e_count + n_count
                    ])

                night_df = pd.DataFrame(
                    night_rows,
                    columns=[
                        "姓名",
                        "E班",
                        "N班",
                        "夜班總數"
                    ]
                )

                st.dataframe(
                    night_df,
                    use_container_width=True
                )
                            # =====================
            # TAB5 規則檢查
            # =====================

            with tabs[4]:

                issues = []

                for nurse in names:

                    # -----------------
                    # 休假天數
                    # -----------------

                    total_rest = sum(
                        1
                        for x in result[nurse]
                        if x in ["off", "R"]
                    )

                    if total_rest < 8:

                        issues.append([
                            nurse,
                            f"休假不足8天 ({total_rest}天)"
                        ])

                    # -----------------
                    # 每週至少一天休
                    # -----------------

                    for start in range(
                        0,
                        num_days,
                        7
                    ):

                        end = min(
                            start + 7,
                            num_days
                        )

                        week = result[nurse][start:end]

                        has_rest = any(
                            x in ["off", "R"]
                            for x in week
                        )

                        if not has_rest:

                            issues.append([
                                nurse,
                                f"第{start//7+1}週無休假"
                            ])

                    # -----------------
                    # 連續上班
                    # -----------------

                    streak = 0

                    for shift in result[nurse]:

                        if shift in [
                            "D",
                            "E",
                            "N"
                        ]:

                            streak += 1

                        else:

                            streak = 0

                        if streak > 5:

                            issues.append([
                                nurse,
                                "連續上班超過5天"
                            ])

                            break

                    # -----------------
                    # 郭珍君規則
                    # -----------------

                    if nurse == "郭珍君":

                        d_count = sum(
                            1
                            for x in result[nurse]
                            if x == "D"
                        )

                        if d_count > 10:

                            issues.append([
                                nurse,
                                f"白班超過10天 ({d_count})"
                            ])

                        for shift in result[nurse]:

                            if shift in ["E", "N"]:

                                issues.append([
                                    nurse,
                                    "出現非白班"
                                ])

                                break

                if len(issues) == 0:

                    st.success(
                        "🎉 沒有發現規則違反"
                    )

                else:

                    issue_df = pd.DataFrame(
                        issues,
                        columns=[
                            "姓名",
                            "問題"
                        ]
                    )

                    st.dataframe(
                        issue_df,
                        use_container_width=True
                    )

            # =====================
            # Excel下載
            # =====================

            output = BytesIO()

            with pd.ExcelWriter(
                output,
                engine="openpyxl"
            ) as writer:

                schedule_df.to_excel(
                    writer,
                    sheet_name="班表"
                )

                manpower_df.to_excel(
                    writer,
                    sheet_name="每日人力",
                    index=False
                )

                holiday_df.to_excel(
                    writer,
                    sheet_name="休假統計",
                    index=False
                )

                night_df.to_excel(
                    writer,
                    sheet_name="夜班統計",
                    index=False
                )

                if len(issues) > 0:

                    issue_df.to_excel(
                        writer,
                        sheet_name="規則檢查",
                        index=False
                    )

            st.download_button(
                label="📥 下載排班Excel",
                data=output.getvalue(),
                file_name="2F護理排班結果.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

    except Exception as e:

        st.error(
            f"系統錯誤：{str(e)}"
        )
