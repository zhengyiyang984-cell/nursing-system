import streamlit as st
import pandas as pd
import numpy as np
import datetime
import random
import re
from io import BytesIO

st.set_page_config(
    page_title="2F護理排班系統",
    layout="wide"
)

WEEKDAYS_CHINESE = ["一","二","三","四","五","六","日"]

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
def parse_permission(text):

    text = str(text).upper()

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

    return "DEN"
    def load_base_schedule(upload_file):

        df = pd.read_excel(
        upload_file,
        header=None
        )

        staffs = {}

        for r in range(len(df)):

            row = [str(x) for x in df.iloc[r].values]

            for name in CORE_STAFF_NAMES:

                if name in "".join(row):

                    perm = "DEN"

                    for c in row:

                        p = parse_permission(c)

                        if p:
                            perm = p

                    staffs[name] = {
                        "perm": perm,
                        "part_time": name == "郭珍君"
                    }

    return staffs
    def load_request_table(
        file,
        names,
        num_days
):

        result = {
            n: [""] * num_days
            for n in names
        }

        xl = pd.ExcelFile(file)

        sheet = xl.sheet_names[0]

    df = pd.read_excel(
        file,
        sheet_name=sheet
    )

    for idx,row in df.iterrows():

        person = str(row.iloc[1]).strip()

        matched = None

        for n in names:

            if n in person:
                matched = n
                break

        if not matched:
            continue

        for day in range(num_days):

            col = day + 2

            if col >= len(df.columns):
                continue

            value = str(
                row.iloc[col]
            ).strip()

            if value == "nan":
                continue

            value = value.upper()

            if value == "R":
                result[matched][day] = "R"

            elif value == "D":
                result[matched][day] = "D"

            elif value == "E":
                result[matched][day] = "E"

            elif value == "N":
                result[matched][day] = "N"

            elif "開會" in value:
                result[matched][day] = "M"

    return result
    def can_work_shift(
        permission,
        shift
):

        if shift in [
            "R",
            "off",
            "M"
        ]:
            return True

    return shift in permission
    with st.sidebar:

        st.header("排班設定")

    start_date = st.date_input(
        "開始日期",
        datetime.date(2026,1,1)
    )

    end_date = st.date_input(
        "結束日期",
        datetime.date(2026,1,31)
    )

    d_min = st.number_input(
        "白班最低",
        value=4
    )

    d_max = st.number_input(
        "白班最高",
        value=5
    )

    e_min = st.number_input(
        "小夜最低",
        value=3
    )

    e_max = st.number_input(
        "小夜最高",
        value=3
    )

    n_min = st.number_input(
        "大夜最低",
        value=2
    )

    n_max = st.number_input(
        "大夜最高",
        value=2
    )

    file_a = st.file_uploader(
        "基本班表",
        type=["xlsx"]
    )

    file_b = st.file_uploader(
        "預排休表",
        type=["xlsx"]
    )
    def generate_schedule(
    names,
    permissions,
    requests,
    num_days,
    d_min,
    e_min,
    n_min
):

        schedule = {
            n:[""] * num_days
            for n in names
        }

    night_count = {
        n:0
        for n in names
    }

    work_count = {
        n:0
        for n in names
    }

    consecutive = {
        n:0
        for n in names
    }

    # ----------------------
    # STEP1
    # 複製預排班
    # ----------------------

    for n in names:

        for d in range(num_days):

            if requests[n][d] != "":

                schedule[n][d] = requests[n][d]

                if requests[n][d] in ["D","E","N"]:

                    work_count[n] += 1

    # ----------------------
    # STEP2
    # N班優先分配
    # ----------------------

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

        for n in names:

            if n == "郭珍君":
                continue

            if schedule[n][day] != "":
                continue

            if not can_work_shift(
                permissions[n],
                "N"
            ):
                continue

            candidates.append(n)

        candidates.sort(
            key=lambda x: night_count[x]
        )

        for nurse in candidates[:need_n]:

            schedule[nurse][day] = "N"

            night_count[nurse] += 1
            work_count[nurse] += 1

            if day + 1 < num_days:

                if schedule[nurse][day+1] == "":
                    schedule[nurse][day+1] = "off"

            if day + 2 < num_days:

                if schedule[nurse][day+2] == "":
                    schedule[nurse][day+2] = "off"
                        # ----------------------
    # STEP3
    # 小夜
    # ----------------------

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

        for n in names:

            if schedule[n][day] != "":
                continue

            if not can_work_shift(
                permissions[n],
                "E"
            ):
                continue

            candidates.append(n)

        candidates.sort(
            key=lambda x: night_count[x]
        )

        for nurse in candidates[:need_e]:

            schedule[nurse][day] = "E"

            night_count[nurse] += 1
            work_count[nurse] += 1
                # ----------------------
    # STEP4
    # 白班
    # ----------------------

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

        for n in names:

            if schedule[n][day] != "":
                continue

            if not can_work_shift(
                permissions[n],
                "D"
            ):
                continue

            candidates.append(n)

        random.shuffle(candidates)

        for nurse in candidates[:need_d]:

            schedule[nurse][day] = "D"

            work_count[nurse] += 1
                # ----------------------
    # STEP5
    # 補休
    # ----------------------

    for n in names:

        for d in range(num_days):

            if schedule[n][d] == "":

                schedule[n][d] = "off"
                    # ----------------------
    # STEP6
    # 郭珍君
    # ----------------------

    if "郭珍君" in names:

        work_days = []

        for d in range(num_days):

            if schedule["郭珍君"][d] == "D":

                work_days.append(d)

        if len(work_days) > 10:

            remove_num = len(work_days) - 10

            for idx in work_days[-remove_num:]:

                schedule["郭珍君"][idx] = "off"
                    # ----------------------
    # STEP7
    # 八天休
    # ----------------------

    for n in names:

        holidays = sum(
            1
            for x in schedule[n]
            if x in ["off","R"]
        )

        if holidays >= 8:
            continue

        need = 8 - holidays

        for d in range(num_days):

            if need <= 0:
                break

            if schedule[n][d] == "D":

                schedule[n][d] = "off"

                need -= 1
                    # ----------------------
    # STEP8
    # 每週休一天
    # ----------------------

    for n in names:

        for start in range(
            0,
            num_days,
            7
        ):

            end = min(
                start+7,
                num_days
            )

            week = schedule[n][start:end]

            has_rest = any(
                x in ["off","R"]
                for x in week
            )

            if not has_rest:

                schedule[n][end-1] = "off"
                st.title("🏥 2F護理排班系統")

if file_a and file_b:

    try:

        staffs = load_base_schedule(file_a)

        names = list(staffs.keys())

        permissions = {
            n: staffs[n]["perm"]
            for n in names
        }

        num_days = (
            end_date - start_date
        ).days + 1

        date_headers = []

        for i in range(num_days):

            d = start_date + datetime.timedelta(days=i)

            date_headers.append(
                f"{d.month}/{d.day}"
            )

        requests = load_request_table(
            file_b,
            names,
            num_days
        )

        if st.button(
            "🚀 啟動排班",
            type="primary"
        ):

            result = generate_schedule(
                names,
                permissions,
                requests,
                num_days,
                d_min,
                e_min,
                n_min
            )

            st.success("排班完成")

            tabs = st.tabs([
                "班表",
                "每日人力",
                "休假統計",
                "夜班統計",
                "規則檢查"
            ])
            with tabs[0]:

                df = pd.DataFrame(
                    result
                ).T

                df.columns = date_headers

                df.insert(
                    0,
                    "權限",
                    [
                        permissions[n]
                        for n in df.index
                    ]
                )

                st.dataframe(
                    df,
                    use_container_width=True
                )
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
                        "D",
                        "E",
                        "N",
                        "M"
                    ]
                )

                st.dataframe(
                    manpower_df,
                    use_container_width=True
                )
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
                        "D",
                        "E",
                        "N",
                        "M"
                    ]
                )

                st.dataframe(
                    manpower_df,
                    use_container_width=True
                )
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
                        "R",
                        "off",
                        "總休假"
                    ]
                )

                st.dataframe(
                    holiday_df,
                    use_container_width=True
                )
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
                        "E",
                        "N",
                        "夜班總數"
                    ]
                )

                st.dataframe(
                    night_df,
                    use_container_width=True
                )
                with tabs[4]:

                    issues = []

                    for nurse in names:

                        total_rest = sum(
                            1
                            for x in result[nurse]
                            if x in ["off","R"]
                        )

                    if total_rest < 8:

                        issues.append([
                            nurse,
                            "休假不足8天"
                        ])

                    consecutive = 0

                    for shift in result[nurse]:

                        if shift in [
                            "D",
                            "E",
                            "N"
                        ]:

                            consecutive += 1

                        else:

                            consecutive = 0

                        if consecutive > 5:

                            issues.append([
                                nurse,
                                "連續上班超過5天"
                            ])

                            break

                if len(issues) == 0:

                    st.success(
                        "沒有發現規則違反"
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
                    except Exception as e:

        st.error(
            f"系統錯誤：{e}"
        )
