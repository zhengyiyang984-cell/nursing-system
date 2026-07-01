"""
scheduler.py - 2F 護理排班系統 V6 核心

設計重點：
1. 固定 R / M / 預排班不被後續流程覆蓋。
2. 郭珍君等半職只排 D，盡量剛好 10 天，且不參與後續補班。
3. 大夜只用 N,N,off,off 區塊，不塞單顆 N。
4. 補人力、補休假、修碎班採多輪交替，但不破壞固定區塊。

保留原本 API：
    build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None)
"""

import random
from copy import deepcopy
from config import *

# --------- 安全補值：避免 config.py 少常數時整個程式掛掉 ---------
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
FORBIDDEN_TRANSITIONS = globals().get("FORBIDDEN_TRANSITIONS", [(SHIFT_E, SHIFT_D), (SHIFT_N, SHIFT_D), (SHIFT_N, SHIFT_E)])


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

        # locked=True 的格子不允許後續修復流程覆蓋。
        self.locked = {n: [False for _ in range(self.days)] for n in self.names}

    # ============================================================
    # 主流程
    # ============================================================
    def generate(self):
        self._apply_requests()
        self._assign_parttime()

        # 夜班先排，因為 N,N,off,off 會占用後續兩天休假。
        self._assign_night_blocks()

        # 先補小夜再補白班，避免 E 後接 D。
        self._assign_shift_by_need(SHIFT_E)
        self._assign_shift_by_need(SHIFT_D)
        self._fill_blank_with_off()

        # 多輪修復，但每一輪都不得破壞 R/M/預排/半職/N區塊。
        for _ in range(8):
            before = self._snapshot()
            self._repair_manpower_shortage()
            self._balance_holidays()
            self._remove_single_day_fragments()
            self._repair_night_blocks()
            self._fill_blank_with_off()
            if before == self._snapshot():
                break

        # 最後再補一次人力與休假，盡量降低違規。
        self._repair_manpower_shortage()
        self._balance_holidays()
        self._repair_night_blocks()
        self._trim_parttime_to_target()
        self._fill_blank_with_off()
        return self.schedule

    def _snapshot(self):
        return tuple(tuple(self.schedule[n]) for n in self.names)

    # ============================================================
    # 基礎工具
    # ============================================================
    def _req(self, nurse, day):
        return self.requests.get(nurse, [""] * self.days)[day]

    def _is_fulltime(self, nurse):
        return nurse not in PART_TIME

    def _is_parttime(self, nurse):
        return nurse in PART_TIME

    def _workload(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in WORK_SHIFTS)

    def _night_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x == SHIFT_N)

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

    def _permission_ok(self, nurse, shift):
        if self._is_parttime(nurse):
            return shift == PARTTIME_ALLOWED_SHIFT
        return shift in str(self.permissions.get(nurse, "DEN")).upper()

    def _request_allows(self, nurse, day, shift):
        req = self._req(nurse, day)
        if req == SHIFT_R:
            return False
        if req in CLINICAL_SHIFTS + [SHIFT_M]:
            return req == shift
        return True

    def _transition_ok(self, nurse, day, shift):
        prev = self._prev(nurse, day)
        nxt = self._next(nurse, day)

        if (prev, shift) in FORBIDDEN_TRANSITIONS:
            return False
        if prev == SHIFT_E and shift == SHIFT_D:
            return False
        if prev == SHIFT_N and shift not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
            return False
        if shift == SHIFT_E and nxt == SHIFT_D:
            return False
        if shift == SHIFT_D and prev == SHIFT_E:
            return False
        return True

    def _max_streak_ok(self, nurse, day, shift):
        if shift not in WORK_SHIFTS:
            return True
        return self._continuous_before(nurse, day) + 1 + self._continuous_after(nurse, day) <= MAX_CONTINUOUS_WORK

    def _can_assign(self, nurse, day, shift, allow_overwrite_off=False):
        if day < 0 or day >= self.days:
            return False
        if self.locked[nurse][day]:
            return False

        cur = self.schedule[nurse][day]
        if cur == SHIFT_OFF and not allow_overwrite_off:
            return False
        if cur not in ["", SHIFT_OFF]:
            return False

        if self._req(nurse, day) == SHIFT_R:
            return False
        if not self._permission_ok(nurse, shift):
            return False
        if not self._request_allows(nurse, day, shift):
            return False
        if not self._transition_ok(nurse, day, shift):
            return False
        if not self._max_streak_ok(nurse, day, shift):
            return False
        return True

    def _can_set_off(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self.locked[nurse][day]:
            return False
        if self._req(nurse, day) not in ["", SHIFT_OFF]:
            return False
        return True

    def _shift_count(self, day, shift):
        return sum(1 for n in self.names if self.schedule[n][day] == shift)

    def _min_req(self, day, shift):
        return int(self.manpower[day].get(f"{shift}_min", 0) or 0)

    def _max_req(self, day, shift):
        return int(self.manpower[day].get(f"{shift}_max", 999) or 999)

    # ============================================================
    # 固定項目：R / M / 預排班
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
                    if self._permission_ok(nurse, req):
                        self.schedule[nurse][day] = req
                        self.locked[nurse][day] = True

    # ============================================================
    # 半職：郭珍君等，只排 D，目標 10 天
    # ============================================================
    def _assign_parttime(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue

            # 先取消非固定、超額的半職 D，避免舊流程造成 18 天 D。
            self._trim_parttime_to_target(nurse)

            current = sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT)
            target = PARTTIME_DAYS - current
            if target <= 0:
                continue

            blocks = [3, 3, 2, 2]
            self.random.shuffle(blocks)

            for block_len in blocks:
                if target <= 0:
                    break
                length = min(block_len, target)
                starts = list(range(0, self.days - length + 1))
                self.random.shuffle(starts)
                starts.sort(key=lambda s: self._parttime_block_score(nurse, s, length), reverse=True)

                placed = False
                for start in starts:
                    if self._can_place_parttime_block(nurse, start, length):
                        for d in range(start, start + length):
                            self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                            self.locked[nurse][d] = True
                        target -= length
                        placed = True
                        break
                if not placed:
                    continue

            # 如果 3+3+2+2 無法完全放入，再用 D 補，但仍鎖住且不參與後續補班。
            for d in range(self.days):
                if target <= 0:
                    break
                if self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                    self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                    self.locked[nurse][d] = True
                    target -= 1

            self._trim_parttime_to_target(nurse)

    def _can_place_parttime_block(self, nurse, start, length):
        # 避免跟既有 D 相鄰，減少碎班與超長連班。
        if start > 0 and self.schedule[nurse][start - 1] == PARTTIME_ALLOWED_SHIFT:
            return False
        if start + length < self.days and self.schedule[nurse][start + length] == PARTTIME_ALLOWED_SHIFT:
            return False
        for d in range(start, start + length):
            if not self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                return False
        return True

    def _parttime_block_score(self, nurse, start, length):
        score = 0
        for d in range(start, start + length):
            if self._shift_count(d, SHIFT_D) < self._min_req(d, SHIFT_D):
                score += 20
            if self._shift_count(d, SHIFT_D) < self._max_req(d, SHIFT_D):
                score += 2
        return score + self.random.random()

    def _trim_parttime_to_target(self, nurse=None):
        nurses = [nurse] if nurse else [n for n in PART_TIME if n in self.names]
        for n in nurses:
            while sum(1 for x in self.schedule[n] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                removed = False
                for d in reversed(range(self.days)):
                    if self.schedule[n][d] == PARTTIME_ALLOWED_SHIFT and self._req(n, d) == "":
                        self.schedule[n][d] = ""
                        self.locked[n][d] = False
                        removed = True
                        break
                if not removed:
                    break

    # ============================================================
    # 大夜：只用 N,N,off,off 區塊
    # ============================================================
    def _assign_night_blocks(self):
        """重寫：全月規劃大夜，只允許 N,N,off,off 區塊。"""
        full_time = [n for n in self.names if self._is_fulltime(n) and self._permission_ok(n, SHIFT_N)]
        if not full_time:
            return
        for _ in range(self.days * max(1, len(full_time))):
            shortage_days = [d for d in range(self.days) if self._shift_count(d, SHIFT_N) < self._min_req(d, SHIFT_N)]
            if not shortage_days:
                break
            shortage_days.sort(key=lambda d: (self._shift_count(d, SHIFT_N) - self._min_req(d, SHIFT_N), d))
            placed = False
            for target_day in shortage_days:
                if self._place_best_night_block_covering(target_day):
                    placed = True
                    break
            if not placed:
                break

    def _place_best_night_block_covering(self, target_day):
        options = []
        for start in [target_day - 1, target_day]:
            if start < 0 or start + 1 >= self.days:
                continue
            for nurse in self.names:
                if self._is_parttime(nurse):
                    continue
                if self._can_place_night_block(nurse, start):
                    options.append((self._night_block_score(nurse, start), nurse, start))
        if not options:
            return False
        self.random.shuffle(options)
        options.sort(key=lambda x: x[0], reverse=True)
        _, nurse, start = options[0]
        self._place_night_block(nurse, start)
        return True

    def _night_block_score(self, nurse, start_day):
        score = 0.0
        for d in [start_day, start_day + 1]:
            if d < self.days:
                score += max(0, self._min_req(d, SHIFT_N) - self._shift_count(d, SHIFT_N)) * 100
                if self._shift_count(d, SHIFT_N) < self._max_req(d, SHIFT_N):
                    score += 10
        score -= self._night_count(nurse) * 25
        score -= self._workload(nurse) * 2
        if self._off_count(nurse) < MIN_FULLTIME_OFF_DAYS:
            score -= 5
        if start_day == 0 and self.history_shift.get(nurse) == SHIFT_N:
            score += 20
        return score + self.random.random()

    def _night_cell_can_be_used(self, nurse, day):
        """N 區塊專用：已固定為 N 的格子可視為可用；其他格子才需一般指派檢查。"""
        if day < 0 or day >= self.days:
            return False
        cur = self.schedule[nurse][day]
        if cur == SHIFT_N:
            return True
        if self.locked[nurse][day]:
            return False
        if cur not in ["", SHIFT_OFF]:
            return False
        if self._req(nurse, day) == SHIFT_R:
            return False
        if not self._permission_ok(nurse, SHIFT_N):
            return False
        if not self._request_allows(nurse, day, SHIFT_N):
            return False
        return True

    def _can_place_night_block(self, nurse, start_day):
        """允許把已固定/預排的單顆 N 補成 N,N,off,off。"""
        if start_day < 0 or start_day + 1 >= self.days:
            return False
        if self._is_parttime(nurse) or not self._permission_ok(nurse, SHIFT_N):
            return False

        # 兩天 N：若該格已經是 N 可沿用；若不是 N 則不可超過 N_max。
        for d in [start_day, start_day + 1]:
            if not self._night_cell_can_be_used(nurse, d):
                return False
            if self.schedule[nurse][d] != SHIFT_N and self._shift_count(d, SHIFT_N) >= self._max_req(d, SHIFT_N):
                return False

        # N 前一天不可是 D/E；N,N 後兩天必須能變成休假。
        prev = self._prev(nurse, start_day)
        if prev in [SHIFT_D, SHIFT_E]:
            return False
        for d in [start_day + 2, start_day + 3]:
            if d >= self.days:
                continue
            if self.locked[nurse][d]:
                return False
            if self._req(nurse, d) not in ["", SHIFT_OFF]:
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False
        return True

    def _place_night_block(self, nurse, start_day):
        for d in [start_day, start_day + 1]:
            if d < self.days:
                self.schedule[nurse][d] = SHIFT_N
                self.locked[nurse][d] = True
        for d in [start_day + 2, start_day + 3]:
            if d < self.days:
                self.schedule[nurse][d] = SHIFT_OFF
                self.locked[nurse][d] = True

    def _repair_night_blocks(self):
        """修復單顆 N；先嘗試補成完整區塊，不能補且人力不缺才移除。"""
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
                if left_n or right_n:
                    day += 1
                    continue
                # 單顆 N：優先向前/向後補成 N,N,off,off。
                fixed = False
                for start in [day, day - 1]:
                    if self._can_place_night_block(nurse, start):
                        self._place_night_block(nurse, start)
                        fixed = True
                        break
                if not fixed and not self.locked[nurse][day] and self._shift_count(day, SHIFT_N) > self._min_req(day, SHIFT_N):
                    self.schedule[nurse][day] = SHIFT_OFF
                day += 1

    # ============================================================
    # D/E 補班
    # ============================================================
    def _assign_shift_by_need(self, shift):
        """重寫：依每日 min 補 D/E；候選排序兼顧人力、白班/小夜平均、工作量平均。"""
        if shift == SHIFT_N:
            self._assign_night_blocks()
            return
        for day in range(self.days):
            guard = 0
            while self._shift_count(day, shift) < self._min_req(day, shift):
                guard += 1
                if guard > len(self.names) * 3:
                    break
                candidates = self._clinical_candidates(day, shift)
                if not candidates:
                    break
                self.schedule[candidates[0]][day] = shift

    def _clinical_candidates(self, day, shift):
        candidates = []
        for nurse in self.names:
            if self._is_parttime(nurse):
                continue
            if self._can_assign(nurse, day, shift, allow_overwrite_off=True):
                candidates.append(nurse)
        self.random.shuffle(candidates)
        candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
        return candidates

    def _candidate_score(self, nurse, day, shift):
        score = 0.0
        score += max(0, self._min_req(day, shift) - self._shift_count(day, shift)) * 100
        if self._prev(nurse, day) == shift:
            score += 18
        if self._next(nurse, day) == shift:
            score += 14
        if self._prev(nurse, day) in WORK_SHIFTS:
            score += 4
        if self._next(nurse, day) in WORK_SHIFTS:
            score += 3
        score -= sum(1 for x in self.schedule[nurse] if x == shift) * 8
        score -= self._workload(nurse) * 3
        score -= self._night_count(nurse)
        if self._is_fulltime(nurse) and self._off_count(nurse) < MIN_FULLTIME_OFF_DAYS:
            score -= 30
        return score + self.random.random()

    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    self.schedule[nurse][day] = SHIFT_R if self._req(nurse, day) == SHIFT_R else SHIFT_OFF

    # ============================================================
    # 修復與平衡
    # ============================================================
    def _repair_manpower_shortage(self):
        """重寫：人力達標優先；N 只能用 N,N,off,off，D/E 可用 off 人員補。"""
        for _ in range(10):
            changed = False
            for day in range(self.days):
                while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N):
                    if self._place_best_night_block_covering(day):
                        changed = True
                    else:
                        break
                for shift in [SHIFT_E, SHIFT_D]:
                    while self._shift_count(day, shift) < self._min_req(day, shift):
                        candidates = self._clinical_candidates(day, shift)
                        if candidates:
                            self.schedule[candidates[0]][day] = shift
                            changed = True
                            continue
                        rescue = self._rescue_candidate(day, shift)
                        if rescue:
                            self.schedule[rescue][day] = shift
                            changed = True
                            continue
                        break
            if not changed:
                break

    def _rescue_candidate(self, day, shift):
        candidates = []
        for nurse in self.names:
            if self._is_parttime(nurse):
                continue
            if self.locked[nurse][day]:
                continue
            if self.schedule[nurse][day] not in ["", SHIFT_OFF]:
                continue
            if self._req(nurse, day) not in ["", SHIFT_OFF]:
                continue
            if not self._permission_ok(nurse, shift):
                continue
            if not self._transition_ok(nurse, day, shift):
                continue
            if not self._max_streak_ok(nurse, day, shift):
                continue
            candidates.append(nurse)
        self.random.shuffle(candidates)
        candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
        return candidates[0] if candidates else None

    def _balance_holidays(self):
        """重寫：補足全職至少 8 天休，並檢查每 7 天至少 1 天休；不得讓人力低於最低。"""
        full_time = [n for n in self.names if self._is_fulltime(n)]
        if not full_time:
            return
        for _ in range(40):
            changed = False
            off_counts = {n: sum(1 for x in self.schedule[n] if x in REST_SHIFTS) for n in full_time}
            for nurse in sorted(full_time, key=lambda n: off_counts[n]):
                for start in range(0, self.days, 7):
                    end = min(start + 7, self.days)
                    block = self.schedule[nurse][start:end]
                    if len(block) < 5 or any(x in REST_SHIFTS for x in block):
                        continue
                    if self._create_holiday_in_range(nurse, start, end, off_counts):
                        changed = True
                        break
                if changed:
                    break
            if changed:
                continue
            under = [n for n in full_time if off_counts[n] < MIN_FULLTIME_OFF_DAYS]
            if not under:
                break
            under.sort(key=lambda n: off_counts[n])
            for nurse in under:
                if self._create_holiday_in_range(nurse, 0, self.days, off_counts):
                    changed = True
                    break
            if not changed:
                break

    def _create_holiday_in_range(self, nurse, start, end, off_counts):
        for day in self._days_sorted_for_holiday(nurse, start, end):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_set_off(nurse, day):
                continue
            if self._shift_count(day, shift) > self._min_req(day, shift):
                self.schedule[nurse][day] = SHIFT_OFF
                return True
        full_time = [n for n in self.names if self._is_fulltime(n)]
        for day in self._days_sorted_for_holiday(nurse, start, end):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_set_off(nurse, day):
                continue
            helpers = []
            for helper in full_time:
                if helper == nurse:
                    continue
                if off_counts.get(helper, 0) <= TARGET_FULLTIME_OFF_DAYS:
                    continue
                if self._can_assign(helper, day, shift, allow_overwrite_off=True):
                    helpers.append(helper)
            if helpers:
                self.random.shuffle(helpers)
                helpers.sort(key=lambda h: (-off_counts[h], self._workload(h)))
                helper = helpers[0]
                self.schedule[nurse][day] = SHIFT_OFF
                self.schedule[helper][day] = shift
                return True
        return False

    def _days_sorted_for_holiday(self, nurse, start=0, end=None):
        end = self.days if end is None else end
        days = list(range(start, end))
        self.random.shuffle(days)
        # 優先挑不會造成缺人、且左右接近休假的日子。
        def score(day):
            shift = self.schedule[nurse][day]
            s = 0
            if shift in [SHIFT_D, SHIFT_E] and self._shift_count(day, shift) > self._min_req(day, shift):
                s += 20
            if day > 0 and self.schedule[nurse][day - 1] in REST_SHIFTS:
                s += 4
            if day < self.days - 1 and self.schedule[nurse][day + 1] in REST_SHIFTS:
                s += 4
            return s
        days.sort(key=score, reverse=True)
        return days

    def _remove_single_day_fragments(self):
        full_time = [n for n in self.names if self._is_fulltime(n)]
        for _ in range(20):
            changed = False
            for nurse in full_time:
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E]:
                        continue
                    if self.locked[nurse][day]:
                        continue
                    left_rest = day == 0 or self.schedule[nurse][day - 1] in REST_SHIFTS
                    right_rest = day == self.days - 1 or self.schedule[nurse][day + 1] in REST_SHIFTS
                    if not (left_rest and right_rest):
                        continue

                    # 先嘗試往後或往前延伸，形成 2 天以上連班。
                    extended = False
                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                            if self._shift_count(nd, cur) < self._max_req(nd, cur):
                                self.schedule[nurse][nd] = cur
                                changed = True
                                extended = True
                                break
                    if extended:
                        continue

                    # 若無法延伸，且人力高於最低值，才取消成 off。
                    if self._can_set_off(nurse, day) and self._shift_count(day, cur) > self._min_req(day, cur):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = True
            if not changed:
                break


def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
    return scheduler.generate()
