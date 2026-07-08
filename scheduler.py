"""
scheduler.py - 2F 護理排班系統 V20 Solver

保留原 API：
    build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None)

設計原則：
1. 預排 D/E/N/M/R 最高優先，固定鎖定，不被覆蓋。
2. 最低人力優先，D/E/N 會盡力補滿，不調低需求。
3. N 盡量整理成 N→N→off→off。
4. 全職至少 8 天休、最多連續上班 5 天。
5. 郭珍君等半職只排 D，目標 10 天。
6. 所有迴圈都有 guard，避免 Streamlit 卡住。
"""

import random
from config import *

SHIFT_D = globals().get("SHIFT_D", "D")
SHIFT_E = globals().get("SHIFT_E", "E")
SHIFT_N = globals().get("SHIFT_N", "N")
SHIFT_M = globals().get("SHIFT_M", "M")
SHIFT_R = globals().get("SHIFT_R", "R")
SHIFT_OFF = globals().get("SHIFT_OFF", "off")

CLINICAL_SHIFTS = globals().get("CLINICAL_SHIFTS", [SHIFT_D, SHIFT_E, SHIFT_N])
WORK_SHIFTS = globals().get("WORK_SHIFTS", [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M])
REST_SHIFTS = globals().get("REST_SHIFTS", [SHIFT_OFF, SHIFT_R])

PART_TIME = globals().get("PART_TIME", ["郭珍君"])
PARTTIME_DAYS = globals().get("PARTTIME_DAYS", 10)
PARTTIME_ALLOWED_SHIFT = globals().get("PARTTIME_ALLOWED_SHIFT", SHIFT_D)

MAX_CONTINUOUS_WORK = globals().get("MAX_CONTINUOUS_WORK", 5)
MIN_FULLTIME_OFF_DAYS = globals().get("MIN_FULLTIME_OFF_DAYS", 8)
TARGET_FULLTIME_OFF_DAYS = globals().get("TARGET_FULLTIME_OFF_DAYS", 9)

FORBIDDEN_TRANSITIONS = globals().get(
    "FORBIDDEN_TRANSITIONS",
    {(SHIFT_E, SHIFT_D), (SHIFT_N, SHIFT_D), (SHIFT_N, SHIFT_E), (SHIFT_N, SHIFT_M)},
)


class NurseScheduler:
    def __init__(self, names, permissions, requests, manpower, history_shift, history_streak, seed=None):
        self.names = list(names)
        self.permissions = permissions or {}
        self.requests = requests or {}
        self.manpower = manpower or []
        self.history_shift = history_shift or {}
        self.history_streak = history_streak or {}
        self.days = len(self.manpower)
        self.random = random.Random(seed)

        self.schedule = {n: ["" for _ in range(self.days)] for n in self.names}
        self.locked = {n: [False for _ in range(self.days)] for n in self.names}
        self.night_locked = {n: [False for _ in range(self.days)] for n in self.names}

    # ============================================================
    # 主流程
    # ============================================================
    def generate(self):
        self._apply_requests()
        self._restore_locked_requests()

        self._assign_parttime()
        self._repair_fixed_night_requests()
        self._assign_night_blocks()

        self._repair_manpower_shortage(max_rounds=4)
        self._fill_blank_with_off()

        for _ in range(8):
            before = self._snapshot()

            self._restore_locked_requests()
            self._repair_fixed_night_requests()
            self._repair_night_blocks()
            self._repair_manpower_shortage(max_rounds=3)
            self._balance_holidays()
            self._repair_long_streaks()
            self._repair_manpower_shortage(max_rounds=3)
            self._repair_e_to_d_transitions()
            self._remove_single_day_fragments()
            self._trim_parttime_to_target()
            self._fill_blank_with_off()

            if before == self._snapshot():
                break

        # 最後一輪：硬性規則優先
        for _ in range(5):
            self._restore_locked_requests()
            self._repair_fixed_night_requests()
            self._repair_night_blocks()
            self._repair_manpower_shortage(max_rounds=3)
            self._balance_holidays()
            self._repair_long_streaks()
            self._repair_manpower_shortage(max_rounds=2)
            self._fill_blank_with_off()

        return self.schedule

    def _snapshot(self):
        return tuple(tuple(self.schedule[n]) for n in self.names)

    # ============================================================
    # 基礎工具
    # ============================================================
    def _req(self, nurse, day):
        row = self.requests.get(nurse, [""] * self.days)
        if day < 0 or day >= len(row):
            return ""
        return row[day]

    def _is_fulltime(self, nurse):
        return nurse not in PART_TIME

    def _is_parttime(self, nurse):
        return nurse in PART_TIME

    def _min_req(self, day, shift):
        if day < 0 or day >= self.days:
            return 0
        return int(self.manpower[day].get(f"{shift}_min", 0) or 0)

    def _shift_count(self, day, shift):
        if day < 0 or day >= self.days:
            return 0
        return sum(1 for n in self.names if self.schedule[n][day] == shift)

    def _workload(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in WORK_SHIFTS)

    def _shift_workload(self, nurse, shift):
        return sum(1 for x in self.schedule[nurse] if x == shift)

    def _off_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in REST_SHIFTS or x == "")

    def _prev(self, nurse, day):
        if day == 0:
            return self.history_shift.get(nurse, SHIFT_OFF)
        return self.schedule[nurse][day - 1]

    def _next(self, nurse, day):
        if day >= self.days - 1:
            return SHIFT_OFF
        return self.schedule[nurse][day + 1]

    def _permission_ok(self, nurse, shift):
        if self._is_parttime(nurse):
            return shift == PARTTIME_ALLOWED_SHIFT
        return shift in str(self.permissions.get(nurse, "DEN")).upper()

    def _fixed_request(self, nurse, day):
        return self._req(nurse, day) in [SHIFT_R, SHIFT_M] or self._req(nurse, day) in CLINICAL_SHIFTS

    def _transition_ok(self, nurse, day, shift):
        prev_shift = self._prev(nurse, day)
        next_shift = self._next(nurse, day)

        if (prev_shift, shift) in FORBIDDEN_TRANSITIONS:
            return False
        if prev_shift == SHIFT_N and shift not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
            return False
        if shift == SHIFT_E and next_shift == SHIFT_D:
            return False
        if shift == SHIFT_D and prev_shift == SHIFT_E:
            return False
        return True

    def _continuous_before(self, nurse, day):
        if day == 0:
            return int(self.history_streak.get(nurse, 0) or 0)
        count = 0
        d = day - 1
        while d >= 0 and self.schedule[nurse][d] in WORK_SHIFTS:
            count += 1
            d -= 1
        return count

    def _continuous_after(self, nurse, day):
        count = 0
        d = day + 1
        while d < self.days and self.schedule[nurse][d] in WORK_SHIFTS:
            count += 1
            d += 1
        return count

    def _max_streak_ok(self, nurse, day, shift):
        if shift not in WORK_SHIFTS:
            return True
        return self._continuous_before(nurse, day) + 1 + self._continuous_after(nurse, day) <= MAX_CONTINUOUS_WORK

    def _can_assign(self, nurse, day, shift, allow_overwrite_off=False, relax_streak=False):
        if day < 0 or day >= self.days:
            return False

        # 預排 D/E/N/M/R 不能被後續流程覆蓋。
        if self._fixed_request(nurse, day):
            return False
        if self.locked[nurse][day] or self.night_locked[nurse][day]:
            return False

        cur = self.schedule[nurse][day]
        if cur == SHIFT_OFF and not allow_overwrite_off:
            return False
        if cur not in ["", SHIFT_OFF]:
            return False

        if not self._permission_ok(nurse, shift):
            return False
        if not self._transition_ok(nurse, day, shift):
            return False
        if not relax_streak and not self._max_streak_ok(nurse, day, shift):
            return False

        return True

    def _can_set_off(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self.locked[nurse][day] or self.night_locked[nurse][day]:
            return False
        if self._fixed_request(nurse, day):
            return False
        return True

    def _day_has_surplus(self, day, shift):
        return self._shift_count(day, shift) > self._min_req(day, shift)

    # ============================================================
    # 固定預排
    # ============================================================
    def _apply_requests(self):
        for nurse in self.names:
            for day in range(self.days):
                req = self._req(nurse, day)
                if req == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                    self.locked[nurse][day] = True
                elif req == SHIFT_M:
                    self.schedule[nurse][day] = SHIFT_M
                    self.locked[nurse][day] = True
                elif req in CLINICAL_SHIFTS:
                    # 人工預排優先，不檢查權限，避免 D/E/N 被忽略成 off。
                    self.schedule[nurse][day] = req
                    self.locked[nurse][day] = True

    def _restore_locked_requests(self):
        for nurse in self.names:
            for day in range(self.days):
                req = self._req(nurse, day)
                if req == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                    self.locked[nurse][day] = True
                    self.night_locked[nurse][day] = False
                elif req == SHIFT_M:
                    self.schedule[nurse][day] = SHIFT_M
                    self.locked[nurse][day] = True
                    self.night_locked[nurse][day] = False
                elif req in CLINICAL_SHIFTS:
                    self.schedule[nurse][day] = req
                    self.locked[nurse][day] = True

    # ============================================================
    # 半職
    # ============================================================
    def _assign_parttime(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue

            # 先清掉半職非預排 D，重新排到 10 天
            for day in range(self.days):
                if not self.locked[nurse][day] and self.schedule[nurse][day] == PARTTIME_ALLOWED_SHIFT:
                    self.schedule[nurse][day] = ""

            current = sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT)
            remaining = max(0, PARTTIME_DAYS - current)

            blocks = [3, 3, 2, 2]
            self.random.shuffle(blocks)

            for length in blocks:
                if remaining <= 0:
                    break
                length = min(length, remaining)
                starts = list(range(0, max(0, self.days - length + 1)))
                self.random.shuffle(starts)
                starts.sort(key=lambda s: self._parttime_block_score(nurse, s, length), reverse=True)

                for start in starts:
                    if self._can_place_parttime_block(nurse, start, length):
                        for d in range(start, start + length):
                            self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                            self.locked[nurse][d] = True
                        remaining -= length
                        break

            # 若區塊排不滿，再用 D 缺人的日期補
            for day in sorted(range(self.days), key=lambda d: self._shift_count(d, SHIFT_D) - self._min_req(d, SHIFT_D)):
                if remaining <= 0:
                    break
                if self._can_assign(nurse, day, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True, relax_streak=True):
                    self.schedule[nurse][day] = PARTTIME_ALLOWED_SHIFT
                    self.locked[nurse][day] = True
                    remaining -= 1

            self._trim_parttime_to_target(nurse)

    def _parttime_block_score(self, nurse, start, length):
        score = 0
        for d in range(start, start + length):
            score += max(0, self._min_req(d, SHIFT_D) - self._shift_count(d, SHIFT_D)) * 20
        return score + self.random.random()

    def _can_place_parttime_block(self, nurse, start, length):
        if start < 0 or start + length > self.days:
            return False
        if start > 0 and self.schedule[nurse][start - 1] == PARTTIME_ALLOWED_SHIFT:
            return False
        if start + length < self.days and self.schedule[nurse][start + length] == PARTTIME_ALLOWED_SHIFT:
            return False
        for day in range(start, start + length):
            if not self._can_assign(nurse, day, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True, relax_streak=True):
                return False
        return True

    def _trim_parttime_to_target(self, nurse=None):
        nurses = [nurse] if nurse else [n for n in PART_TIME if n in self.names]
        for n in nurses:
            guard = 0
            while sum(1 for x in self.schedule[n] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                guard += 1
                if guard > self.days:
                    break
                removed = False
                days = list(reversed(range(self.days)))
                days.sort(key=lambda d: self._day_has_surplus(d, PARTTIME_ALLOWED_SHIFT), reverse=True)
                for day in days:
                    if self.schedule[n][day] == PARTTIME_ALLOWED_SHIFT and not self.locked[n][day]:
                        if self._day_has_surplus(day, PARTTIME_ALLOWED_SHIFT):
                            self.schedule[n][day] = SHIFT_OFF
                            removed = True
                            break
                if not removed:
                    break

    # ============================================================
    # 夜班 N→N→off→off
    # ============================================================
    def _assign_night_blocks(self):
        attempts = max(1, self.days * max(1, len(self.names)) * 3)
        for _ in range(attempts):
            shortage = [d for d in range(self.days) if self._shift_count(d, SHIFT_N) < self._min_req(d, SHIFT_N)]
            if not shortage:
                break
            shortage.sort(key=lambda d: (self._shift_count(d, SHIFT_N) - self._min_req(d, SHIFT_N), d))
            placed = False
            for day in shortage:
                if self._place_best_night_block_covering(day):
                    placed = True
                    break
                if self._force_fill_shift(day, SHIFT_N):
                    placed = True
                    break
            if not placed:
                break

    def _repair_fixed_night_requests(self):
        """將預排單顆 N 盡量擴成 N,N,off,off。"""
        for nurse in self.names:
            if self._is_parttime(nurse):
                continue
            for day in range(self.days):
                if self.schedule[nurse][day] != SHIFT_N:
                    continue

                left_n = day > 0 and self.schedule[nurse][day - 1] == SHIFT_N
                right_n = day + 1 < self.days and self.schedule[nurse][day + 1] == SHIFT_N
                if left_n or right_n:
                    continue

                # 優先 N,N 從當天開始
                if self._can_extend_fixed_night(nurse, day):
                    self._extend_fixed_night(nurse, day)
                    continue

                # 再試前一天 + 當天
                if self._can_extend_fixed_night(nurse, day - 1):
                    self._extend_fixed_night(nurse, day - 1)
                    continue

    def _can_extend_fixed_night(self, nurse, start):
        if start < 0 or start + 1 >= self.days:
            return False
        if self._is_parttime(nurse):
            return False

        for d in [start, start + 1]:
            if self.schedule[nurse][d] == SHIFT_N:
                continue
            if self.locked[nurse][d] or self.night_locked[nurse][d]:
                return False
            if self._fixed_request(nurse, d):
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False
            if not self._permission_ok(nurse, SHIFT_N):
                return False

        for d in [start + 2, start + 3]:
            if d >= self.days:
                continue
            if self.schedule[nurse][d] in REST_SHIFTS:
                continue
            if self.locked[nurse][d] or self.night_locked[nurse][d]:
                return False
            if self._fixed_request(nurse, d):
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False

        return True

    def _extend_fixed_night(self, nurse, start):
        for d in [start, start + 1]:
            if 0 <= d < self.days:
                self.schedule[nurse][d] = SHIFT_N
                self.night_locked[nurse][d] = True
        for d in [start + 2, start + 3]:
            if 0 <= d < self.days:
                if self.schedule[nurse][d] == SHIFT_R:
                    self.locked[nurse][d] = True
                else:
                    self.schedule[nurse][d] = SHIFT_OFF
                    self.night_locked[nurse][d] = True

    def _can_place_night_block(self, nurse, start):
        if start < 0 or start + 1 >= self.days:
            return False
        if self._is_parttime(nurse) or not self._permission_ok(nurse, SHIFT_N):
            return False
        if self._prev(nurse, start) in [SHIFT_D, SHIFT_E, SHIFT_M]:
            return False

        for d in [start, start + 1]:
            if self.schedule[nurse][d] == SHIFT_N:
                continue
            if self._fixed_request(nurse, d) or self.locked[nurse][d] or self.night_locked[nurse][d]:
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False

        for d in [start + 2, start + 3]:
            if d >= self.days:
                continue
            if self.schedule[nurse][d] in REST_SHIFTS:
                continue
            if self._fixed_request(nurse, d) or self.locked[nurse][d] or self.night_locked[nurse][d]:
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False

        return True

    def _place_best_night_block_covering(self, target_day):
        options = []
        for start in [target_day - 1, target_day]:
            for nurse in self.names:
                if self._can_place_night_block(nurse, start):
                    score = self._night_block_score(nurse, start, target_day)
                    options.append((score, nurse, start))
        if not options:
            return False
        self.random.shuffle(options)
        options.sort(key=lambda x: x[0], reverse=True)
        _, nurse, start = options[0]
        self._place_night_block(nurse, start)
        return True

    def _night_block_score(self, nurse, start, target_day):
        score = 0.0
        for d in [start, start + 1]:
            score += max(0, self._min_req(d, SHIFT_N) - self._shift_count(d, SHIFT_N)) * 100
        if start <= target_day <= start + 1:
            score += 50
        score -= self._shift_workload(nurse, SHIFT_N) * 20
        score -= self._workload(nurse) * 2
        return score + self.random.random()

    def _place_night_block(self, nurse, start):
        for d in [start, start + 1]:
            if 0 <= d < self.days:
                self.schedule[nurse][d] = SHIFT_N
                self.night_locked[nurse][d] = True
        for d in [start + 2, start + 3]:
            if 0 <= d < self.days:
                if self.schedule[nurse][d] == SHIFT_R or self._req(nurse, d) == SHIFT_R:
                    self.schedule[nurse][d] = SHIFT_R
                    self.locked[nurse][d] = True
                else:
                    self.schedule[nurse][d] = SHIFT_OFF
                    self.night_locked[nurse][d] = True

    def _repair_night_blocks(self):
        for nurse in self.names:
            if self._is_parttime(nurse):
                continue
            day = 0
            while day < self.days:
                if self.schedule[nurse][day] != SHIFT_N:
                    day += 1
                    continue

                left_n = day > 0 and self.schedule[nurse][day - 1] == SHIFT_N
                right_n = day + 1 < self.days and self.schedule[nurse][day + 1] == SHIFT_N

                if not (left_n or right_n):
                    if self._can_extend_fixed_night(nurse, day):
                        self._extend_fixed_night(nurse, day)
                    elif self._can_extend_fixed_night(nurse, day - 1):
                        self._extend_fixed_night(nurse, day - 1)
                    elif not self.locked[nurse][day] and self._day_has_surplus(day, SHIFT_N):
                        self.schedule[nurse][day] = SHIFT_OFF
                        self.night_locked[nurse][day] = False
                    day += 1
                    continue

                # 找到 N,N 後，確保後兩天休
                if right_n:
                    start = day
                else:
                    start = day - 1

                for rest_day in [start + 2, start + 3]:
                    if rest_day >= self.days:
                        continue
                    if self.schedule[nurse][rest_day] in REST_SHIFTS:
                        continue
                    if self._can_set_off(nurse, rest_day):
                        shift = self.schedule[nurse][rest_day]
                        if shift in [SHIFT_D, SHIFT_E] and self._day_has_surplus(rest_day, shift):
                            self.schedule[nurse][rest_day] = SHIFT_OFF
                        elif shift in [SHIFT_D, SHIFT_E] and self._swap_to_make_off(nurse, rest_day, shift):
                            pass

                day += 1

    # ============================================================
    # D / E / N 人力補足
    # ============================================================
    def _clinical_candidates(self, day, shift, relax_streak=False):
        candidates = []
        for nurse in self.names:
            if self._can_assign(nurse, day, shift, allow_overwrite_off=True, relax_streak=relax_streak):
                candidates.append(nurse)
        self.random.shuffle(candidates)
        candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
        return candidates

    def _candidate_score(self, nurse, day, shift):
        score = 0.0
        score += max(0, self._min_req(day, shift) - self._shift_count(day, shift)) * 100
        if self._prev(nurse, day) == shift:
            score += 15
        if self._next(nurse, day) == shift:
            score += 10
        if self._off_count(nurse) < MIN_FULLTIME_OFF_DAYS:
            score -= 20
        score -= self._shift_workload(nurse, shift) * 8
        score -= self._workload(nurse) * 3
        return score + self.random.random()

    def _force_fill_shift(self, day, shift):
        # 第一輪：完全合法
        candidates = self._clinical_candidates(day, shift, relax_streak=False)
        if candidates:
            self.schedule[candidates[0]][day] = shift
            return True

        # 第二輪：醫院模式，最低人力優先，可暫時放寬連班，後續再修
        candidates = self._clinical_candidates(day, shift, relax_streak=True)
        if candidates:
            self.schedule[candidates[0]][day] = shift
            return True

        return False

    def _repair_manpower_shortage(self, max_rounds=3):
        for _ in range(max_rounds):
            changed = False

            for day in range(self.days):
                for shift in [SHIFT_N, SHIFT_E, SHIFT_D]:
                    guard = 0
                    while self._shift_count(day, shift) < self._min_req(day, shift):
                        guard += 1
                        if guard > len(self.names) * 3:
                            break

                        if shift == SHIFT_N and self._place_best_night_block_covering(day):
                            changed = True
                            continue

                        if self._force_fill_shift(day, shift):
                            changed = True
                            continue

                        break

            if not changed:
                break

    # ============================================================
    # 休假與連班
    # ============================================================
    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    self.schedule[nurse][day] = SHIFT_OFF

    def _find_longest_streak(self, nurse):
        best = None
        cur_start = None
        cur_len = int(self.history_streak.get(nurse, 0) or 0)
        if cur_len > 0:
            cur_start = 0

        for day in range(self.days):
            if self.schedule[nurse][day] in WORK_SHIFTS:
                if cur_start is None:
                    cur_start = day
                    cur_len = 0
                cur_len += 1
            else:
                if cur_start is not None and (best is None or cur_len > best[2]):
                    best = (cur_start, day - 1, cur_len)
                cur_start = None
                cur_len = 0

        if cur_start is not None and (best is None or cur_len > best[2]):
            best = (cur_start, self.days - 1, cur_len)

        return best

    def _repair_long_streaks(self):
        for nurse in self.names:
            if not self._is_fulltime(nurse):
                continue

            for _ in range(12):
                streak = self._find_longest_streak(nurse)
                if not streak or streak[2] <= MAX_CONTINUOUS_WORK:
                    break

                start, end, _length = streak
                days = list(range(start, end + 1))
                days.sort(key=lambda d: abs(d - (start + end) / 2))

                fixed = False
                for day in days:
                    shift = self.schedule[nurse][day]
                    if shift not in [SHIFT_D, SHIFT_E]:
                        continue
                    if not self._can_set_off(nurse, day):
                        continue

                    if self._day_has_surplus(day, shift):
                        self.schedule[nurse][day] = SHIFT_OFF
                        fixed = True
                        break

                    if self._swap_to_make_off(nurse, day, shift):
                        fixed = True
                        break

                if not fixed:
                    break

    def _balance_holidays(self):
        full_time = [n for n in self.names if self._is_fulltime(n)]

        for _ in range(40):
            changed = False
            off_counts = {n: sum(1 for x in self.schedule[n] if x in REST_SHIFTS) for n in full_time}

            # 每週至少一天休
            for nurse in sorted(full_time, key=lambda n: off_counts[n]):
                for start in range(0, self.days, 7):
                    end = min(start + 7, self.days)
                    block = self.schedule[nurse][start:end]
                    if len(block) >= 5 and not any(x in REST_SHIFTS for x in block):
                        if self._create_holiday(nurse, start, end, off_counts):
                            changed = True
                            break
                if changed:
                    break

            if changed:
                continue

            # 全職至少 8 天休
            under = [n for n in full_time if off_counts[n] < MIN_FULLTIME_OFF_DAYS]
            if not under:
                break

            under.sort(key=lambda n: off_counts[n])
            for nurse in under:
                if self._create_holiday(nurse, 0, self.days, off_counts):
                    changed = True
                    break

            if not changed:
                break

    def _create_holiday(self, nurse, start, end, off_counts):
        for day in self._holiday_candidate_days(nurse, start, end):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_set_off(nurse, day):
                continue

            if self._day_has_surplus(day, shift):
                self.schedule[nurse][day] = SHIFT_OFF
                return True

            if self._swap_to_make_off(nurse, day, shift, off_counts):
                return True

        return False

    def _holiday_candidate_days(self, nurse, start, end):
        days = list(range(start, end))
        self.random.shuffle(days)

        def score(day):
            shift = self.schedule[nurse][day]
            s = 0
            if shift in [SHIFT_D, SHIFT_E] and self._day_has_surplus(day, shift):
                s += 30
            if day > 0 and self.schedule[nurse][day - 1] in REST_SHIFTS:
                s += 5
            if day + 1 < self.days and self.schedule[nurse][day + 1] in REST_SHIFTS:
                s += 5
            if self.locked[nurse][day] or self.night_locked[nurse][day]:
                s -= 100
            return s

        days.sort(key=score, reverse=True)
        return days

    def _swap_to_make_off(self, nurse, day, shift, off_counts=None):
        if not self._can_set_off(nurse, day):
            return False

        helpers = []
        for helper in self.names:
            if helper == nurse or self._is_parttime(helper):
                continue
            if off_counts is not None and off_counts.get(helper, 0) <= TARGET_FULLTIME_OFF_DAYS:
                continue
            if self.schedule[helper][day] != SHIFT_OFF:
                continue
            if self._can_assign(helper, day, shift, allow_overwrite_off=True, relax_streak=True):
                helpers.append(helper)

        if not helpers:
            return False

        self.random.shuffle(helpers)
        helpers.sort(key=lambda h: (self._workload(h), self._shift_workload(h, shift)))
        helper = helpers[0]
        self.schedule[helper][day] = shift
        self.schedule[nurse][day] = SHIFT_OFF
        return True

    # ============================================================
    # 收尾最佳化
    # ============================================================
    def _repair_e_to_d_transitions(self):
        for nurse in self.names:
            if not self._is_fulltime(nurse):
                continue
            for day in range(1, self.days):
                if self.schedule[nurse][day - 1] == SHIFT_E and self.schedule[nurse][day] == SHIFT_D:
                    if not self.locked[nurse][day] and self._day_has_surplus(day, SHIFT_D):
                        self.schedule[nurse][day] = SHIFT_OFF
                    elif not self.locked[nurse][day - 1] and self._day_has_surplus(day - 1, SHIFT_E):
                        self.schedule[nurse][day - 1] = SHIFT_OFF

    def _remove_single_day_fragments(self):
        for _ in range(6):
            changed = False
            for nurse in self.names:
                if not self._is_fulltime(nurse):
                    continue
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E]:
                        continue
                    if self.locked[nurse][day] or self.night_locked[nurse][day]:
                        continue

                    left_rest = day == 0 or self.schedule[nurse][day - 1] in REST_SHIFTS
                    right_rest = day == self.days - 1 or self.schedule[nurse][day + 1] in REST_SHIFTS

                    if not (left_rest and right_rest):
                        continue

                    extended = False
                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                            self.schedule[nurse][nd] = cur
                            extended = True
                            changed = True
                            break

                    if extended:
                        continue

                    if self._day_has_surplus(day, cur) and self._can_set_off(nurse, day):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = True

            if not changed:
                break


def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
    return scheduler.generate()
