"""
scheduler.py - 2F 護理排班核心 V4

設計重點：
1. 兼職郭珍君只排 D，且盡量剛好 10 天。
2. 大夜只用 N -> N -> off -> off 區塊，不直接塞單顆 N。
3. D/E 補人力時不會抓兼職。
4. 全職休假 >= 8 天優先保底，但不破壞固定 R/M/預排臨床班。
5. E 後不可 D，N 後不可 D/E/M，最多連上 5 天。
"""

import random
from config import *


class NurseScheduler:
    def __init__(
        self,
        names,
        permissions,
        requests,
        manpower,
        history_shift,
        history_streak,
        seed=None,
    ):
        self.names = list(names)
        self.permissions = permissions or {}
        self.requests = requests or {}
        self.manpower = manpower or []
        self.history_shift = history_shift or {}
        self.history_streak = history_streak or {}
        self.days = len(self.manpower)
        self.random = random.Random(seed)
        self.schedule = {n: ["" for _ in range(self.days)] for n in self.names}

        for n in self.names:
            self.requests.setdefault(n, [""] * self.days)
            if len(self.requests[n]) < self.days:
                self.requests[n] = self.requests[n] + [""] * (self.days - len(self.requests[n]))

    # =========================================================
    # 主流程
    # =========================================================
    def generate(self):
        self._apply_requests()
        self._protect_history_night_rest()
        self._assign_parttime_exact_blocks()
        self._assign_night_blocks()
        self._assign_shift_by_need(SHIFT_E)
        self._assign_shift_by_need(SHIFT_D)
        self._fill_blank_with_off()

        for _ in range(8):
            changed = False
            changed |= self._repair_manpower_shortage()
            changed |= self._normalize_night_blocks()
            changed |= self._balance_holidays()
            changed |= self._remove_single_day_fragments()
            changed |= self._enforce_parttime_exact()
            self._fill_blank_with_off()
            if not changed:
                break

        self._final_cleanup()
        return self.schedule

    # =========================================================
    # 基礎工具
    # =========================================================
    def _is_full_time(self, nurse):
        return nurse not in PART_TIME

    def _is_fixed_request(self, nurse, day):
        req = self.requests[nurse][day]
        return req in [SHIFT_R, SHIFT_M] + CLINICAL_SHIFTS

    def _is_work(self, shift):
        return shift in WORK_SHIFTS

    def _is_rest(self, shift):
        return shift in REST_SHIFTS or shift == ""

    def _workload(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in WORK_SHIFTS)

    def _night_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x == SHIFT_N)

    def _off_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in REST_SHIFTS or x == "")

    def _shift_count(self, day, shift):
        return sum(1 for n in self.names if self.schedule[n][day] == shift)

    def _min_req(self, day, shift):
        return int(self.manpower[day].get(f"{shift}_min", 0))

    def _max_req(self, day, shift):
        return int(self.manpower[day].get(f"{shift}_max", 999))

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
        if shift not in CLINICAL_SHIFTS:
            return True
        if nurse in PART_TIME:
            return shift == PARTTIME_ALLOWED_SHIFT
        return shift in str(self.permissions.get(nurse, "DEN")).upper()

    def _request_allows(self, nurse, day, shift):
        req = self.requests[nurse][day]
        if req == SHIFT_R:
            return False
        if req in [SHIFT_M] + CLINICAL_SHIFTS:
            return req == shift
        return True

    def _is_history_night_rest_day(self, nurse, day):
        """若上月最後已經連兩天以上 N，月初前兩天保護休假。"""
        if self.history_shift.get(nurse) != SHIFT_N:
            return False
        streak = int(self.history_streak.get(nurse, 0) or 0)
        return streak >= 2 and day in [0, 1]

    def _transition_ok(self, nurse, day, shift):
        prev = self._prev(nurse, day)
        if (prev, shift) in FORBIDDEN_TRANSITIONS:
            return False
        if prev == SHIFT_N and shift not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
            return False
        if shift == SHIFT_E and day < self.days - 1:
            if self.schedule[nurse][day + 1] == SHIFT_D:
                return False
        return True

    def _max_streak_ok(self, nurse, day, shift):
        if shift not in WORK_SHIFTS:
            return True
        before = self._continuous_before(nurse, day)
        after = self._continuous_after(nurse, day)
        return before + 1 + after <= MAX_CONTINUOUS_WORK

    def _can_assign(self, nurse, day, shift, allow_overwrite_off=False):
        if day < 0 or day >= self.days:
            return False
        if self._is_history_night_rest_day(nurse, day) and shift in WORK_SHIFTS:
            return False
        cur = self.schedule[nurse][day]
        if cur not in ["", SHIFT_OFF]:
            return False
        if cur == SHIFT_OFF and not allow_overwrite_off:
            return False
        if self.requests[nurse][day] == SHIFT_R:
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

    def _can_turn_to_off(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self.requests[nurse][day] != "":
            return False
        return self.schedule[nurse][day] in CLINICAL_SHIFTS

    # =========================================================
    # 固定資料套用
    # =========================================================
    def _apply_requests(self):
        for nurse in self.names:
            for day in range(self.days):
                req = self.requests[nurse][day]
                if req == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                elif req == SHIFT_M:
                    self.schedule[nurse][day] = SHIFT_M
                elif req in CLINICAL_SHIFTS and self._permission_ok(nurse, req):
                    self.schedule[nurse][day] = req

    def _protect_history_night_rest(self):
        for nurse in self.names:
            if self.history_shift.get(nurse) == SHIFT_N and int(self.history_streak.get(nurse, 0) or 0) >= 2:
                for day in [0, 1]:
                    if day < self.days and self.schedule[nurse][day] == "" and self.requests[nurse][day] == "":
                        self.schedule[nurse][day] = SHIFT_OFF

    # =========================================================
    # 兼職：郭珍君固定 10 天 D，優先 3/3/2/2 區塊
    # =========================================================
    def _assign_parttime_exact_blocks(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue

            # 清掉非固定的兼職班，避免前一輪或補班造成超過 10 天
            for day in range(self.days):
                if self.requests[nurse][day] == "" and self.schedule[nurse][day] == PARTTIME_ALLOWED_SHIFT:
                    self.schedule[nurse][day] = ""

            fixed_d = sum(1 for d in range(self.days) if self.schedule[nurse][d] == PARTTIME_ALLOWED_SHIFT)
            target = max(0, PARTTIME_DAYS - fixed_d)
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
                    days = range(start, start + length)
                    if all(self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True) for d in days):
                        for d in days:
                            self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                        target -= length
                        placed = True
                        break
                if not placed:
                    continue

            # 若固定預排或不可排導致仍不足，才用連續性最佳的單日補足
            while target > 0:
                candidates = [d for d in range(self.days) if self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True)]
                if not candidates:
                    break
                candidates.sort(key=lambda d: self._parttime_single_score(nurse, d), reverse=True)
                self.schedule[nurse][candidates[0]] = PARTTIME_ALLOWED_SHIFT
                target -= 1

            self._enforce_parttime_exact()

    def _parttime_block_score(self, nurse, start, length):
        score = 0
        if start > 0 and self.schedule[nurse][start - 1] == PARTTIME_ALLOWED_SHIFT:
            score += 5
        if start + length < self.days and self.schedule[nurse][start + length] == PARTTIME_ALLOWED_SHIFT:
            score += 5
        for d in range(start, start + length):
            if self._shift_count(d, SHIFT_D) < self._min_req(d, SHIFT_D):
                score += 10
            if self.requests[nurse][d] in [SHIFT_R, SHIFT_M]:
                score -= 100
        return score

    def _parttime_single_score(self, nurse, day):
        score = 0
        if day > 0 and self.schedule[nurse][day - 1] == PARTTIME_ALLOWED_SHIFT:
            score += 8
        if day < self.days - 1 and self.schedule[nurse][day + 1] == PARTTIME_ALLOWED_SHIFT:
            score += 8
        if self._shift_count(day, SHIFT_D) < self._min_req(day, SHIFT_D):
            score += 10
        return score

    def _enforce_parttime_exact(self):
        changed = False
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue
            while sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                removable = [
                    d for d in range(self.days)
                    if self.schedule[nurse][d] == PARTTIME_ALLOWED_SHIFT and self.requests[nurse][d] == ""
                ]
                if not removable:
                    break
                # 優先移除不影響 D_min 的 D，且移除後較不形成碎班
                removable.sort(key=lambda d: (self._shift_count(d, SHIFT_D) > self._min_req(d, SHIFT_D), -self._parttime_single_score(nurse, d)), reverse=True)
                self.schedule[nurse][removable[0]] = SHIFT_OFF
                changed = True
        return changed

    # =========================================================
    # 大夜：只排 N,N,off,off
    # =========================================================
    def _assign_night_blocks(self):
        for day in range(self.days):
            guard = 0
            while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N) and guard < 30:
                guard += 1
                candidates = self._night_candidates(day)
                if not candidates:
                    break
                self._place_night_block(candidates[0], day)

    def _night_candidates(self, start_day):
        candidates = []
        for nurse in self.names:
            if nurse in PART_TIME:
                continue
            if self._can_place_night_block(nurse, start_day):
                candidates.append(nurse)
        self.random.shuffle(candidates)
        candidates.sort(key=lambda n: (self._night_count(n), self._workload(n), -self._off_count(n)))
        return candidates

    def _can_place_night_block(self, nurse, start_day):
        if start_day < 0 or start_day + 3 >= self.days:
            return False
        if start_day > 0 and self.schedule[nurse][start_day - 1] == SHIFT_N:
            return False
        if self.history_shift.get(nurse) == SHIFT_N and start_day == 0 and int(self.history_streak.get(nurse, 0) or 0) >= 2:
            return False

        # N, N
        for d in [start_day, start_day + 1]:
            if self._shift_count(d, SHIFT_N) >= self._max_req(d, SHIFT_N) and self.schedule[nurse][d] != SHIFT_N:
                return False
            if not self._can_assign(nurse, d, SHIFT_N, allow_overwrite_off=True):
                return False

        # off, off
        for d in [start_day + 2, start_day + 3]:
            if self.requests[nurse][d] not in ["", SHIFT_OFF]:
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False
        return True

    def _place_night_block(self, nurse, start_day):
        self.schedule[nurse][start_day] = SHIFT_N
        self.schedule[nurse][start_day + 1] = SHIFT_N
        self.schedule[nurse][start_day + 2] = SHIFT_OFF
        self.schedule[nurse][start_day + 3] = SHIFT_OFF

    def _normalize_night_blocks(self):
        """修復單顆 N 或 N 後未休兩天。無法修復時，移除非固定 N。"""
        changed = False
        for nurse in [n for n in self.names if n not in PART_TIME]:
            day = 0
            while day < self.days:
                if self.schedule[nurse][day] != SHIFT_N:
                    day += 1
                    continue

                ok = (
                    day + 3 < self.days
                    and self.schedule[nurse][day + 1] == SHIFT_N
                    and self.schedule[nurse][day + 2] == SHIFT_OFF
                    and self.schedule[nurse][day + 3] == SHIFT_OFF
                )
                if ok:
                    day += 4
                    continue

                # 嘗試把 day 當成 block 起點修復
                if day + 3 < self.days:
                    can_fix = True
                    for d, val in [(day + 1, SHIFT_N), (day + 2, SHIFT_OFF), (day + 3, SHIFT_OFF)]:
                        if self.requests[nurse][d] != "" and self.requests[nurse][d] != val:
                            can_fix = False
                        if self.schedule[nurse][d] not in ["", SHIFT_OFF, val]:
                            can_fix = False
                    if can_fix and self._permission_ok(nurse, SHIFT_N):
                        self.schedule[nurse][day + 1] = SHIFT_N
                        self.schedule[nurse][day + 2] = SHIFT_OFF
                        self.schedule[nurse][day + 3] = SHIFT_OFF
                        changed = True
                        day += 4
                        continue

                # 無法修，若不是固定預排 N，移除
                if self.requests[nurse][day] == "" and self._shift_count(day, SHIFT_N) > self._min_req(day, SHIFT_N):
                    self.schedule[nurse][day] = SHIFT_OFF
                    changed = True
                day += 1
        return changed

    # =========================================================
    # D / E 補班
    # =========================================================
    def _assign_shift_by_need(self, shift):
        if shift == SHIFT_N:
            self._assign_night_blocks()
            return
        for day in range(self.days):
            guard = 0
            while self._shift_count(day, shift) < self._min_req(day, shift) and guard < 30:
                guard += 1
                candidates = [
                    n for n in self.names
                    if n not in PART_TIME and self._can_assign(n, day, shift, allow_overwrite_off=True)
                ]
                if not candidates:
                    break
                self.random.shuffle(candidates)
                candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
                self.schedule[candidates[0]][day] = shift

    def _candidate_score(self, nurse, day, shift):
        score = 0.0
        if self._prev(nurse, day) == shift:
            score += 10
        if day < self.days - 1 and self.schedule[nurse][day + 1] == shift:
            score += 8
        if self._prev(nurse, day) in WORK_SHIFTS:
            score += 3
        if shift == SHIFT_E and self._prev(nurse, day) == SHIFT_D:
            score += 2
        score -= self._workload(nurse) * 1.2
        score -= sum(1 for x in self.schedule[nurse] if x == shift) * 1.5
        score += self._off_count(nurse) * 0.2
        score += self.random.random()
        return score

    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    self.schedule[nurse][day] = SHIFT_R if self.requests[nurse][day] == SHIFT_R else SHIFT_OFF

    # =========================================================
    # 修復：人力不足、休假不足、碎班
    # =========================================================
    def _repair_manpower_shortage(self):
        changed = False
        for day in range(self.days):
            # N 只用 night block 修，不直接塞單顆 N
            guard = 0
            while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N) and guard < 20:
                guard += 1
                candidates = self._night_candidates(day)
                if not candidates:
                    break
                self._place_night_block(candidates[0], day)
                changed = True

            for shift in [SHIFT_E, SHIFT_D]:
                guard = 0
                while self._shift_count(day, shift) < self._min_req(day, shift) and guard < 20:
                    guard += 1
                    candidates = [
                        n for n in self.names
                        if n not in PART_TIME and self._can_assign(n, day, shift, allow_overwrite_off=True)
                    ]
                    if not candidates:
                        break
                    self.random.shuffle(candidates)
                    candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
                    self.schedule[candidates[0]][day] = shift
                    changed = True
        return changed

    def _balance_holidays(self):
        changed = False
        full_time = [n for n in self.names if n not in PART_TIME]

        for _ in range(30):
            off_counts = {n: sum(1 for x in self.schedule[n] if x in REST_SHIFTS) for n in full_time}
            under = [n for n in full_time if off_counts[n] < MIN_FULLTIME_OFF_DAYS]
            if not under:
                break
            under.sort(key=lambda n: off_counts[n])
            moved = False

            for nurse in under:
                # A. 直接退掉多餘人力
                days = list(range(self.days))
                self.random.shuffle(days)
                days.sort(key=lambda d: self._shift_count(d, self.schedule[nurse][d]) - self._min_req(d, self.schedule[nurse][d]) if self.schedule[nurse][d] in CLINICAL_SHIFTS else -999, reverse=True)
                for day in days:
                    shift = self.schedule[nurse][day]
                    if shift not in CLINICAL_SHIFTS or not self._can_turn_to_off(nurse, day):
                        continue
                    if self._shift_count(day, shift) > self._min_req(day, shift):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = moved = True
                        break
                if moved:
                    break

                # B. 找休太多的人交換
                for day in range(self.days):
                    shift = self.schedule[nurse][day]
                    if shift not in [SHIFT_D, SHIFT_E] or not self._can_turn_to_off(nurse, day):
                        continue
                    helpers = [
                        h for h in full_time
                        if h != nurse
                        and off_counts.get(h, 0) > TARGET_FULLTIME_OFF_DAYS
                        and self._can_assign(h, day, shift, allow_overwrite_off=True)
                    ]
                    if helpers:
                        helpers.sort(key=lambda h: (-off_counts[h], self._workload(h)))
                        helper = helpers[0]
                        self.schedule[nurse][day] = SHIFT_OFF
                        self.schedule[helper][day] = shift
                        changed = moved = True
                        break
                if moved:
                    break

            if not moved:
                break

        return changed

    def _remove_single_day_fragments(self):
        changed = False
        full_time = [n for n in self.names if n not in PART_TIME]
        for _ in range(20):
            loop_changed = False
            for nurse in full_time:
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E]:
                        continue
                    left_rest = day == 0 or self.schedule[nurse][day - 1] in REST_SHIFTS
                    right_rest = day == self.days - 1 or self.schedule[nurse][day + 1] in REST_SHIFTS
                    if not (left_rest and right_rest):
                        continue

                    if self._can_turn_to_off(nurse, day) and self._shift_count(day, cur) > self._min_req(day, cur):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = loop_changed = True
                        continue

                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                            if self._shift_count(nd, cur) < self._max_req(nd, cur):
                                self.schedule[nurse][nd] = cur
                                changed = loop_changed = True
                                break
            if not loop_changed:
                break
        return changed

    def _final_cleanup(self):
        self._normalize_night_blocks()
        self._enforce_parttime_exact()
        self._fill_blank_with_off()


def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(
        names,
        permissions,
        requests,
        manpower,
        history_shift,
        history_streak,
        seed=seed,
    )
    return scheduler.generate()
