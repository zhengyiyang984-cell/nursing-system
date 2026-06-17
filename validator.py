# validator.py
class NursingValidator:
    def __init__(self, df):
        self.df = df
        
    def check_part_time_days(self, staff_name, max_days=10):
        """檢查兼職人員是否超過 10 天上班限制"""
        schedule = self.df[self.df['姓名/職級'] == staff_name].iloc[0]
        # 統計班別為 D, E, N 的總天數
        active_days = schedule.isin(['D', 'E', 'N']).sum()
        
        if active_days > max_days:
            return False, f"{staff_name} 目前排班 {active_days} 天，超過兼職上限 {max_days} 天。"
        return True, "符合規範"
