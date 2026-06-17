# validator.py
import config

class ScheduleValidator:
    def __init__(self, df):
        self.df = df # 傳入的 DataFrame

    def get_staff_stats(self, staff_name):
        """計算人員出勤天數"""
        row = self.df[self.df['姓名/職級'] == staff_name].iloc[0]
        # 只統計 is_working 為 True 的班別
        working_days = [val for val in row if val in [k for k, v in config.SHIFT_STATUS.items() if v["is_working"]]]
        return len(working_days)

    def validate_rules(self):
        """檢查整份排班表是否合規"""
        errors = []
        staff_list = self.df['姓名/職級'].unique()
        
        # 1. 檢查兼職天數 (針對每個員工)
        for staff in staff_list:
            days = self.get_staff_stats(staff)
            if days > config.RULES["MAX_PART_TIME_DAYS"]:
                errors.append(f"{staff} 已排 {days} 天，超過限制 {config.RULES['MAX_PART_TIME_DAYS']} 天")
        
        # 2. 檢查每日人力需求 (針對每一天)
        date_cols = [c for c in self.df.columns if c not in ['姓名/職級']]
        for day in date_cols:
            d_count = sum(1 for s in self.df[day] if s == 'D')
            if d_count < config.RULES["MIN_D_SHIFT"]:
                errors.append(f"日期 {day}: 早班人力不足 (現有 {d_count})")
                
        return errors
