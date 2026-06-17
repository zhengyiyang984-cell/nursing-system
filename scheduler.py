# scheduler.py
import pandas as pd
import numpy as np
import config

def generate(df):
    """
    初步的排班產生器：
    根據人員名單與日期，進行基礎的班別填充
    """
    staff_names = [col for col in df.columns if col != 'Date']
    schedule = df.copy()
    
    for staff in staff_names:
        # 暫時用簡單的邏輯填入：預設為 OFF，之後由演算法填入 D/R
        schedule[staff] = 'OFF'
        
    return schedule
