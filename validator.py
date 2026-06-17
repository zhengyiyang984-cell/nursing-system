# validator.py
import config

class NursingValidator:
    def __init__(self, df):
        self.df = df
        
    def calculate_work_days(self, staff_name):
        """計算該人員的實際出勤天數 (包含開會 M)"""
        row = self.df[self.df['姓名/職級'] == staff_name].iloc[0]
        # 只統計 'is_working' 為 True 的天數
        work_days = [val for val in row if val in [k for k, v in config.SHIFT_STATUS.items() if v["is_working"]]]
        return len(work_days)

    def get_daily_manpower(self, day):
        """計算當日實際投入人力 (排除開會 M)"""
        manpower_list = []
        for index, row in self.df.iterrows():
            shift = row[day]
            if config.SHIFT_STATUS.get(shift, {}).get("counts_in_manpower", False):
                manpower_list.append(row['姓名/職級'])
        return manpower_list
