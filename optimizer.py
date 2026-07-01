import random
import statistics as py_statistics
from copy import deepcopy

from scheduler import build_schedule_once
from validator import validate_schedule
from config import *


def safe_stdev(values):
    if len(values) <= 1:
        return 0
    try:
        return py_statistics.pstdev(values)
    except Exception:
        return 0


def _shift_count(schedule, names, day, shift):
    return sum(1 for n in names if schedule.get(n, [])[day] == shift)


def _full_time(names):
    return [n for n in names if n not in PART_TIME]


def _is_fixed_request(requests, nurse, day):
    req = requests.get(nurse, [])[day] if nurse in requests and day < len(requests[nurse]) else ""
    return req in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R]


def score_schedule(schedule, names, manpower, history_shift, requests, history_streak=None):
    """
    分數越高越好。
    優先順序：人力達標 > 大夜規則/硬性規則 > 夜班平均 > 白班平均 > 工作量平均。
    """
    issues = validate_schedule(schedule, names, manpower, history_shift, requests, history_streak)
    score = 1_000_000.0

    # 1) 人力優先：缺人是最大扣分，超人次之。
    for day in range(len(manpower)):
        for shift in CLINICAL_SHIFTS:
            actual = _shift_count(schedule, names, day, shift)
            min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
            max_req = int(manpower[day].get(f"{shift}_max", 999) or 999)
            if actual < min_req:
                score -= (min_req - actual) * 20000
            if actual > max_req:
                score -= (actual - max_req) * 2000

    # 2) 規則違規扣分。
    for issue in issues:
        category = str(issue.get("category", ""))
        message = str(issue.get("message", ""))
        severity = issue.get("severity", "warning")
        if "每日人力" in category or "低於最低" in message:
            score -= 20000
        elif "大夜" in category or "N→N→off→off" in message:
            score -= 12000
        elif severity == "error":
            score -= 8000
        elif "碎班" in category:
            score -= 800
        else:
            score -= 500

    full_time = _full_time(names)
    if full_time:
        night_counts = [sum(1 for x in schedule[n] if x == SHIFT_N) for n in full_time]
        day_counts = [sum(1 for x in schedule[n] if x == SHIFT_D) for n in full_time]
        work_counts = [sum(1 for x in schedule[n] if x in WORK_SHIFTS) for n in full_time]
        off_counts = [sum(1 for x in schedule[n] if x in REST_SHIFTS) for n in full_time]

        # 3) 公平性：夜班最重要，其次白班，再來總工作量與休假。
        score -= safe_stdev(night_counts) * 1600
        score -= safe_stdev(day_counts) * 900
        score -= safe_stdev(work_counts) * 700
        score -= safe_stdev(off_counts) * 500

    return round(score, 2), issues


def _try_move_shift(schedule, names, requests, manpower, shift, day, rng):
    """Local Search：把超編日的人移到缺人日，或交換同班別，改善人力與平均。"""
    min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
    if _shift_count(schedule, names, day, shift) >= min_req:
        return False

    # 找其他日該班別超編的人，搬到缺人日；不動預排固定格。
    donor_days = list(range(len(manpower)))
    rng.shuffle(donor_days)
    donor_days.sort(key=lambda d: _shift_count(schedule, names, d, shift) - int(manpower[d].get(f"{shift}_min", 0) or 0), reverse=True)

    for from_day in donor_days:
        if from_day == day:
            continue
        if _shift_count(schedule, names, from_day, shift) <= int(manpower[from_day].get(f"{shift}_min", 0) or 0):
            continue
        donors = [n for n in names if n not in PART_TIME and schedule[n][from_day] == shift and not _is_fixed_request(requests, n, from_day)]
        rng.shuffle(donors)
        donors.sort(key=lambda n: sum(1 for x in schedule[n] if x == shift), reverse=True)
        for nurse in donors:
            if _is_fixed_request(requests, nurse, day):
                continue
            if schedule[nurse][day] not in REST_SHIFTS:
                continue
            trial = deepcopy(schedule)
            trial[nurse][from_day] = SHIFT_OFF
            trial[nurse][day] = shift
            schedule[nurse][from_day] = SHIFT_OFF
            schedule[nurse][day] = shift
            return True
    return False


def _local_search(schedule, names, manpower, history_shift, requests, history_streak, rng, rounds=80):
    """小範圍搜尋：只嘗試不動 R/M/預排的 D/E 調整；保守避免破壞夜班區塊。"""
    best = deepcopy(schedule)
    best_score, best_issues = score_schedule(best, names, manpower, history_shift, requests, history_streak)

    for _ in range(rounds):
        trial = deepcopy(best)
        changed = False

        # 優先修 D/E 缺人，N 交給 scheduler 的 N,N,off,off 區塊處理。
        days = list(range(len(manpower)))
        rng.shuffle(days)
        for day in days:
            for shift in [SHIFT_E, SHIFT_D]:
                if _try_move_shift(trial, names, requests, manpower, shift, day, rng):
                    changed = True

        if not changed:
            continue

        s, issues = score_schedule(trial, names, manpower, history_shift, requests, history_streak)
        if s > best_score:
            best, best_score, best_issues = trial, s, issues

    return best, best_score, best_issues


def optimize_schedule(names, permissions, requests, manpower, history_shift, history_streak, attempts=100, base_seed=None, progress_callback=None):
    best = None
    results = []
    rng = random.Random(base_seed)

    for i in range(max(1, int(attempts))):
        seed = rng.randint(1, 10_000_000)
        schedule = build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
        schedule, score, issues = _local_search(
            schedule, names, manpower, history_shift, requests, history_streak, random.Random(seed + 99), rounds=50
        )
        item = {"rank": None, "score": score, "issues": issues, "schedule": schedule, "seed": seed}
        results.append(item)
        if best is None or score > best["score"]:
            best = item
        if progress_callback:
            progress_callback(i + 1, attempts, best["score"])

    results.sort(key=lambda x: x["score"], reverse=True)
    for idx, item in enumerate(results, start=1):
        item["rank"] = idx
    return best, results[:10]
