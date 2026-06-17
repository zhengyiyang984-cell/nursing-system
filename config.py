"""
2F 護理排班系統 V3.0 - 設定檔
所有規則集中管理。
"""

CORE_STAFF = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳",
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸",
    "汪家容", "林欣儀", "林怡微", "溫鈺羚",
]

PART_TIME = ["郭珍君"]
PARTTIME_DAYS = 10
PARTTIME_ALLOWED_SHIFT = "D"

SHIFT_D = "D"
SHIFT_E = "E"
SHIFT_N = "N"
SHIFT_M = "M"
SHIFT_R = "R"
SHIFT_OFF = "off"

CLINICAL_SHIFTS = [SHIFT_D, SHIFT_E, SHIFT_N]
WORK_SHIFTS = [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M]
REST_SHIFTS = [SHIFT_OFF, SHIFT_R]
ALL_SHIFTS = [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R, SHIFT_OFF]

MAX_CONTINUOUS_WORK = 5
MIN_FULLTIME_OFF_DAYS = 8
TARGET_FULLTIME_OFF_DAYS = 9

# 大夜固定模式：N → N → off → off
NIGHT_BLOCK = [SHIFT_N, SHIFT_N, SHIFT_OFF, SHIFT_OFF]

# D/E 可混連，但 E 後不可 D。D 可以接 N，E 可以接 N。
FORBIDDEN_TRANSITIONS = {
    (SHIFT_E, SHIFT_D),
    (SHIFT_N, SHIFT_D),
    (SHIFT_N, SHIFT_E),
    (SHIFT_N, SHIFT_M),
}

DEFAULT_WEEKDAY_MANPOWER = {
    "D_min": 4, "D_max": 6,
    "E_min": 3, "E_max": 4,
    "N_min": 2, "N_max": 2,
}

DEFAULT_WEEKEND_MANPOWER = {
    "D_min": 3, "D_max": 5,
    "E_min": 2, "E_max": 4,
    "N_min": 2, "N_max": 2,
}

SHIFT_COLORS = {
    SHIFT_D: "FFF59D",     # 黃
    SHIFT_E: "C8E6C9",     # 綠
    SHIFT_N: "90CAF9",     # 藍
    SHIFT_M: "CE93D8",     # 紫
    SHIFT_R: "EF9A9A",     # 紅
    SHIFT_OFF: "E0E0E0",   # 灰
}

SCORE_WEIGHTS = {
    "hard_violation": 1000,
    "manpower_shortage": 500,
    "fragment": 100,
    "holiday": 50,
    "night_fairness": 20,
    "workload_fairness": 10,
}
