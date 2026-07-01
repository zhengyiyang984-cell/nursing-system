import random
from config import *


class NurseScheduler:
    """2F 護理排班核心 V5

    設計重點：
    1. 兼職郭珍君鎖定：只排 D，盡量剛好 10 天，後續補班不再動她。
    2. 大夜只用 N,N,off,off 區塊排入，不塞單顆 N。
    3. 每次休假平衡、碎班修正後，都會再次補人力。
    4. 盡量不動 R、M、預排 D/E/N。
    """

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

    # =========================================================
    # 主流程
    # =========================================================
    def generate(self):
        self._apply_requests()
        self._assign_parttime_exact()
        self._assign_night_blocks()
        self._assign_shift_by_need(SHIFT_E)
        self._assign_shift_by_need(SHIFT_D)
        self._fill_blank_with_off()

        # 多輪修復：補人力與休假平衡會互相影響，所以交替執行。
        for _ in range(5):
            changed = False
            changed |= self._repair_night_shortage()
            changed |= self._repair_shift_shortage(SHIFT_E)
            changed |= self._repair_shift_shortage(SHIFT_D)
            changed |= self._balance_holidays()
            changed |= self._remove_single_day_fragments()
            changed |= self._enforce_parttime_limit()
            self._fill_blank_with_off()
            if not changed:
                break

        # 最後保底：先確保兼職，再補人力，再填 off。
        self._enforce_parttime_limit()
        self._repair_night_shortage()
        self._repair_shift_shortage(SHIFT_E)
        self._repair_shift_shortage(SHIFT_D)
        self._fill_blank_with_off()
        return self.schedule

    # =========================================================
    # 基礎工具
    # =========================================================
    def _req(self, nurse, day):
        return self.requests.get(nurse, [""] * self.days)[day]

    def _is_fixed_request(self, nurse, day):
        return self._req(nurse, day) in [SHIFT_R, SHIFT_M] + CLINICAL_SHIFTS

    def _is_protected(self, nurse, day):
        """不可被系統改掉的格子。"""
        return self._req(nurse, day) in [SHIFT_R, SHIFT_M] + CLINICAL_SHIFTS

    def _workload(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in WORK_SHIFTS)

    def _night_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x == SHIFT_N)

    def _off_count(self, nurse):
        return sum(1 for x in self.schedule[nurse] if x in REST_SHIFTS or x == "")

    def _shift_count(self, day, shift):
        return sum(1 for n in self.names if self.schedule[n][day] == shift)

    def _min_req(self, day, shift):
        return self.manpower[day].get(f"{shift}_min", 0)

    def _max_req(self, day, shift):
        return self.manpower[day].get(f"{shift}_max", 999)

    def _prev(self, nurse, day):
        if day == 0:
            return self.history_shift.get(nurse, SHIFT_OFF)
        return self.schedule[nurse][day - 1]

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
        if nurse in PART_TIME:
            return shift == PARTTIME_ALLOWED_SHIFT
        return shift in self.permissions.get(nurse, "DEN")

    def _request_allows(self, nurse, day, shift):
        req = self._req(nurse, day)
        if req == SHIFT_R:
            return False
        if req in CLINICAL_SHIFTS + [SHIFT_M]:
            return req == shift
        return True

    def _transition_ok(self, nurse, day, shift):
        prev = self._prev(nurse, day)
        if (prev, shift) in FORBIDDEN_TRANSITIONS:
            return False
        if prev == SHIFT_N and shift not in [SHIFT_N, SHIFT_OFF, SHIFT_R]:
            return False
        if day < self.days - 1 and shift == SHIFT_E and self.schedule[nurse][day + 1] == SHIFT_D:
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
        if nurse in PART_TIME and shift != PARTTIME_ALLOWED_SHIFT:
            return False
        cur = self.schedule[nurse][day]
        if cur not in ["", SHIFT_OFF] or (cur == SHIFT_OFF and not allow_overwrite_off):
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

    def _can_clear_to_off(self, nurse, day):
        if day < 0 or day >= self.days:
            return False
        if self._is_protected(nurse, day):
            return False
        return self.schedule[nurse][day] in CLINICAL_SHIFTS

    # =========================================================
    # 固定資料
    # =========================================================
    def _apply_requests(self):
        for nurse in self.names:
            for day in range(self.days):
                req = self._req(nurse, day)
                if req == SHIFT_R:
                    self.schedule[nurse][day] = SHIFT_R
                elif req == SHIFT_M:
                    self.schedule[nurse][day] = SHIFT_M
                elif req in CLINICAL_SHIFTS and self._permission_ok(nurse, req):
                    self.schedule[nurse][day] = req

    # =========================================================
    # 兼職：郭珍君只排 D，目標剛好 10 天
    # =========================================================
    def _assign_parttime_exact(self):
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue

            # 先移除非固定的兼職 D，避免舊結果或修復過量。
            for day in range(self.days):
                if self.schedule[nurse][day] == PARTTIME_ALLOWED_SHIFT and not self._is_protected(nurse, day):
                    self.schedule[nurse][day] = ""
                elif self.schedule[nurse][day] in [SHIFT_E, SHIFT_N, SHIFT_M] and not self._is_protected(nurse, day):
                    self.schedule[nurse][day] = ""

            current = sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT)
            need = max(0, PARTTIME_DAYS - current)
            blocks = [3, 3, 2, 2]
            self.random.shuffle(blocks)

            for block_len in blocks:
                if need <= 0:
                    break
                length = min(block_len, need)
                starts = list(range(0, self.days - length + 1))
                self.random.shuffle(starts)
                starts.sort(key=lambda s: self._parttime_block_score(nurse, s, length), reverse=True)
                for start in starts:
                    days = list(range(start, start + length))
                    if all(self._can_assign(nurse, d, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True) for d in days):
                        for d in days:
                            self.schedule[nurse][d] = PARTTIME_ALLOWED_SHIFT
                        need -= length
                        break

            # 若因 R/M 太多造成不足，最後用單日補到 10；但仍只排 D。
            for day in range(self.days):
                if need <= 0:
                    break
                if self._can_assign(nurse, day, PARTTIME_ALLOWED_SHIFT, allow_overwrite_off=True):
                    self.schedule[nurse][day] = PARTTIME_ALLOWED_SHIFT
                    need -= 1

            self._enforce_parttime_limit()

    def _parttime_block_score(self, nurse, start, length):
        score = 0
        for day in range(start, start + length):
            if self._shift_count(day, SHIFT_D) < self._min_req(day, SHIFT_D):
                score += 30
            if day > 0 and self.schedule[nurse][day - 1] == PARTTIME_ALLOWED_SHIFT:
                score += 3
            if day + 1 < self.days and self.schedule[nurse][day + 1] == PARTTIME_ALLOWED_SHIFT:
                score += 3
        return score

    def _enforce_parttime_limit(self):
        changed = False
        for nurse in PART_TIME:
            if nurse not in self.names:
                continue
            # 不允許兼職 E/N/M，固定預排 M 例外不改；非固定全部清掉。
            for day in range(self.days):
                if self.schedule[nurse][day] in [SHIFT_E, SHIFT_N] and not self._is_protected(nurse, day):
                    self.schedule[nurse][day] = SHIFT_OFF
                    changed = True

            while sum(1 for x in self.schedule[nurse] if x == PARTTIME_ALLOWED_SHIFT) > PARTTIME_DAYS:
                removable = []
                for day in range(self.days):
                    if self.schedule[nurse][day] != PARTTIME_ALLOWED_SHIFT:
                        continue
                    if self._is_protected(nurse, day):
                        continue
                    # 優先移除當天 D 人力超過最低的日子。
                    surplus = self._shift_count(day, SHIFT_D) - self._min_req(day, SHIFT_D)
                    removable.append((surplus, day))
                if not removable:
                    break
                removable.sort(reverse=True)
                _, day = removable[0]
                self.schedule[nurse][day] = SHIFT_OFF
                changed = True
        return changed

    # =========================================================
    # 大夜：只能排 N,N,off,off
    # =========================================================
    def _assign_night_blocks(self):
        for day in range(self.days):
            while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N):
                if not self._place_best_night_block_covering(day):
                    break

    def _repair_night_shortage(self):
        changed = False
        for day in range(self.days):
            while self._shift_count(day, SHIFT_N) < self._min_req(day, SHIFT_N):
                if self._place_best_night_block_covering(day):
                    changed = True
                else:
                    break
        return changed

    def _place_best_night_block_covering(self, day):
        options = []
        for start in [day - 1, day]:
            if start < 0 or start >= self.days:
                continue
            for nurse in self.names:
                if nurse in PART_TIME:
                    continue
                if self._can_place_night_block(nurse, start):
                    options.append((self._night_block_score(nurse, start, day), nurse, start))
        if not options:
            return False
        self.random.shuffle(options)
        options.sort(reverse=True)
        _, nurse, start = options[0]
        self._place_night_block(nurse, start)
        return True

    def _night_block_score(self, nurse, start, target_day):
        score = 0
        for d in [start, start + 1]:
            if 0 <= d < self.days and self._shift_count(d, SHIFT_N) < self._min_req(d, SHIFT_N):
                score += 60
        score -= self._night_count(nurse) * 8
        score -= self._workload(nurse) * 2
        score += self._off_count(nurse)
        score += self.random.random()
        return score

    def _can_place_night_block(self, nurse, start):
        if start < 0 or start >= self.days:
            return False
        n_days = [start, start + 1]
        off_days = [start + 2, start + 3]

        # N,N：月底若第二天超出，允許只排到月底，但平常要兩天。
        for d in n_days:
            if d >= self.days:
                continue
            if self._shift_count(d, SHIFT_N) >= self._max_req(d, SHIFT_N) and self.schedule[nurse][d] != SHIFT_N:
                return False
            if not self._can_assign(nurse, d, SHIFT_N, allow_overwrite_off=True):
                return False

        # off,off：不可覆蓋固定 R/M/D/E/N，也不可覆蓋已排好的臨床班。
        for d in off_days:
            if d >= self.days:
                continue
            if self._is_protected(nurse, d):
                return False
            if self.schedule[nurse][d] not in ["", SHIFT_OFF]:
                return False
        return True

    def _place_night_block(self, nurse, start):
        for d in [start, start + 1]:
            if d < self.days:
                self.schedule[nurse][d] = SHIFT_N
        for d in [start + 2, start + 3]:
            if d < self.days and not self._is_protected(nurse, d):
                self.schedule[nurse][d] = SHIFT_OFF

    # =========================================================
    # E / D 人力
    # =========================================================
    def _assign_shift_by_need(self, shift):
        if shift == SHIFT_N:
            return
        for day in range(self.days):
            while self._shift_count(day, shift) < self._min_req(day, shift):
                candidates = self._shift_candidates(day, shift)
                if not candidates:
                    break
                self.schedule[candidates[0]][day] = shift

    def _repair_shift_shortage(self, shift):
        if shift == SHIFT_N:
            return self._repair_night_shortage()
        changed = False
        for day in range(self.days):
            guard = 0
            while self._shift_count(day, shift) < self._min_req(day, shift) and guard < len(self.names) + 5:
                guard += 1
                candidates = self._shift_candidates(day, shift)
                if not candidates:
                    break
                self.schedule[candidates[0]][day] = shift
                changed = True
        return changed

    def _shift_candidates(self, day, shift):
        candidates = []
        for nurse in self.names:
            if nurse in PART_TIME:
                continue
            if self._can_assign(nurse, day, shift, allow_overwrite_off=True):
                candidates.append(nurse)
        self.random.shuffle(candidates)
        candidates.sort(key=lambda n: self._candidate_score(n, day, shift), reverse=True)
        return candidates

    def _candidate_score(self, nurse, day, shift):
        score = 0
        prev = self._prev(nurse, day)
        if prev == shift:
            score += 12
        if prev in WORK_SHIFTS:
            score += 4
        if day + 1 < self.days and self.schedule[nurse][day + 1] == shift:
            score += 8
        if self._shift_count(day, shift) < self._min_req(day, shift):
            score += 20
        score -= self._workload(nurse) * 2
        score -= sum(1 for x in self.schedule[nurse] if x == shift) * 2
        score += self._off_count(nurse) * 0.5
        score += self.random.random()
        return score

    # =========================================================
    # 修復與平衡
    # =========================================================
    def _fill_blank_with_off(self):
        for nurse in self.names:
            for day in range(self.days):
                if self.schedule[nurse][day] == "":
                    if self._req(nurse, day) == SHIFT_R:
                        self.schedule[nurse][day] = SHIFT_R
                    else:
                        self.schedule[nurse][day] = SHIFT_OFF

    def _balance_holidays(self):
        full_time = [n for n in self.names if n not in PART_TIME]
        changed = False
        for _ in range(20):
            off_counts = {n: sum(1 for x in self.schedule[n] if x in REST_SHIFTS) for n in full_time}
            under = [n for n in full_time if off_counts[n] < MIN_FULLTIME_OFF_DAYS]
            if not under:
                break
            under.sort(key=lambda n: off_counts[n])
            did = False
            for nurse in under:
                if self._give_one_more_off(nurse, off_counts):
                    changed = True
                    did = True
                    break
            if not did:
                break
        return changed

    def _give_one_more_off(self, nurse, off_counts):
        # 先找該班別人力超過最低的 D/E；不動 N，避免破壞 N block。
        days = list(range(self.days))
        self.random.shuffle(days)
        days.sort(key=lambda d: self._shift_count(d, self.schedule[nurse][d]) - self._min_req(d, self.schedule[nurse][d]) if self.schedule[nurse][d] in [SHIFT_D, SHIFT_E] else -99, reverse=True)
        for day in days:
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_clear_to_off(nurse, day):
                continue
            if self._shift_count(day, shift) > self._min_req(day, shift):
                self.schedule[nurse][day] = SHIFT_OFF
                return True

        # 若剛好最低，找休比較多的人頂替。
        helpers_pool = [n for n in self.names if n not in PART_TIME and n != nurse]
        for day in days:
            shift = self.schedule[nurse][day]
            if shift not in [SHIFT_D, SHIFT_E]:
                continue
            if not self._can_clear_to_off(nurse, day):
                continue
            helpers = []
            for helper in helpers_pool:
                if off_counts.get(helper, 0) <= TARGET_FULLTIME_OFF_DAYS:
                    continue
                if self._can_assign(helper, day, shift, allow_overwrite_off=True):
                    helpers.append(helper)
            if helpers:
                helpers.sort(key=lambda h: (off_counts.get(h, 0), -self._workload(h)), reverse=True)
                helper = helpers[0]
                self.schedule[nurse][day] = SHIFT_OFF
                self.schedule[helper][day] = shift
                return True
        return False

    def _remove_single_day_fragments(self):
        changed = False
        full_time = [n for n in self.names if n not in PART_TIME]
        for _ in range(20):
            did = False
            for nurse in full_time:
                for day in range(self.days):
                    cur = self.schedule[nurse][day]
                    if cur not in [SHIFT_D, SHIFT_E]:
                        continue
                    left_rest = day == 0 or self.schedule[nurse][day - 1] in REST_SHIFTS
                    right_rest = day == self.days - 1 or self.schedule[nurse][day + 1] in REST_SHIFTS
                    if not (left_rest and right_rest):
                        continue

                    if self._can_clear_to_off(nurse, day) and self._shift_count(day, cur) > self._min_req(day, cur):
                        self.schedule[nurse][day] = SHIFT_OFF
                        changed = True
                        did = True
                        continue

                    # 不能取消時，嘗試把同班別延伸到前後一天。
                    for nd in [day + 1, day - 1]:
                        if 0 <= nd < self.days and self._shift_count(nd, cur) < self._max_req(nd, cur):
                            if self._can_assign(nurse, nd, cur, allow_overwrite_off=True):
                                self.schedule[nurse][nd] = cur
                                changed = True
                                did = True
                                break
            if not did:
                break
        return changed


def build_schedule_once(names, permissions, requests, manpower, history_shift, history_streak, seed=None):
    scheduler = NurseScheduler(names, permissions, requests, manpower, history_shift, history_streak, seed=seed)
    return scheduler.generate()
