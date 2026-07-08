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
    issues = validate_schedule(schedule, names, manpower, history_shift, requests, history_streak)
    score = 1_000_000.0

    # 人力不足是最高優先
    for day in range(len(manpower)):
        for shift in CLINICAL_SHIFTS:
            actual = _shift_count(schedule, names, day, shift)
            min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
            if actual < min_req:
                score -= (min_req - actual) * 30000

    # 規則違規扣分
    for issue in issues:
        category = str(issue.get("category", ""))
        message = str(issue.get("message", ""))
        severity = issue.get("severity", "warning")
        if "每日人力" in category or "低於最低" in message:
            score -= 30000
        elif "大夜" in category or "N→N→off→off" in message:
            score -= 15000
        elif "休假不足" in category or "連續上班" in category:
            score -= 12000
        elif severity == "error":
            score -= 9000
        elif "碎班" in category:
            score -= 700
        else:
            score -= 400

    full_time = _full_time(names)
    if full_time:
        night_counts = [sum(1 for x in schedule[n] if x == SHIFT_N) for n in full_time]
        day_counts = [sum(1 for x in schedule[n] if x == SHIFT_D) for n in full_time]
        work_counts = [sum(1 for x in schedule[n] if x in WORK_SHIFTS) for n in full_time]
        off_counts = [sum(1 for x in schedule[n] if x in REST_SHIFTS) for n in full_time]
        score -= safe_stdev(night_counts) * 1600
        score -= safe_stdev(day_counts) * 900
        score -= safe_stdev(work_counts) * 700
        score -= safe_stdev(off_counts) * 500

    return round(score, 2), issues


def _try_move_shift(schedule, names, requests, manpower, shift, day, rng):
    min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
    if _shift_count(schedule, names, day, shift) >= min_req:
        return False

    donor_days = list(range(len(manpower)))
    rng.shuffle(donor_days)
    donor_days.sort(
        key=lambda d: _shift_count(schedule, names, d, shift) - int(manpower[d].get(f"{shift}_min", 0) or 0),
        reverse=True,
    )
    for from_day in donor_days:
        if from_day == day:
            continue
        if _shift_count(schedule, names, from_day, shift) <= int(manpower[from_day].get(f"{shift}_min", 0) or 0):
            continue
        donors = [
            n for n in names
            if n not in PART_TIME
            and schedule[n][from_day] == shift
            and not _is_fixed_request(requests, n, from_day)
        ]
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


def _local_search(schedule, names, manpower, history_shift, requests, history_streak, rng, rounds=20):
    best = deepcopy(schedule)
    best_score, best_issues = score_schedule(best, names, manpower, history_shift, requests, history_streak)
    for _ in range(rounds):
        trial = deepcopy(best)
        changed = False
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
    attempts = max(1, int(attempts))

    for i in range(attempts):
        seed = rng.randint(1, 10_000_000)
        schedule = build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
        schedule, score, issues = _local_search(
            schedule, names, manpower, history_shift, requests, history_streak, random.Random(seed + 99), rounds=20
        )
        item = {"rank": None, "score": score, "issues": issues, "schedule": schedule, "seed": seed}
        results.append(item)
        if best is None or score > best["score"]:
            best = item
        if progress_callback:
            progress_callback(i + 1, attempts, best["score"])
        # 若已無 error，提早結束，加快 Streamlit
        if best and not any(x.get("severity") == "error" for x in best.get("issues", [])) and i >= min(5, attempts - 1):
            break

    results.sort(key=lambda x: x["score"], reverse=True)
    for idx, item in enumerate(results, start=1):
        item["rank"] = idx
    return best, results[:10]
