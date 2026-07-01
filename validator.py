"""
validator.py - 2F 護理排班系統 V6 規則檢查

保留原本 API：
    validate_schedule(schedule, names, manpower, history_shift, requests)
    issues_to_dataframe(issues, date_headers)
"""

import pandas as pd
from config import *

# --------- 安全補值：避免 config.py 少常數時整個程式掛掉 ---------
SHIFT_D = globals().get("SHIFT_D", "D")
SHIFT_E = globals().get("SHIFT_E", "E")
SHIFT_N = globals().get("SHIFT_N", "N")
SHIFT_M = globals().get("SHIFT_M", "M")
SHIFT_R = globals().get("SHIFT_R", "R")
SHIFT_OFF = globals().get("SHIFT_OFF", "off")

CLINICAL_SHIFTS = globals().get("CLINICAL_SHIFTS", [SHIFT_D, SHIFT_E, SHIFT_N])
WORK_SHIFTS = globals().get("WORK_SHIFTS", [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M])
REST_SHIFTS = globals().get("REST_SHIFTS", [SHIFT_OFF, SHIFT_R])
ALL_SHIFTS = globals().get("ALL_SHIFTS", [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R, SHIFT_OFF])

PART_TIME = globals().get("PART_TIME", ["郭珍君"])
PARTTIME_DAYS = globals().get("PARTTIME_DAYS", 10)
PARTTIME_ALLOWED_SHIFT = globals().get("PARTTIME_ALLOWED_SHIFT", SHIFT_D)

MAX_CONTINUOUS_WORK = globals().get("MAX_CONTINUOUS_WORK", 5)
MIN_FULLTIME_OFF_DAYS = globals().get("MIN_FULLTIME_OFF_DAYS", 8)
FORBIDDEN_TRANSITIONS = globals().get(
    "FORBIDDEN_TRANSITIONS",
    [(SHIFT_E, SHIFT_D), (SHIFT_N, SHIFT_D), (SHIFT_N, SHIFT_E)],
)


def _issue(category, nurse="", day=None, shift="", message="", severity="warning", suggestion=""):
    return {
        "category": category,
        "nurse": nurse,
        "day": day,
        "shift": shift,
        "message": message,
        "severity": severity,
        "suggestion": suggestion,
    }


def _req(requests, nurse, day, days):
    return requests.get(nurse, [""] * days)[day]


def _shift_count(schedule, names, day, shift):
    return sum(1 for n in names if schedule.get(n, [])[day] == shift)


def _longest_work_streak(row, history_streak=0):
    longest = 0
    cur = history_streak
    for s in row:
        if s in WORK_SHIFTS:
            cur += 1
            longest = max(longest, cur)
        else:
            cur = 0
    return longest


def _single_day_fragments(row):
    """回傳 1 天碎班位置；N 不在這裡檢查，N 由 night pattern 檢查。"""
    result = []
    days = len(row)
    for d, s in enumerate(row):
        if s not in [SHIFT_D, SHIFT_E]:
            continue
        left_rest = d == 0 or row[d - 1] in REST_SHIFTS
        right_rest = d == days - 1 or row[d + 1] in REST_SHIFTS
        if left_rest and right_rest:
            result.append(d)
    return result


def _check_night_pattern(schedule, names, requests, issues):
    days = len(next(iter(schedule.values()))) if schedule else 0
    for nurse in names:
        if nurse in PART_TIME:
            continue
        row = schedule[nurse]
        d = 0
        while d < days:
            if row[d] != SHIFT_N:
                d += 1
                continue

            # N 必須是 N,N；月底最後一天若只有單 N 仍提醒。
            if d + 1 >= days or row[d + 1] != SHIFT_N:
                issues.append(_issue(
                    "大夜規則",
                    nurse,
                    d,
                    SHIFT_N,
                    "大夜必須成組：N→N→off→off，目前出現單顆 N。",
                    "error",
                    "請改成連續兩天 N，或將此 N 改為其他合法班別。",
                ))
                d += 1
                continue

            # N,N 後兩天應休；月底超出月份不檢查。
            for rest_day in [d + 2, d + 3]:
                if rest_day < days and row[rest_day] not in REST_SHIFTS:
                    issues.append(_issue(
                        "大夜規則",
                        nurse,
                        rest_day,
                        row[rest_day],
                        "大夜後必須休兩天：N→N→off→off。",
                        "error",
                        "請將大夜後兩天調整為 off/R，或整組夜班重新安排。",
                    ))
            d += 2


def _check_manpower(schedule, names, manpower, issues):
    days = len(manpower)
    for d in range(days):
        for shift in CLINICAL_SHIFTS:
            actual = _shift_count(schedule, names, d, shift)
            min_req = int(manpower[d].get(f"{shift}_min", 0))
            max_req = int(manpower[d].get(f"{shift}_max", 999))

            if actual < min_req:
                issues.append(_issue(
                    "每日人力未滿",
                    "",
                    d,
                    shift,
                    f"{shift} 目前 {actual} 人，低於最低需求 {min_req} 人。",
                    "error",
                    "請補足人力，或調整該週人力最低需求。",
                ))
            if actual > max_req:
                issues.append(_issue(
                    "每日人力超過",
                    "",
                    d,
                    shift,
                    f"{shift} 目前 {actual} 人，高於最高限制 {max_req} 人。",
                    "warning",
                    "可考慮將多出人員改為 off 或其他缺人班別。",
                ))


def _check_requests(schedule, names, requests, issues):
    days = len(next(iter(schedule.values()))) if schedule else 0
    for nurse in names:
        for d in range(days):
            req = _req(requests, nurse, d, days)
            cur = schedule[nurse][d]
            if req == "":
                continue
            if req == SHIFT_R and cur != SHIFT_R:
                issues.append(_issue(
                    "預排休違規",
                    nurse,
                    d,
                    cur,
                    "R 是固定預排休，不能改成上班。",
                    "error",
                    "請恢復為 R。",
                ))
            elif req in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M] and cur != req:
                issues.append(_issue(
                    "預排班違規",
                    nurse,
                    d,
                    cur,
                    f"此日預排為 {req}，目前卻是 {cur}。",
                    "error",
                    f"請恢復為 {req}，或回到預排休表調整需求。",
                ))


def _check_transitions(schedule, names, history_shift, issues):
    days = len(next(iter(schedule.values()))) if schedule else 0
    for nurse in names:
        row = schedule[nurse]
        prev = history_shift.get(nurse, SHIFT_OFF)
        for d in range(days):
            cur = row[d]
            if (prev, cur) in FORBIDDEN_TRANSITIONS:
                issues.append(_issue(
                    "班別銜接違規",
                    nurse,
                    d,
                    cur,
                    f"{prev} 後不能接 {cur}。",
                    "error",
                    "請調整前後班別，例如改 off 或同班別延續。",
                ))
            if prev == SHIFT_N and cur not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
                issues.append(_issue(
                    "大夜銜接違規",
                    nurse,
                    d,
                    cur,
                    "N 後只能接 N 或休假。",
                    "error",
                    "請將 N 後調整為 N/off/R。",
                ))
            prev = cur


def _check_holidays_and_streaks(schedule, names, history_streak, issues):
    days = len(next(iter(schedule.values()))) if schedule else 0
    for nurse in names:
        row = schedule[nurse]

        if nurse in PART_TIME:
            d_count = sum(1 for x in row if x == PARTTIME_ALLOWED_SHIFT)
            invalid = sum(1 for x in row if x not in [PARTTIME_ALLOWED_SHIFT, SHIFT_OFF, SHIFT_R, ""])
            if d_count != PARTTIME_DAYS:
                issues.append(_issue(
                    "兼職天數",
                    nurse,
                    None,
                    PARTTIME_ALLOWED_SHIFT,
                    f"兼職 D 班需剛好 {PARTTIME_DAYS} 天，目前 {d_count} 天。",
                    "error",
                    "請限制郭珍君只排 3+3+2+2 共 10 天 D。",
                ))
            if invalid > 0:
                issues.append(_issue(
                    "兼職班別",
                    nurse,
                    None,
                    "",
                    "兼職只能排 D/off/R，不能排 E/N/M。",
                    "error",
                    "請將兼職非 D 班別改為 off 或移給全職。",
                ))
            continue

        off_total = sum(1 for x in row if x in REST_SHIFTS)
        if off_total < MIN_FULLTIME_OFF_DAYS:
            issues.append(_issue(
                "全職休假不足",
                nurse,
                None,
                "",
                f"全職每月至少 {MIN_FULLTIME_OFF_DAYS} 天休，目前 {off_total} 天。",
                "error",
                "請用休假較多者頂替此人的部分班別。",
            ))

        longest = _longest_work_streak(row, history_streak.get(nurse, 0))
        if longest > MAX_CONTINUOUS_WORK:
            issues.append(_issue(
                "連續上班過長",
                nurse,
                None,
                "",
                f"最多連續上班 {MAX_CONTINUOUS_WORK} 天，目前最長 {longest} 天。",
                "error",
                "請在連班中間插入 off/R。",
            ))

        # 每 7 天至少一天休；以本月第1天開始切週。
        for start in range(0, days, 7):
            block = row[start:min(start + 7, days)]
            if len(block) >= 5 and not any(x in REST_SHIFTS for x in block):
                issues.append(_issue(
                    "每週休假不足",
                    nurse,
                    start,
                    "",
                    f"第 {start // 7 + 1} 週未安排休假。",
                    "warning",
                    "請該週至少安排 1 天 off/R。",
                ))

        for d in _single_day_fragments(row):
            issues.append(_issue(
                "一日碎班",
                nurse,
                d,
                row[d],
                f"{row[d]} 出現 1 天碎班。",
                "warning",
                "可改 off，或與前後同班別連成 2 天以上。",
            ))


def validate_schedule(schedule, names, manpower, history_shift=None, requests=None, history_streak=None):
    """
    回傳 issues list。每筆為 dict，可供 optimizer 計分與 app 顯示。
    相容舊呼叫：validate_schedule(schedule, names, manpower, history_shift, requests)
    """
    history_shift = history_shift or {}
    history_streak = history_streak or {}
    requests = requests or {n: [""] * len(manpower) for n in names}

    issues = []
    if not schedule:
        return [_issue("系統錯誤", "", None, "", "schedule 是空的。", "error")]

    _check_requests(schedule, names, requests, issues)
    _check_manpower(schedule, names, manpower, issues)
    _check_transitions(schedule, names, history_shift, issues)
    _check_night_pattern(schedule, names, requests, issues)
    _check_holidays_and_streaks(schedule, names, history_streak, issues)
    return issues


def issues_to_dataframe(issues, date_headers=None):
    rows = []
    date_headers = date_headers or []
    for item in issues:
        day = item.get("day")
        if isinstance(day, int) and 0 <= day < len(date_headers):
            date_text = date_headers[day]
        elif isinstance(day, int):
            date_text = f"第 {day + 1} 天"
        else:
            date_text = "全月"

        rows.append({
            "對象/類別": item.get("nurse") or item.get("category", ""),
            "日期": date_text,
            "班別": item.get("shift", ""),
            "提醒": item.get("message", ""),
            "建議": item.get("suggestion", ""),
            "嚴重度": item.get("severity", "warning"),
        })
    return pd.DataFrame(rows)
