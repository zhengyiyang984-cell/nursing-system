# config.py

# 班別狀態定義
# is_working: 是否計算在「出勤天數」中
# counts_in_manpower: 是否計入「人力數」 (排班人數)
SHIFT_STATUS = {
    "D": {"is_working": True,  "counts_in_manpower": True},
    "E": {"is_working": True,  "counts_in_manpower": True},
    "N": {"is_working": True,  "counts_in_manpower": True},
    "M": {"is_working": True,  "counts_in_manpower": False}, # 開會: 有出勤但人力為 0
    "R": {"is_working": False, "counts_in_manpower": False},
    "V": {"is_working": False, "counts_in_manpower": False},
    "OFF": {"is_working": False, "counts_in_manpower": False}
}

# 規則設定
RULES = {
    "MAX_PART_TIME_DAYS": 10,   # 兼職人員每月上限天數
    "MIN_D_SHIFT": 4,           # 每日早班最低需求
    "MIN_E_SHIFT": 3,           # 每日小夜最低需求
    "MIN_N_SHIFT": 2            # 每日大夜最低需求
}
