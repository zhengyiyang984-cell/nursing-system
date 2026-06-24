import pandas as pd
from config import *


def previous_shift(schedule, history_shift, nurse, day):
    if day == 0:
        return history_shift.get(nurse, SHIFT_OFF)
    return schedule[nurse][day - 1]


def validate_schedule(schedule, names, manpower, history_shift=None, requests=None):
    history_shift = history_shift or {n: SHIFT_OFF for n in names}
    requests = requests or {n: [""] * len(manpower) for n in names}
    issues = []
    days = len(manpower)

    # 每日人力檢查
    for d in range(days):
        for shift in CLINICAL_SHIFTS:
            count = sum(1 for n in names if schedule[n][d] == shift)
            min_req = manpower[d].get(f"{shift}_min", 0)
            max_req = manpower[d].get(f"{shift}_max", 999)
            if count < min_req:
                issues.append(["每日人力不足", d, shift, f"{shift} 僅 {count} 人，低於最低 {min_req} 人"])
            if count > max_req:
                issues.append(["每日人力超過", d, shift, f"{shift} 有 {count} 人，超過最高 {max_req} 人"])

    for n in names:
        # 預排休不可被覆蓋
        for d in range(days):
            if d < len(requests[n]) and requests[n][d] == SHIFT_R and schedule[n][d] != SHIFT_R:
                issues.append([n, d, "R", "預排休 R 被覆蓋"])

        # 班別銜接
        for d in range(days):
            prev = previous_shift(schedule, history_shift, n, d)
            cur = schedule[n][d]
            if (prev, cur) in FORBIDDEN_TRANSITIONS:
                issues.append([n, d, cur, f"不允許 {prev} → {cur}"])

        # 最多連上 MAX_CONTINUOUS_WORK 天
        streak = 0
        for d in range(days):
            if schedule[n][d] in WORK_SHIFTS:
                streak += 1
                if streak > MAX_CONTINUOUS_WORK:
                    issues.append([n, d, schedule[n][d], f"連續上班超過 {MAX_CONTINUOUS_WORK} 天"])
            else:
                streak = 0

        # 大夜固定 N N off off
        d = 0
        while d < days:
            if schedule[n][d] == SHIFT_N:
                if d + 3 >= days:
                    d += 1
                    continue
                block = schedule[n][d:d + 4]
                if block != NIGHT_BLOCK:
                    issues.append([n, d, "N", "大夜必須為 N → N → off → off"])
                d += 4
            else:
                d += 1

        # 1 天碎班
        for d in range(days):
            if schedule[n][d] in CLINICAL_SHIFTS:
                left_rest = d == 0 or schedule[n][d - 1] in REST_SHIFTS
                right_rest = d == days - 1 or schedule[n][d + 1] in REST_SHIFTS
                if left_rest and right_rest:
                    issues.append([n, d, schedule[n][d], "出現 1 天碎班"])

        # 休假天數 / 兼職規則
        if n not in PART_TIME:
            off_days = sum(1 for x in schedule[n] if x in REST_SHIFTS)
            if off_days < MIN_FULLTIME_OFF_DAYS:
                issues.append([n, "全月", "休假", f"全職休假不足 {MIN_FULLTIME_OFF_DAYS} 天，目前 {off_days} 天"])
        else:
            d_count = sum(1 for x in schedule[n] if x == PARTTIME_ALLOWED_SHIFT)
            non_d_work = sum(1 for x in schedule[n] if x in WORK_SHIFTS and x != PARTTIME_ALLOWED_SHIFT)
            if d_count != PARTTIME_DAYS:
                issues.append([n, "全月", "兼職", f"兼職 D 班需剛好 {PARTTIME_DAYS} 天，目前 {d_count} 天"])
            if non_d_work:
                issues.append([n, "全月", "兼職", "兼職不可排 D 以外班別"])

    return issues


def issues_to_dataframe(issues, date_headers=None):
    rows = []
    for item in issues:
        target, day, shift, message = item
        if isinstance(day, int) and date_headers and day < len(date_headers):
            day_label = date_headers[day]
        else:
            day_label = str(day)
        rows.append({"對象/類別": target, "日期": day_label, "班別": shift, "提醒": message})
    return pd.DataFrame(rows)
