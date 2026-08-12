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

# 可用班別權限（供人員設定下拉選單使用）
PERMISSION_OPTIONS = ["DEN", "DE", "DN", "EN", "D", "E", "N"]

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
    "D_min": 4,
    "E_min": 3,
    "N_min": 2,
}

DEFAULT_WEEKEND_MANPOWER = {
    "D_min": 3,
    "E_min": 2,
    "N_min": 2,
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


# =====================================================
# 請假管理
# =====================================================
# 排班核心內部仍以 R 代表「當天不可排班」；
# 下面的假別用於 UI 顯示、統計與 Excel 匯出。
LEAVE_TYPES = [
    "特休",
    "病假",
    "事假",
    "公假",
    "婚假",
    "喪假",
    "產假",
    "陪產假",
    "家庭照顧假",
    "生理假",
    "育嬰假",
    "無薪假",
    "其他",
]

LEAVE_DISPLAY_CODES = {
    "特休": "特休",
    "病假": "病假",
    "事假": "事假",
    "公假": "公假",
    "婚假": "婚假",
    "喪假": "喪假",
    "產假": "產假",
    "陪產假": "陪產",
    "家庭照顧假": "家照",
    "生理假": "生理",
    "育嬰假": "育嬰",
    "無薪假": "無薪",
    "其他": "其他假",
}

LEAVE_COLORS = {
    "特休": "FFD6A5",
    "病假": "FFADAD",
    "事假": "FDFFB6",
    "公假": "CAFFBF",
    "婚假": "FFC6FF",
    "喪假": "BDB2FF",
    "產假": "A0C4FF",
    "陪產": "9BF6FF",
    "家照": "CDEAC0",
    "生理": "FFB5E8",
    "育嬰": "B5EAD7",
    "無薪": "D9D9D9",
    "其他假": "E2F0D9",
}

SHIFT_COLORS.update(LEAVE_COLORS)


# =====================================================
# 班別權限顯示顏色
# =====================================================
# 最終班表的 D/E/N/M/R/off/各類假別不再上底色；
# 只有「班別權限」欄統一使用這個顏色。
PERMISSION_CELL_COLOR = "D9EAF7"   # 淺藍


# =====================================================
# 最終班表問題標示顏色
# =====================================================
# 當日人力「多於或少於最低需求」，或規則檢查有問題時使用。
PROBLEM_CELL_COLOR = "FFC7CE"      # 淺紅底
PROBLEM_FONT_COLOR = "9C0006"      # 深紅字
