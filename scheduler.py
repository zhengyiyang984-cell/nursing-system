"""
scheduler.py - 2F 護理排班系統 V8 Stable

保留原 API：
    build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None)

設計重點：
1. 固定 R / M / 預排 D/E/N 不被後續流程覆蓋。
2. 郭珍君等半職只排 D，目標 10 天。
3. 大夜盡量使用 N,N,off,off 區塊。
4. 只使用最低人力 D_min / E_min / N_min，不使用最大人力。
5. 所有 while / 修復流程都有 guard，避免 Streamlit 卡住。
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
        self._assign_night_blocks()
        self._repair_manpower_shortage(max_rounds=2)
        self._assign_shift_by_need(SHIFT_E)
        self._assign_shift_by_need(SHIFT_D)
        self._fill_blank_with_off()

        for _ in range(4):
            before = self._snapshot()
            self._repair_manpower_shortage(max_rounds=1)
            self._repair_long_streaks()
            self._balance_holidays()
            self._repair_manpower_shortage(max_rounds=1)
            self._remove_single_day_fragments()
            self._repair_night_blocks()
            self._fill_blank_with_off()
            if before == self._snapshot():
                break

        self._repair_manpower_shortage(max_rounds=2)
        self._repair_long_streaks()
        self._balance_holidays()
        self._repair_manpower_shortage(max_rounds=1)
        self._trim_parttime_to_target()
        self._fill_blank_with_off()

        # 最後收尾：專門修 E→D 與一日碎班，不改 app.py 的介面。
        self._final_repair(max_rounds=6)
        self._repair_long_streaks()
        self._balance_holidays()
        self._repair_manpower_shortage(max_rounds=1)
        self._restore_locked_requests()
        self._hospital_force_manpower()
        self._fill_blank_with_off()
        return self.schedule

    def _restore_locked_requests(self):
        """最後保險：還原所有預排 D/E/N/M/R。"""
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
                    self.schedule[nurse][day] = req
                    self.locked[nurse][day] = True


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

    def _night_count(self, nurse):
        return self._shift_workload(nurse, SHIFT_N)

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

    def _request_allows(self, nurse, day, shift):
        req = self._req(nurse, day)
        if req == SHIFT_R:
            return False
        if req in CLINICAL_SHIFTS or req == SHIFT_M:
            return req == shift
        return True

    def _is_fixed_cell(self, nurse, day):
        return self.locked[nurse][day]

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

    def _can_assign(self, nurse, day, shift, allow_overwrite_off=False):
        if day < 0 or day >= self.days:
            return False

        # 預排 D/E/N/M/R 是人工指定，不能被後續流程覆蓋。
        req = self._req(nurse, day)
        if req == SHIFT_R or req == SHIFT_M or req in CLINICAL_SHIFTS:
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
        if not self._max_streak_ok(nurse, day, shift):
            return False
        return True

    def _can_set_off(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self.locked[nurse][day] or self.night_locked[nurse][day]:
            return False
        if self._req(nurse, day) not in ["", SHIFT_OFF]:
            return False
        return True

    def _day_has_surplus(self, day, shift):
        return self._shift_count(day, shift) > self._min_req(day, shift)

    # ============================================================
    # 固定項目
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
                    self.schedule[nurse][day] = req
                    self.locked[nurse][day] = True

    # ============================================================
    # 半職
    # ============================================================
    def _assign_parttime(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue
            self._clear_unlocked_parttime(nurse)
            current = sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT)
            remaining = max(0, PARTTIME_DAYS - current)
            blocks = [3, 3, 2, 2]
            self.random.shuffle(blocks)
            for block_len in blocks:
                if remaining <= 0:
                    break
                length = min(block_len, remaining)
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
            for day in range(self.days):
                if remaining <= 0:
                    break
                if self._can_assign(nurse, day, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                    self.schedule[nurse][day] = PARTTIME_ALLOWED_SHIFT
                    self.locked[nurse][day] = True
                    remaining -= 1
            self._trim_parttime_to_target(nurse)

    def _clear_unlocked_parttime(self, nurse):
        for day in range(self.days):
            if not self.locked[nurse][day] and self.schedule[nurse][day] == PARTTIME_ALLOWED_SHIFT:
                self.schedule[nurse][day] = ""

    def _can_place_parttime_block(self, nurse, start, length):
        if start < 0 or start + length > self.days:
            return False
        if start > 0 and self.schedule[nurse][start - 1] == PARTTIME_ALLOWED_SHIFT:
            return False
        if start + length < self.days and self.schedule[nurse][start + length] == PARTTIME_ALLOWED_SHIFT:
            return False
        for day in range(start, start + length):
            if not self._can_assign(nurse, day, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                return False
        return True

    def _parttime_block_score(self, nurse, start, length):
        score = 0.0
        for day in range(start, start + length):
            if self._shift_count(day, SHIFT_D) < self._min_req(day, SHIFT_D):
                score += 30
            if day > 0 and self.schedule[nurse][day - 1] == SHIFT_OFF:
                score += 1
            if day + 1 < self.days and self.schedule[nurse][day + 1] == SHIFT_OFF:
                score += 1
        return score + self.random.random()

    def _trim_parttime_to_target(self, nurse=None):
        nurses = [nurse] if nurse else [n for n in PART_TIME if n in self.names]
        for n in nurses:
            while sum(1 for x in self.schedule[n] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                removed = False
                for day in reversed(range(self.days)):
                    if self.schedule[n][day] == PARTTIME_ALLOWED_SHIFT and not self.locked[n][day]:
                        self.schedule[n][day] = SHIFT_OFF
                        removed = True
                        break
                if not removed:
                    break

    # ============================================================
    # 夜班 N,N,off,off
    # ============================================================
    def _assign_night_blocks(self):
        attempts = max(1, self.days * max(1, len(self.names)) * 2)
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
            if not placed:
                break

    def _place_best_night_block_covering(self, target_day):
        options = []
        for start in [target_day - 1, target_day]:
            if start < 0 or start + 1 >= self.days:
                continue
            for nurse in self.names:
                if self._can_place_night_block(nurse, start):
                    options.append((self._night_block_score(nurse, start), nurse, start))
        if not options:
            return False
        self.random.shuffle(options)
        options.sort(key=lambda x: x[0], reverse=True)
        _, nurse, start = options[0]
        self._place_night_block(nurse, start)
        return True

    def _night_block_score(self, nurse, start):
        score = 0.0
        for day in [start, start + 1]:
            score += max(0, self._min_req(day, SHIFT_N) - self._shift_count(day, SHIFT_N)) * 100
        score -= self._night_count(nurse) * 20
        score -= self._workload(nurse) * 2
        if start == 0 and self.history_shift.get(nurse) == SHIFT_N:
            score += 20
        return score + self.random.random()

    def _night_cell_can_be_used(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self._is_parttime(nurse) or not self._permission_ok(nurse, SHIFT_N):
            return False
        cur = self.schedule[nurse][day]
        if cur == SHIFT_N:
            return True
        if self.locked[nurse][day] or self.night_locked[nurse][day]:
            return False
        if cur not in ["", SHIFT_OFF]:
            return False
        if self._req(nurse, day) == SHIFT_R:
            return False
        return self._request_allows(nurse, day, SHIFT_N)

    def _can_place_night_block(self, nurse, start):
        if start < 0 or start + 1 >= self.days:
            return False
        if self._is_parttime(nurse) or not self._permission_ok(nurse, SHIFT_N):
            return False
        prev_shift = self._prev(nurse, start)
        if prev_shift in [SHIFT_D, SHIFT_E, SHIFT_M]:
            return False
        for day in [start, start + 1]:
            if not self._night_cell_can_be_used(nurse, day):
                return False
        for day in [start + 2, start + 3]:
            if day >= self.days:
                continue
            if self.locked[nurse][day] or self.night_locked[nurse][day]:
                return False
            if self._req(nurse, day) not in ["", SHIFT_OFF]:
                return False
            if self.schedule[nurse][day] not in ["", SHIFT_OFF]:
                return False
        return True

    def _place_night_block(self, nurse, start):
        for day in [start, start + 1]:
            if 0 <= day < self.days:
                self.schedule[nurse][day] = SHIFT_N
                self.night_locked[nurse][day] = True

        for day in [start + 2, start + 3]:
            if 0 <= day < self.days:
                if self.schedule[nurse][day] == SHIFT_R or self._req(nurse, day) == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                    self.locked[nurse][day] = True
                    continue
                self.schedule[nurse][day] = SHIFT_OFF
                self.night_locked[nurse][day] = True

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
                if left_n or right_n:
                    day += 1
                    continue
                fixed = False
                for start in [day - 1, day]:
                    if self._can_place_night_block(nurse, start):
                        self._place_night_block(nurse, start)
                        fixed = True
                        break
                if not fixed and not self.locked[nurse][day] and self._day_has_surplus(day, SHIFT_N):
                    self.schedule[nurse][day] = SHIFT_OFF
                    self.night_locked[nurse][day] = False
                day += 1

    # ============================================================
    # D / E 補班
    # ============================================================
    def _assign_shift_by_need(self, shift):
        if shift == SHIFT_N:
            self._assign_night_blocks()
            return
        for day in range(self.days):
            guard = 0
            while self._shift_count(day, shift) < self._min_req(day, shift):
                guard += 1
                if guard > len(self.names) * 2:
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
            score += 15
        if self._next(nurse, day) == shift:
            score += 10
        if self._prev(nurse, day) in WORK_SHIFTS:
            score += 3
        if self._next(nurse, day) in WORK_SHIFTS:
            score += 2
        score -= self._shift_workload(nurse, shift) * 8
        score -= self._workload(nurse) * 3
        if self._off_count(nurse) < MIN_FULLTIME_OFF_DAYS:
            score -= 25
        return score + self.random.random()

    def _rescue_candidate(self, day, shift):
        candidates = []
        for nurse in self.names:
            if self._is_parttime(nurse):
                continue
            if self.locked[nurse][day] or self.night_locked[nurse][day]:
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

    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    self.schedule[nurse][day] = SHIFT_R if self._req(nurse, day) == SHIFT_R else SHIFT_OFF

    # ============================================================
    # 修復器
    # ============================================================
    def _repair_manpower_shortage(self, max_rounds=2):
        for _ in range(max_rounds):
            changed = False
            for day in range(self.days):
                guard = 0
                while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N):
                    guard += 1
                    if guard > len(self.names):
                        break
                    if self._place_best_night_block_covering(day):
                        changed = True
                    else:
                        break

                for shift in [SHIFT_E, SHIFT_D]:
                    guard = 0
                    while self._shift_count(day, shift) < self._min_req(day, shift):
                        guard += 1
                        if guard > len(self.names):
                            break
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


    def _hospital_force_manpower(self, max_rounds=4):
        """醫院模式：最低人力優先，最後一定盡量補滿 D/E/N。"""
        for _ in range(max_rounds):
            changed = False
            self._restore_locked_requests()

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

    def _force_fill_shift(self, day, shift):
        """最後手段補足單日最低人力。

        只從空白/off 且非預排、非夜班鎖定者補人；不覆蓋 D/E/N/M/R 預排。
        權限仍會檢查。若規則太緊，會放寬連班限制，但不放寬預排鎖定。
        """
        candidates = []

        for nurse in self.names:
            if self._is_parttime(nurse) and shift != PARTTIME_ALLOWED_SHIFT:
                continue
            if self.locked[nurse][day] or self.night_locked[nurse][day]:
                continue
            if self._req(nurse, day) not in ["", SHIFT_OFF]:
                continue
            if self.schedule[nurse][day] not in ["", SHIFT_OFF]:
                continue
            if not self._permission_ok(nurse, shift):
                continue
            if not self._transition_ok(nurse, day, shift):
                continue

            # 第一順位：正常連班限制內。
            if self._max_streak_ok(nurse, day, shift):
                priority = 0
            else:
                # 第二順位：為了補足最低人力，允許暫時超過連班，之後再修。
                priority = 1

            candidates.append((
                priority,
                self._workload(nurse),
                self._shift_workload(nurse, shift),
                self.random.random(),
                nurse,
            ))

        if not candidates:
            return False

        candidates.sort()
        nurse = candidates[0][-1]
        self.schedule[nurse][day] = shift
        return True


    def _repair_long_streaks(self):
        """修正最長連班超過上限。

        優先在連班中段把 D/E 改 off；若該日人力剛好等於最低需求，
        會先找 off 的同仁接班，再讓原護理師休假。
        不動預排、R/M、夜班區塊與半職。
        """
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

                    helper = self._find_helper_for_shift(nurse, day, shift)
                    if helper is not None:
                        self.schedule[helper][day] = shift
                        self.schedule[nurse][day] = SHIFT_OFF
                        fixed = True
                        break

                if not fixed:
                    for day in days:
                        shift = self.schedule[nurse][day]
                        if shift not in [SHIFT_D, SHIFT_E]:
                            continue
                        if self._swap_to_make_off(nurse, day, shift):
                            fixed = True
                            break

                if not fixed:
                    break

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
                if cur_start is not None:
                    end = day - 1
                    if best is None or cur_len > best[2]:
                        best = (cur_start, end, cur_len)
                cur_start = None
                cur_len = 0
        if cur_start is not None:
            best = max(best or (cur_start, self.days - 1, cur_len), (cur_start, self.days - 1, cur_len), key=lambda x: x[2])
        return best

    def _balance_holidays(self):
        full_time = [n for n in self.names if self._is_fulltime(n)]
        for _ in range(20):
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
                if self._force_make_holiday(nurse):
                    changed = True
                    break
            if not changed:
                break

    def _create_holiday(self, nurse, start, end, off_counts):
        for day in self._holiday_candidate_days(nurse, start, end):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if self._can_set_off(nurse, day) and self._day_has_surplus(day, shift):
                self.schedule[nurse][day] = SHIFT_OFF
                return True
        for day in self._holiday_candidate_days(nurse, start, end):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
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
            if self.locked[helper][day] or self.night_locked[helper][day]:
                continue
            if self._can_assign(helper, day, shift, allow_overwrite_off=True):
                helpers.append(helper)
        if not helpers:
            return False
        self.random.shuffle(helpers)
        helpers.sort(key=lambda h: (self._workload(h), self._shift_workload(h, shift)))
        helper = helpers[0]
        self.schedule[nurse][day] = SHIFT_OFF
        self.schedule[helper][day] = shift
        return True

    def _force_make_holiday(self, nurse):
        for day in self._holiday_candidate_days(nurse, 0, self.days):
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_set_off(nurse, day):
                continue
            helper = self._find_helper_for_shift(nurse, day, shift)
            if helper is None:
                continue
            self.schedule[helper][day] = shift
            self.schedule[nurse][day] = SHIFT_OFF
            return True
        return False

    def _remove_single_day_fragments(self):
        for _ in range(8):
            changed = False
            for nurse in self.names:
                if not self._is_fulltime(nurse):
                    continue
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E] or self.locked[nurse][day] or self.night_locked[nurse][day]:
                        continue
                    left_rest = day == 0 or self.schedule[nurse][day - 1] in REST_SHIFTS
                    right_rest = day == self.days - 1 or self.schedule[nurse][day + 1] in REST_SHIFTS
                    if not (left_rest and right_rest):
                        continue
                    extended = False
                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                            self.schedule[nurse][nd] = cur
                            changed = True
                            extended = True
                            break
                    if extended:
                        continue
                    if self._can_set_off(nurse, day) and self._day_has_surplus(day, cur):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = True
            if not changed:
                break


    # ============================================================
    # Final Repair：最後只修 E→D 與一日碎班
    # ============================================================
    def _final_repair(self, max_rounds=3):
        """
        最後收尾修復：
        1. 修 E→D 銜接違規。
        2. 再跑一日碎班修復。
        3. 修完後補最低人力，避免修復造成缺人。
        有 guard，不會讓 Streamlit 卡住。
        """
        for _ in range(max_rounds):
            before = self._snapshot()

            self._repair_e_to_d_transitions()
            self._remove_single_day_fragments()
            self._repair_long_streaks()
            self._repair_manpower_shortage(max_rounds=1)
            self._balance_holidays()
            self._repair_long_streaks()
            self._repair_manpower_shortage(max_rounds=1)
            self._repair_e_to_d_transitions()
            self._fill_blank_with_off()

            if before == self._snapshot():
                break

    def _can_change_existing_shift(self, nurse, day, new_shift):
        """
        檢查已排好的 D/E 是否可改成另一個 D/E/off。
        不動預排、R/M、夜班區塊與半職。
        """
        if day < 0 or day >= self.days:
            return False
        if self._is_parttime(nurse):
            return False
        if self.locked[nurse][day] or self.night_locked[nurse][day]:
            return False

        old_shift = self.schedule[nurse][day]
        if old_shift not in [SHIFT_D, SHIFT_E, SHIFT_OFF, ""]:
            return False

        if new_shift == SHIFT_OFF:
            return self._can_set_off(nurse, day)

        if new_shift not in [SHIFT_D, SHIFT_E]:
            return False
        if not self._permission_ok(nurse, new_shift):
            return False
        if not self._request_allows(nurse, day, new_shift):
            return False

        original = self.schedule[nurse][day]
        self.schedule[nurse][day] = SHIFT_OFF
        ok = (
            self._transition_ok(nurse, day, new_shift)
            and self._max_streak_ok(nurse, day, new_shift)
        )
        self.schedule[nurse][day] = original
        return ok

    def _find_helper_for_shift(self, avoid_nurse, day, shift):
        """找一位 off 的全職同仁補上指定班別，避免修正後低於最低人力。"""
        helpers = []
        for helper in self.names:
            if helper == avoid_nurse or self._is_parttime(helper):
                continue
            if self.schedule[helper][day] != SHIFT_OFF:
                continue
            if self.locked[helper][day] or self.night_locked[helper][day]:
                continue
            if self._can_assign(helper, day, shift, allow_overwrite_off=True):
                helpers.append(helper)

        self.random.shuffle(helpers)
        helpers.sort(key=lambda h: (self._workload(h), self._shift_workload(h, shift)))
        return helpers[0] if helpers else None

    def _repair_e_to_d_transitions(self):
        """
        修正 E 後接 D：
        優先把 D 改成 E；若會造成 D 缺人，就找 helper 補 D。
        不行時，才嘗試把 D 改 off，或把前一天 E 改 off。
        """
        changed = False

        for nurse in self.names:
            if not self._is_fulltime(nurse):
                continue

            for day in range(1, self.days):
                if self.schedule[nurse][day - 1] != SHIFT_E:
                    continue
                if self.schedule[nurse][day] != SHIFT_D:
                    continue

                # A. D 改成 E；若 D 不足，找 helper 補 D。
                if self._can_change_existing_shift(nurse, day, SHIFT_E):
                    if self._day_has_surplus(day, SHIFT_D):
                        self.schedule[nurse][day] = SHIFT_E
                        changed = True
                        continue

                    helper = self._find_helper_for_shift(nurse, day, SHIFT_D)
                    if helper:
                        self.schedule[nurse][day] = SHIFT_E
                        self.schedule[helper][day] = SHIFT_D
                        changed = True
                        continue

                # B. D 改 off；只在人力仍足夠時做。
                if self._day_has_surplus(day, SHIFT_D) and self._can_change_existing_shift(nurse, day, SHIFT_OFF):
                    self.schedule[nurse][day] = SHIFT_OFF
                    changed = True
                    continue

                # C. 前一天 E 改 off；只在人力仍足夠時做。
                prev_day = day - 1
                if (
                    self._day_has_surplus(prev_day, SHIFT_E)
                    and self._can_change_existing_shift(nurse, prev_day, SHIFT_OFF)
                ):
                    self.schedule[nurse][prev_day] = SHIFT_OFF
                    changed = True
                    continue

                # D. 前一天 E 改 D；只在 E 有餘裕時做。
                if (
                    self._day_has_surplus(prev_day, SHIFT_E)
                    and self._can_change_existing_shift(nurse, prev_day, SHIFT_D)
                ):
                    self.schedule[nurse][prev_day] = SHIFT_D
                    changed = True
                    continue

        return changed



def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
    return scheduler.generate()
