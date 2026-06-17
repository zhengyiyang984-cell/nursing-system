# validator.py
import config

class ScheduleValidator:
    def __init__(self, schedule_df):
        self.schedule = schedule_df

    def check_part_time_limit(self, staff_id):
        """檢查兼職人員天數是否超過 10 天"""
        count = (self.schedule[staff_id] != 'OFF').sum()
        if count > config.MAX_PART_TIME_DAYS:
            return False, f"人員 {staff_id} 超過兼職上限 {config.MAX_PART_TIME_DAYS} 天"
        return True, "OK"

    def validate_all(self):
        """執行所有規則檢查"""
        # 在這裡呼叫各種 check 函數
        pass
