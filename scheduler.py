import random
import statistics
from copy import deepcopy
from config import *
from validator import validate_schedule


class NurseScheduler:
    def __init__(self, names, permissions, requests, manpower, history_shift, history_streak, seed=None):
        self.names = list(names)
        self.permissions = permissions
        self.requests = requests
        self.manpower = manpower
        self.history_shift = history_shift
        self.history_streak = history_streak
        self.days = len(manpower)
        self.random = random.Random(seed)
        self.schedule = {
            n: ["" for _ in range(self.days)]
            for n in self.names
        }

        self.night_locked = set()
        # 鎖定兼職由 _assign_parttime 排出的 D，避免後續補人力又把兼職排超過 10 天
        self.fixed_parttime_days = set()

    def generate(self):
        self._apply_requests()
        self._assign_parttime()
        self._assign_night_blocks()
        self._assign_shift_by_need(SHIFT_E)
        self._assign_shift_by_need(SHIFT_D)
        self._fill_blank_with_off()

        # 反覆修復：先補人力，再修 N 班、休假與碎班，最後再補人力
        for _ in range(3):
            self._repair_manpower_shortage()
            self._enforce_night_pattern()
            self._balance_holidays()
            self._remove_single_day_fragments()
            self._trim_parttime_extra_days()

        self._repair_manpower_shortage()
        self._enforce_night_pattern()
        self._trim_parttime_extra_days()
        self._repair_manpower_shortage()
        self._fill_blank_with_off()
        return self.schedule

    # ---------- 基礎工具 ----------
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
            return self.history_streak.get(nurse, 0)
        count = 0
        d = day - 1
        while d >= 0 and self.schedule[nurse][d] in WORK_SHIFTS:
            count += 1
            d -= 1
        return count

    def _permission_ok(self, nurse, shift):
        if nurse in PART_TIME:
            return shift == PARTTIME_ALLOWED_SHIFT
        return shift in self.permissions.get(nurse, "DEN")

    def _request_allows(self, nurse, day, shift):
        req = self.requests.get(nurse, [""] * self.days)[day]
        if req == SHIFT_R:
            return False
        if req in CLINICAL_SHIFTS + [SHIFT_M]:
            return req == shift
        return True

    def _is_fixed_request(self, nurse, day):
        req = self.requests.get(nurse, [""] * self.days)[day]
        return req in [SHIFT_R, SHIFT_M] + CLINICAL_SHIFTS

    def _transition_ok(self, nurse, day, shift):
        prev = self._prev(nurse, day)
        if (prev, shift) in FORBIDDEN_TRANSITIONS:
            return False
        # 若前一天是 N，只有第二天 N 或休假可接受；非夜班分配不准接在 N 後
        if prev == SHIFT_N and shift not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
            return False
        # 若今天排 E，隔天若已固定 D，則不行
        if day < self.days - 1 and shift == SHIFT_E and self.schedule[nurse][day + 1] == SHIFT_D:
            return False
        return True

    def _max_streak_ok(self, nurse, day, shift):
        if shift not in WORK_SHIFTS:
            return True
        before = self._continuous_before(nurse, day)
        if before + 1 > MAX_CONTINUOUS_WORK:
            return False
        # 往後看已排好的連班
        after = 0
        d = day + 1
        while d < self.days and self.schedule[nurse][d] in WORK_SHIFTS:
            after += 1
            d += 1
        return before + 1 + after <= MAX_CONTINUOUS_WORK

    def _can_assign(self, nurse, day, shift, allow_overwrite_off=False):
        if day < 0 or day >= self.days:
            return False
        cur = self.schedule[nurse][day]
        if cur not in ["", SHIFT_OFF] or (cur == SHIFT_OFF and not allow_overwrite_off):
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

    def _shift_count(self, day, shift):
        return sum(1 for n in self.names if self.schedule[n][day] == shift)

    def _min_req(self, day, shift):
        return self.manpower[day].get(f"{shift}_min", 0)

    def _max_req(self, day, shift):
        return self.manpower[day].get(f"{shift}_max", 999)

    # ---------- 排班步驟 ----------
    
    def _apply_requests(self):
        for nurse in self.names:
            for day in range(self.days):
                req = self.requests[nurse][day]
                if req == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                elif req == SHIFT_M:
                    self.schedule[nurse][day] = SHIFT_M
                elif req in CLINICAL_SHIFTS:
                    if self._permission_ok(nurse, req):
                        self.schedule[nurse][day] = req

    def _assign_parttime(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue

            # 固定預排的 D 先算入；若固定 D 已超過 PARTTIME_DAYS，不能任意刪除，只能保留並交由規則檢查提示
            current = sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT)
            target = max(0, PARTTIME_DAYS - current)

            # 優先排 3,3,2,2 區塊，讓兼職不是碎班
            blocks = [3, 3, 2, 2]
            for block_len in blocks:
                if target <= 0:
                    break
                length = min(block_len, target)
                starts = list(range(0, self.days - length + 1))
                self.random.shuffle(starts)
                starts.sort(
                    key=lambda s: self._parttime_block_score(nurse, s, length),
                    reverse=True
                )

                placed = False
                for start in starts:
                    days = list(range(start, start + length))
                    # 避免跟既有兼職 D 緊貼，盡量維持區塊清楚
                    before_ok = start == 0 or self.schedule[nurse][start - 1] != PARTTIME_ALLOWED_SHIFT
                    after_ok = start + length >= self.days or self.schedule[nurse][start + length] != PARTTIME_ALLOWED_SHIFT
                    if not (before_ok and after_ok):
                        continue
                    if all(self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True) for d in days):
                        for d in days:
                            self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                            self.fixed_parttime_days.add((nurse, d))
                        target -= length
                        placed = True
                        break

                # 若找不到完整區塊，後面再單日補足
                if not placed:
                    continue

            # 若區塊排不滿，單日補滿到 10 天
            for d in range(self.days):
                if target <= 0:
                    break
                if self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                    self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                    self.fixed_parttime_days.add((nurse, d))
                    target -= 1

            self._trim_parttime_extra_days()

    def _parttime_block_score(self, nurse, start, length):
        score = 0
        for d in range(start, start + length):
            if self._shift_count(d, SHIFT_D) < self._min_req(d, SHIFT_D):
                score += 10
        return score

    def _assign_night_blocks(self):
        # 每天補 N_min；N 以 N,N,off,off 一組排
        for day in range(self.days):
            while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N):
                candidates = self._night_candidates(day)
                if not candidates:
                    break
                nurse = candidates[0]
                self._place_night_block(nurse, day)

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
        if start_day >= self.days:
            return False
        # N,N
        for d in [start_day, start_day + 1]:
            if self._shift_count(d, SHIFT_N) >= self._max_req(d, SHIFT_N) and self.schedule[nurse][d] != SHIFT_N:
                return False
            if not self._can_assign(nurse, d, SHIFT_N, allow_overwrite_off=True):
                return False
        # off,off 不能覆蓋 R/M/固定臨床；可用月底不足時放寬
        for d in [start_day + 2, start_day + 3]:
            if d >= self.days:
                continue
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False
            if self.requests[nurse][d] not in ["", SHIFT_OFF]:
                return False
        return True

    def _place_night_block(self, nurse, start_day):
      self.schedule[nurse][start_day] = SHIFT_N
      self.night_locked.add((nurse, start_day))

      if start_day + 1 < self.days:
         self.schedule[nurse][start_day + 1] = SHIFT_N
         self.night_locked.add((nurse, start_day + 1))

      for d in [start_day + 2, start_day + 3]:
          if d < self.days:
              self.schedule[nurse][d] = SHIFT_OFF
              self.night_locked.add((nurse, d))

    def _assign_shift_by_need(self, shift):
        for day in range(self.days):
            while self._shift_count(day, shift) < self._min_req(day, shift):
                candidates = []
                for nurse in self.names:

                    if nurse in PART_TIME:
                        continue
                    if self._can_assign(nurse, day, shift, allow_overwrite_off=True):
                        candidates.append(nurse)
                if not candidates:
                    break
                self.random.shuffle(candidates)
                candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
                if shift == SHIFT_N:
                    break
                self.schedule[candidates[0]][day] = shift

    def _candidate_score(self, nurse, day, shift):
        score = 0
        if self._prev(nurse, day) == shift:
            score += 8
        if day < self.days - 1 and self.schedule[nurse][day + 1] == shift:
            score += 6
        if self._prev(nurse, day) in WORK_SHIFTS:
            score += 4
        score -= self._workload(nurse) * 1.5
        if shift == SHIFT_E:
            score -= sum(1 for x in self.schedule[nurse] if x == SHIFT_E) * 2
        if shift == SHIFT_D:
            score -= sum(1 for x in self.schedule[nurse] if x == SHIFT_D) * 1
        score += self.random.random()
        return score

    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    if self.requests[nurse][day] == SHIFT_R:
                        self.schedule[nurse][day] = SHIFT_R
                    else:
                        self.schedule[nurse][day] = SHIFT_OFF

    # ---------- 修復與平衡 ----------
    def _repair_manpower_shortage(self):
        for _ in range(5):
            changed = False
            for day in range(self.days):
                for shift in [SHIFT_N, SHIFT_E, SHIFT_D]:
                    while self._shift_count(day, shift) < self._min_req(day, shift):
                        if shift == SHIFT_N:
                            candidates = self._night_candidates(day)
                            if not candidates:
                                break
                            self._place_night_block(candidates[0], day)
                            changed = True
                        else:
                            candidates = [
                                n for n in self.names
                                if n not in PART_TIME
                                and self._can_assign(n, day, shift, allow_overwrite_off=True)
                            ]
                            if not candidates:
                                break
                            self.random.shuffle(candidates)
                            candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
                            if shift == SHIFT_N:
                                break
                            self.schedule[candidates[0]][day] = shift
                            changed = True
            if not changed:
                break

    def _trim_parttime_extra_days(self):
        """兼職固定 PARTTIME_DAYS 天 D；只刪非預排、非鎖定的多餘 D。"""
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue
            while sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                removable = [
                    d for d in range(self.days - 1, -1, -1)
                    if self.schedule[nurse][d] == PARTTIME_ALLOWED_SHIFT
                    and self.requests[nurse][d] == ""
                    and (nurse, d) not in self.fixed_parttime_days
                ]
                if not removable:
                    # 若全部都是本次排入的鎖定日，仍可由月底往前刪，避免超過 10 天
                    removable = [
                        d for d in range(self.days - 1, -1, -1)
                        if self.schedule[nurse][d] == PARTTIME_ALLOWED_SHIFT
                        and self.requests[nurse][d] == ""
                    ]
                if not removable:
                    break
                d = removable[0]
                self.schedule[nurse][d] = SHIFT_OFF
                self.fixed_parttime_days.discard((nurse, d))

    def _enforce_night_pattern(self):
        """盡量修正成 N,N,off,off，避免單 N 或 N 後接 D/E。"""
        full_time = [n for n in self.names if n not in PART_TIME]
        for nurse in full_time:
            day = 0
            while day < self.days:
                if self.schedule[nurse][day] != SHIFT_N:
                    day += 1
                    continue

                start = day
                while day < self.days and self.schedule[nurse][day] == SHIFT_N:
                    day += 1
                end = day
                length = end - start

                # 單天 N：優先把隔天補成 N；不行就嘗試前一天補 N
                if length == 1:
                    if start + 1 < self.days and self._can_assign(nurse, start + 1, SHIFT_N, allow_overwrite_off=True):
                        if self._shift_count(start + 1, SHIFT_N) < self._max_req(start + 1, SHIFT_N):
                            self.schedule[nurse][start + 1] = SHIFT_N
                            end = start + 2
                    elif start - 1 >= 0 and self._can_assign(nurse, start - 1, SHIFT_N, allow_overwrite_off=True):
                        if self._shift_count(start - 1, SHIFT_N) < self._max_req(start - 1, SHIFT_N):
                            self.schedule[nurse][start - 1] = SHIFT_N
                            start -= 1
                            end = day

                # N 區塊後兩天應為 off；不覆蓋 R/M/預排臨床班
                for off_day in [end, end + 1]:
                    if off_day >= self.days:
                        continue
                    if self.requests[nurse][off_day] != "":
                        continue
                    if self.schedule[nurse][off_day] in ["", SHIFT_OFF]:
                        self.schedule[nurse][off_day] = SHIFT_OFF
                        continue
                    cur = self.schedule[nurse][off_day]
                    if cur in CLINICAL_SHIFTS and self._shift_count(off_day, cur) > self._min_req(off_day, cur):
                        self.schedule[nurse][off_day] = SHIFT_OFF

    def _balance_holidays(self):
        full_time = [n for n in self.names if n not in PART_TIME]

        for _ in range(30):
            changed = False
            off_counts = {n: sum(1 for x in self.schedule[n] if x in REST_SHIFTS) for n in full_time}
            under = [n for n in full_time if off_counts[n] < MIN_FULLTIME_OFF_DAYS]
            if not under:
                break
            under.sort(key=lambda n: off_counts[n])

            for nurse in under:
                # 先找「人力高於最低」的班直接轉 off
                candidates = []
                for day in range(self.days):
                    shift = self.schedule[nurse][day]
                    if shift not in CLINICAL_SHIFTS:
                        continue
                    if self.requests[nurse][day] != "":
                        continue
                    if self._shift_count(day, shift) > self._min_req(day, shift):
                        candidates.append(day)

                if candidates:
                    # 優先拿掉單日碎班或工作量較重的天
                    candidates.sort(key=lambda d: self._fragment_penalty(nurse, d), reverse=True)
                    d = candidates[0]
                    self.schedule[nurse][d] = SHIFT_OFF
                    changed = True
                    break

                # 若不能直接拿掉，找休假較多者頂替
                for day in range(self.days):
                    shift = self.schedule[nurse][day]
                    if shift not in CLINICAL_SHIFTS:
                        continue
                    if self.requests[nurse][day] != "":
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
                        changed = True
                        break

                if changed:
                    break

            if not changed:
                break

    def _fragment_penalty(self, nurse, day):
        cur = self.schedule[nurse][day]
        left = SHIFT_OFF if day == 0 else self.schedule[nurse][day - 1]
        right = SHIFT_OFF if day == self.days - 1 else self.schedule[nurse][day + 1]
        score = 0
        if left in REST_SHIFTS and right in REST_SHIFTS:
            score += 10
        if cur == SHIFT_D:
            score += 1
        return score

    def _remove_single_day_fragments(self):
        full_time = [n for n in self.names if n not in PART_TIME]
        rest_values = set(REST_SHIFTS) | {""}

        for _ in range(10):
            changed = False
            for nurse in full_time:
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E]:
                        continue

                    left = SHIFT_OFF if day == 0 else self.schedule[nurse][day - 1]
                    right = SHIFT_OFF if day == self.days - 1 else self.schedule[nurse][day + 1]
                    left_rest = left in rest_values
                    right_rest = right in rest_values
                    if not (left_rest and right_rest):
                        continue

                    # 非預排且當日人力有餘，直接改 off
                    if self.requests[nurse][day] == "" and self._shift_count(day, cur) > self._min_req(day, cur):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = True
                        continue

                    # 無法取消時，嘗試往前/後延長同班，避免 1 天碎班
                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                            if self._shift_count(nd, cur) < self._max_req(nd, cur):
                                self.schedule[nurse][nd] = cur
                                changed = True
                                break
            if not changed:
                break


def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
    return scheduler.generate()
