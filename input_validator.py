"""排班輸入資料檢查。"""
from config import *

VALID_PERMISSIONS = {"DEN", "DE", "DN", "EN", "D", "E", "N"}


def validate_inputs(names, permissions, requests, manpower, history_shift, history_streak):
    issues = []
    days = len(manpower)

    def add(category, message, nurse="", day=None, severity="error"):
        issues.append({
            "category": category,
            "message": message,
            "nurse": nurse,
            "day": day,
            "severity": severity,
        })

    if len(set(names)) != len(names):
        add("名單錯誤", "人員名單出現重複姓名。")

    for nurse in names:
        perm = str(permissions.get(nurse, "")).upper().strip()
        if perm not in VALID_PERMISSIONS:
            add("權限錯誤", f"權限 {perm or '空白'} 不合法。", nurse)

        row = requests.get(nurse)
        if row is None or len(row) != days:
            add("日期對齊錯誤", f"預排資料應有 {days} 天，目前為 {len(row) if row is not None else 0} 天。", nurse)
            continue

        for day, req in enumerate(row):
            if req not in ["", SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R]:
                add("班別錯誤", f"預排班別 {req} 不合法。", nurse, day)
            if req in CLINICAL_SHIFTS and req not in perm:
                add("權限衝突", f"預排 {req} 超出權限 {perm}。", nurse, day)

        if nurse in PART_TIME:
            fixed_d = sum(1 for x in row if x == PARTTIME_ALLOWED_SHIFT)
            invalid = [(i, x) for i, x in enumerate(row) if x in [SHIFT_E, SHIFT_N]]
            if fixed_d > PARTTIME_DAYS:
                add("兼職預排衝突", f"固定 D 已有 {fixed_d} 天，超過上限 {PARTTIME_DAYS} 天。", nurse)
            for day, req in invalid:
                add("兼職預排衝突", f"兼職只能排 D/M/R，不能預排 {req}。", nurse, day)

        hs = history_shift.get(nurse, SHIFT_OFF)
        if hs not in ALL_SHIFTS:
            add("上月資料錯誤", f"上月最後班 {hs} 不合法。", nurse)
        try:
            streak = int(history_streak.get(nurse, 0))
            if streak < 0:
                raise ValueError
        except (TypeError, ValueError):
            add("上月資料錯誤", "已連上天數必須為非負整數。", nurse)

    for day, req in enumerate(manpower):
        for shift in CLINICAL_SHIFTS:
            key = f"{shift}_min"
            try:
                value = int(req.get(key, 0))
                if value < 0:
                    raise ValueError
            except (TypeError, ValueError):
                add("人力設定錯誤", f"{key} 必須為非負整數。", day=day)

    return issues
