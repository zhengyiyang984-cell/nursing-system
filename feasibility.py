"""排班前可行性預檢。

這不是完整求解器，但能先攔截明顯不可能的需求，避免浪費大量嘗試次數。
"""
from config import *


def check_feasibility(names, permissions, requests, manpower):
    issues = []
    days = len(manpower)

    def add(message, day=None, shift="", severity="error"):
        issues.append({
            "category": "可行性檢查",
            "message": message,
            "nurse": "",
            "day": day,
            "shift": shift,
            "severity": severity,
        })

    for day in range(days):
        for shift in CLINICAL_SHIFTS:
            minimum = int(manpower[day].get(f"{shift}_min", 0) or 0)
            fixed = sum(1 for n in names if requests.get(n, [""] * days)[day] == shift)
            candidates = 0

            for nurse in names:
                req = requests.get(nurse, [""] * days)[day]
                if nurse in PART_TIME and shift != PARTTIME_ALLOWED_SHIFT:
                    continue
                if shift not in str(permissions.get(nurse, "")):
                    continue
                if req in [SHIFT_R, SHIFT_M]:
                    continue
                if req in CLINICAL_SHIFTS and req != shift:
                    continue
                candidates += 1

            if candidates < minimum:
                add(
                    f"最多只能安排 {candidates} 人，但最低需求是 {minimum} 人（固定已有 {fixed} 人）。",
                    day,
                    shift,
                )

    # 每日三班總需求不能超過當日可上臨床班總人數。
    for day in range(days):
        total_min = sum(int(manpower[day].get(f"{s}_min", 0) or 0) for s in CLINICAL_SHIFTS)
        available = sum(
            1 for n in names
            if requests.get(n, [""] * days)[day] not in [SHIFT_R, SHIFT_M]
        )
        if total_min > available:
            add(f"D/E/N 最低人力合計 {total_min} 人，但當日最多只有 {available} 人可上臨床班。", day)

    return issues
