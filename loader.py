# loader.py
import pandas as pd

def load_excel(file_path):
    """
    讀取排班 Excel，預期格式：
    - 第一欄為日期 (Date)
    - 其他欄位為人員姓名
    """
    try:
        df = pd.read_excel(file_path)
        # 確保日期欄位為 datetime 格式
        df['Date'] = pd.to_datetime(df['Date'])
        return df
    except Exception as e:
        print(f"讀取 Excel 失敗: {e}")
        return None

def get_staff_names(df):
    """獲取 Excel 中除日期外的所有人員姓名"""
    return [col for col in df.columns if col != 'Date']
