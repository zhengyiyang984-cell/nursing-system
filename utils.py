import datetime as dt
from config import DEFAULT_WEEKDAY_MANPOWER, DEFAULT_WEEKEND_MANPOWER

WEEKDAYS_CHINESE = {0: "一", 1: "二", 2: "三", 3: "四", 4: "五", 5: "六", 6: "日"}


def make_date_headers(start_date, num_days):
    headers = []
    for i in range(num_days):
        cur = start_date + dt.timedelta(days=i)
        headers.append(f"{cur.strftime('%m/%d')}({WEEKDAYS_CHINESE[cur.weekday()]})")
    return headers


def default_manpower_by_dates(start_date, num_days):
    rows = []
    for i in range(num_days):
        cur = start_date + dt.timedelta(days=i)
        base = DEFAULT_WEEKEND_MANPOWER if cur.weekday() >= 5 else DEFAULT_WEEKDAY_MANPOWER
        rows.append(dict(base))
    return rows


def count_shift(schedule, names, day, shift):
    return sum(1 for n in names if schedule[n][day] == shift)
