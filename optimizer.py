import random
import statistics as py_statistics
from scheduler import build_schedule_once
from validator import validate_schedule
from config import *


def safe_stdev(values):

    if len(values) <= 1:
        return 0

    try:
        return statistics.pstdev(values)
    except:
        return 0

def score_schedule(schedule, names, manpower, history_shift, requests):
    issues = validate_schedule(schedule, names, manpower, history_shift, requests)
    score = 10000

    for issue in issues:
        msg = issue[3]
        if "人力" in str(issue[0]) or "低於最低" in msg:
            score -= SCORE_WEIGHTS["manpower_shortage"]
        elif "碎班" in msg:
            score -= SCORE_WEIGHTS["fragment"]
        else:
            score -= SCORE_WEIGHTS["hard_violation"]

    full_time = [n for n in names if n not in PART_TIME]
    if full_time:
        off_counts = [sum(1 for x in schedule[n] if x in REST_SHIFTS) for n in full_time]
        n_counts = [sum(1 for x in schedule[n] if x == SHIFT_N) for n in full_time]
        work_counts = [sum(1 for x in schedule[n] if x in WORK_SHIFTS) for n in full_time]
        score -= safe_stdev(off_counts) * SCORE_WEIGHTS["holiday"]
        score -= safe_stdev(n_counts) * SCORE_WEIGHTS["night_fairness"]
        score -= safe_stdev(work_counts) * SCORE_WEIGHTS["workload_fairness"]

    return round(score, 2), issues


def optimize_schedule(names, permissions, requests, manpower, history_shift, history_streak, attempts=100, base_seed=None, progress_callback=None):
    best = None
    results = []
    rng = random.Random(base_seed)

    for i in range(max(1, int(attempts))):
        seed = rng.randint(1, 10_000_000)
        schedule = build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
        score, issues = score_schedule(schedule, names, manpower, history_shift, requests)
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
