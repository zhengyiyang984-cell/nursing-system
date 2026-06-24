import pandas as pd
from config import *


def build_schedule_dataframe(schedule, names, date_headers, permissions=None):

    df = pd.DataFrame(schedule).T

    df = df.loc[names]

    df.columns = date_headers

    # 新增姓名欄
    df.insert(0, "姓名", df.index)

    # 新增權限欄
    if permissions:
        df.insert(
            1,
            "班別權限",
            [permissions.get(n, "DEN") for n in df.index]
        )

    df = df.reset_index(drop=True)

    return df


def build_manpower_dataframe(schedule, names, manpower, date_headers):
    rows = []
    for d, date in enumerate(date_headers):
        row = {"日期": date}
        for shift in CLINICAL_SHIFTS:
            count = sum(1 for n in names if schedule[n][d] == shift)
            row[f"{shift}實際"] = count
            row[f"{shift}需求"] = f"{manpower[d].get(f'{shift}_min', 0)}~{manpower[d].get(f'{shift}_max', 999)}"
        row["M會議"] = sum(1 for n in names if schedule[n][d] == SHIFT_M)
        rows.append(row)
    return pd.DataFrame(rows)


def build_person_statistics(schedule, names):
    rows = []
    for n in names:
        row = {"姓名": n}
        for shift in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R, SHIFT_OFF]:
            row[shift] = sum(1 for x in schedule[n] if x == shift)
        row["總上班"] = sum(1 for x in schedule[n] if x in WORK_SHIFTS)
        row["總休假"] = sum(1 for x in schedule[n] if x in REST_SHIFTS)
        row["夜班總計"] = row[SHIFT_E] + row[SHIFT_N]
        row["最長連上"] = longest_work_streak(schedule[n])
        rows.append(row)
    return pd.DataFrame(rows)


def longest_work_streak(shifts):
    best = 0
    cur = 0
    for s in shifts:
        if s in WORK_SHIFTS:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best
