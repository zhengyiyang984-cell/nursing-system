"""V27 排班前可行性檢查。

目標：在進入 Scheduler 前先攔截明顯無解的硬性條件，
避免浪費大量 attempts，也避免輸出一份明知不合法的班表。
"""
from config import *


def _req(requests, nurse, day, days):
    row = requests.get(nurse, [""] * days)
    return row[day] if day < len(row) else ""


def check_feasibility(names, permissions, requests, manpower, history_shift=None, history_streak=None):
    issues = []
    days = len(manpower)
    history_shift = history_shift or {}
    history_streak = history_streak or {}

    def add(message, day=None, shift="", nurse="", severity="error"):
        issues.append({
            "category": "可行性檢查",
            "message": message,
            "nurse": nurse,
            "day": day,
            "shift": shift,
            "severity": severity,
            "suggestion": "請先調整預排、請假、人員權限或最低人力後再排班。",
        })

    # -------------------------------------------------
    # 1. 固定預排與權限是否直接衝突
    # -------------------------------------------------
    for nurse in names:
        perm = str(permissions.get(nurse, "DEN")).upper()
        for day in range(days):
            req = _req(requests, nurse, day, days)
            if req in CLINICAL_SHIFTS:
                if nurse in PART_TIME and req != PARTTIME_ALLOWED_SHIFT:
                    add(
                        f"兼職人員固定預排 {req}，但兼職只允許 {PARTTIME_ALLOWED_SHIFT}。",
                        day, req, nurse,
                    )
                elif nurse not in PART_TIME and req not in perm:
                    add(
                        f"固定預排為 {req}，但目前權限 {perm} 不包含此班別。",
                        day, req, nurse,
                    )

    # -------------------------------------------------
    # 2. 每日各班最大可用人數 vs 最低需求
    # -------------------------------------------------
    for day in range(days):
        for shift in CLINICAL_SHIFTS:
            minimum = int(manpower[day].get(f"{shift}_min", 0) or 0)
            fixed = 0
            candidates = 0

            for nurse in names:
                req = _req(requests, nurse, day, days)
                perm = str(permissions.get(nurse, "DEN")).upper()

                if req == shift:
                    fixed += 1

                if nurse in PART_TIME and shift != PARTTIME_ALLOWED_SHIFT:
                    continue
                if nurse not in PART_TIME and shift not in perm:
                    continue
                if req in [SHIFT_R, SHIFT_M]:
                    continue
                if req in CLINICAL_SHIFTS and req != shift:
                    continue
                candidates += 1

            if candidates < minimum:
                add(
                    f"{shift} 最多只能安排 {candidates} 人，但最低需求是 {minimum} 人（固定已有 {fixed} 人）。",
                    day, shift,
                )

    # -------------------------------------------------
    # 3. 每日三班總需求 vs 當日可上臨床班人數
    # -------------------------------------------------
    for day in range(days):
        total_min = sum(int(manpower[day].get(f"{s}_min", 0) or 0) for s in CLINICAL_SHIFTS)
        available = 0
        for nurse in names:
            req = _req(requests, nurse, day, days)
            if req not in [SHIFT_R, SHIFT_M]:
                available += 1
        if total_min > available:
            add(
                f"D/E/N 最低人力合計 {total_min} 人，但當日最多只有 {available} 人可上臨床班。",
                day,
            )

    # -------------------------------------------------
    # 4. 固定 N 是否已被相鄰固定需求堵死
    # -------------------------------------------------
    for nurse in names:
        if nurse in PART_TIME:
            continue
        for day in range(days):
            if _req(requests, nurse, day, days) != SHIFT_N:
                continue

            paired_left = day > 0 and _req(requests, nurse, day - 1, days) == SHIFT_N
            paired_right = day + 1 < days and _req(requests, nurse, day + 1, days) == SHIFT_N
            if paired_left or paired_right:
                continue

            can_pair_right = False
            if day + 1 < days:
                req2 = _req(requests, nurse, day + 1, days)
                can_pair_right = req2 in ["", SHIFT_N]
                if can_pair_right:
                    for rd in [day + 2, day + 3]:
                        if rd < days and _req(requests, nurse, rd, days) not in ["", SHIFT_R]:
                            can_pair_right = False
                            break

            can_pair_left = False
            if day - 1 >= 0:
                req0 = _req(requests, nurse, day - 1, days)
                can_pair_left = req0 in ["", SHIFT_N]
                if can_pair_left:
                    for rd in [day + 1, day + 2]:
                        if rd < days and _req(requests, nurse, rd, days) not in ["", SHIFT_R]:
                            can_pair_left = False
                            break

            if not can_pair_left and not can_pair_right:
                add(
                    "固定 N 無法延伸成 N→N→off→off，前後已有固定需求衝突。",
                    day, SHIFT_N, nurse,
                )

    # -------------------------------------------------
    # 5. 月初承接上月連班：若已連上達上限，第一天不可再固定上班
    # -------------------------------------------------
    for nurse in names:
        prior = int(history_streak.get(nurse, 0) or 0)
        if prior < MAX_CONTINUOUS_WORK or days == 0:
            continue
        req0 = _req(requests, nurse, 0, days)
        if req0 in WORK_SHIFTS:
            add(
                f"上月已連續上班 {prior} 天，本月第 1 天又固定排 {req0}，會超過最多 {MAX_CONTINUOUS_WORK} 天。",
                0, req0, nurse,
            )

    return issues
