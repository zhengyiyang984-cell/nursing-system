# loader.py
import pandas as pd

def load_data(file_path):
    """讀取 .xlsx 格式的排班表"""
    try:
        # 使用 openpyxl 引擎讀取 xlsx
        df = pd.read_excel(file_path, engine='openpyxl')
        
        # 清除姓名欄位的空格
        if '姓名/職級' in df.columns:
            df['姓名/職級'] = df['姓名/職級'].str.strip()
        return df
    except Exception as e:
        print(f"讀取 Excel 錯誤: {e}")
        return None
