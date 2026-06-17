# loader.py
import pandas as pd

def load_schedule_data(file_path):
    """
    讀取護理排班 Excel
    - 處理 C 欄為姓名的結構
    - 自動識別日期欄位 (4-31)
    """
    # 讀取 CSV/Excel，略過前幾行多餘的敘述 (假設真實資料從第 4 行開始)
    df = pd.read_csv(file_path, header=0)
    
    # 清洗：移除姓名後的空格 (如 "郭珍君PN2 " -> "郭珍君PN2")
    df['姓名/職級'] = df['姓名/職級'].str.strip()
    
    # 建立日期清單 (對應 D 欄以後的欄位)
    date_columns = [col for col in df.columns if col.isdigit()]
    
    return df, date_columns

def get_staff_schedule(df, staff_name):
    """提取特定護理師的班別序列"""
    row = df[df['姓名/職級'] == staff_name]
    if not row.empty:
        return row.iloc[0]
    return None
