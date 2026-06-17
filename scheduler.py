"""
scheduler.py
2F護理排班核心 V3.0
"""

import random
from copy import deepcopy

from config import *


class Scheduler:

    def __init__(
        self,
        names,
        permissions,
        requests,
        manpower,
        history_shift,
        history_streak
    ):

        self.names = names
        self.permissions = permissions
        self.requests = requests
        self.manpower = manpower

        self.history_shift = history_shift
        self.history_streak = history_streak

        self.days = len(manpower)

        self.schedule = {
            n: ["" for _ in range(self.days)]
            for n in names
        }

        self.work_count = {n: 0 for n in names}
        self.night_count = {n: 0 for n in names}
        self.off_count = {n: 0 for n in names}

    # ------------------------

    def can_work(self, nurse, shift):

        permission = self.permissions[nurse]

        return shift in permission

    # ------------------------

    def previous_shift(self, nurse, day):

        if day == 0:
            return self.history_shift.get(nurse, "off")

        return self.schedule[nurse][day - 1]

    # ------------------------

    def continuous_work(self, nurse, day):

        c = 0

        d = day - 1

        while d >= 0:

            if self.schedule[nurse][d] in WORK_SHIFT:
                c += 1
                d -= 1
            else:
                break

        if day == 0:

            c = self.history_streak.get(nurse, 0)

        return c

    # ------------------------

    def is_safe(self, nurse, day, shift):

        prev = self.previous_shift(nurse, day)

        if prev == "E" and shift == "D":
            return False

        if prev == "N":

            if shift != "N":
                return False

        if self.continuous_work(nurse, day) >= MAX_CONTINUOUS_WORK:
            return False

        return True
