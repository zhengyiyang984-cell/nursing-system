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
    """分數越高越好。Error 權重大於公平性，避免選到仍有硬性錯誤的班表。"""
    issues = validate_schedule(schedule, names, manpower, history_shift, requests, history_streak)
    score = 1_000_000.0

    for day in range(len(manpower)):
        for shift in CLINICAL_SHIFTS:
            actual = _shift_count(schedule, names, day, shift)
            min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
            if actual < min_req:
                score -= (min_req - actual) * 60000

    for issue in issues:
        category = str(issue.get("category", ""))
        message = str(issue.get("message", ""))
        severity = issue.get("severity", "warning")

        if "每日人力" in category or "低於最低" in message:
            score -= 60000
        elif "連續上班" in category:
            score -= 50000
        elif "全職休假不足" in category or "休假不足" in category:
            score -= 45000
        elif "大夜" in category or "N→N→off→off" in message:
            score -= 40000
        elif "班別銜接" in category or "E 後不能接 D" in message:
            score -= 35000
        elif severity == "error":
            score -= 30000
        elif "碎班" in category:
            score -= 8000
        elif "每週休假" in category:
            score -= 6000
        else:
            score -= 1000

    full_time = _full_time(names)
    if full_time:
        night_counts = [sum(1 for x in schedule[n] if x == SHIFT_N) for n in full_time]
        day_counts = [sum(1 for x in schedule[n] if x == SHIFT_D) for n in full_time]
        work_counts = [sum(1 for x in schedule[n] if x in WORK_SHIFTS) for n in full_time]
        off_counts = [sum(1 for x in schedule[n] if x in REST_SHIFTS) for n in full_time]

        score -= safe_stdev(night_counts) * 1200
        score -= safe_stdev(day_counts) * 600
        score -= safe_stdev(work_counts) * 500
        score -= safe_stdev(off_counts) * 300

        # 休假以 8 天為主要目標；9 天可接受，但會有小幅扣分。
        for off_count in off_counts:
            if off_count < MIN_FULLTIME_OFF_DAYS:
                score -= (MIN_FULLTIME_OFF_DAYS - off_count) * 10000
            elif off_count == TARGET_FULLTIME_OFF_DAYS:
                pass
            elif off_count <= MAX_FULLTIME_OFF_DAYS:
                score -= (off_count - TARGET_FULLTIME_OFF_DAYS) * 800
            else:
                score -= (off_count - MAX_FULLTIME_OFF_DAYS) * 5000

    return round(score, 2), issues


def _try_move_shift(schedule, names, requests, manpower, shift, day, rng):
    min_req = int(manpower[day].get(f"{shift}_min", 0) or 0)
    if _shift_count(schedule, names, day, shift) >= min_req:
        return False

    donor_days = list(range(len(manpower)))
    rng.shuffle(donor_days)
    donor_days.sort(
        key=lambda d: _shift_count(schedule, names, d, shift)
        - int(manpower[d].get(f"{shift}_min", 0) or 0),
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

            schedule[nurse][from_day] = SHIFT_OFF
            schedule[nurse][day] = shift
            return True

    return False


def _issues_quality(issues, score):
    """硬性錯誤永遠優先；只有錯誤相同時才比較 warning 與 score。"""
    errors = [x for x in issues if x.get("severity") == "error"]
    warnings = [x for x in issues if x.get("severity") != "error"]

    manpower = sum(1 for x in errors if "人力" in str(x.get("category", "")))
    requests_err = sum(1 for x in errors if "預排" in str(x.get("category", "")))
    nights = sum(1 for x in errors if "大夜" in str(x.get("category", "")))
    transitions = sum(1 for x in errors if "銜接" in str(x.get("category", "")))
    streaks = sum(1 for x in errors if "連續上班" in str(x.get("category", "")))
    holidays = sum(1 for x in errors if "休假不足" in str(x.get("category", "")))

    return (
        len(errors),
        manpower,
        requests_err,
        nights,
        transitions,
        streaks,
        holidays,
        len(warnings),
        -float(score),
    )


def _local_search(schedule, names, manpower, history_shift, requests, history_streak, rng, rounds=20):
    best = deepcopy(schedule)
    best_score, best_issues = score_schedule(best, names, manpower, history_shift, requests, history_streak)
    best_quality = _issues_quality(best_issues, best_score)

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
        trial_quality = _issues_quality(issues, s)

        # V27：絕不接受 error 數更多的 trial。
        if trial_quality < best_quality:
            best = trial
            best_score = s
            best_issues = issues
            best_quality = trial_quality

    return best, best_score, best_issues



def quality_key(item):
    """V27：0 Error 永遠排在任何含 Error 的班表前面。"""
    return _issues_quality(
        item.get("issues", []),
        float(item.get("score", 0)),
    )

def optimize_schedule(
    names,
    permissions,
    requests,
    manpower,
    history_shift,
    history_streak,
    attempts=60,
    base_seed=None,
    progress_callback=None,
    local_search_top=3,
    local_search_rounds=8,
    patience=15,
):
    """
    V26.5 加速版：
    1. 第一階段只快速建立候選班表 + 評分，不對每一份都跑 Local Search。
    2. 只挑前幾名候選做 Local Search。
    3. 連續多次沒有改善時提早停止。
    4. 一旦得到 0 error 的高品質班表，可提前結束。

    舊版：attempts × 20 次 local search。
    新版：attempts 次快速候選 + 前 local_search_top 名才做 local search。
    """
    rng = random.Random(base_seed)
    attempts = max(1, int(attempts))
    local_search_top = max(1, int(local_search_top))
    local_search_rounds = max(0, int(local_search_rounds))
    patience = max(3, int(patience))

    candidates = []
    best = None
    no_improve = 0

    # ==============================
    # Stage 1：快速產生候選班表
    # ==============================
    for i in range(attempts):
        seed = rng.randint(1, 10_000_000)

        schedule = build_schedule_once(
            names,
            permissions,
            requests,
            manpower,
            history_shift,
            history_streak,
            seed=seed,
        )

        score, issues = score_schedule(
            schedule,
            names,
            manpower,
            history_shift,
            requests,
            history_streak,
        )

        item = {
            "rank": None,
            "score": score,
            "issues": issues,
            "schedule": schedule,
            "seed": seed,
        }
        candidates.append(item)

        improved = best is None or quality_key(item) < quality_key(best)

        if improved:
            best = item
            no_improve = 0
        else:
            no_improve += 1

        if progress_callback:
            progress_callback(i + 1, attempts, best["score"])

        best_errors = sum(
            1 for x in best.get("issues", [])
            if x.get("severity") == "error"
        )
        best_warnings = sum(
            1 for x in best.get("issues", [])
            if x.get("severity") != "error"
        )

        # 已經得到無 error 的結果，不必浪費大量嘗試。
        if best_errors == 0 and i >= min(7, attempts - 1):
            # warning 很少時直接進入第二階段
            if best_warnings <= 3:
                break

            # 雖有 warning，但很久沒改善也停止
            if no_improve >= max(6, patience // 2):
                break

        # 一直沒有改善就停止
        if i >= 12 and no_improve >= patience:
            break

    # 只保留品質最好的候選，避免大量 schedule 留在記憶體。
    candidates.sort(key=quality_key)
    shortlist = candidates[:min(local_search_top, len(candidates))]

    # ==============================
    # Stage 2：只精修前幾名
    # ==============================
    refined = []

    for item in shortlist:
        if local_search_rounds <= 0:
            refined.append(item)
            continue

        seed = item["seed"]

        schedule, score, issues = _local_search(
            item["schedule"],
            names,
            manpower,
            history_shift,
            requests,
            history_streak,
            random.Random(seed + 99),
            rounds=local_search_rounds,
        )

        refined.append({
            "rank": None,
            "score": score,
            "issues": issues,
            "schedule": schedule,
            "seed": seed,
        })

    # 原候選 + 精修候選一起比較
    results = candidates[:10] + refined
    results.sort(key=quality_key)

    # 去除相同 seed 的較差重複版本，只留品質最好者
    unique = []
    seen_seed = set()

    for item in results:
        seed = item["seed"]
        if seed in seen_seed:
            continue
        seen_seed.add(seed)
        unique.append(item)

    best = unique[0] if unique else best

    for idx, item in enumerate(unique, start=1):
        item["rank"] = idx

    return best, unique[:10]

