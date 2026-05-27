import streamlit as st
import pandas as pd
from io import BytesIO
import datetime
import re

# --- 頁面設定 ---
st.set_page_config(page_title="2F 護理排班系統", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]
CORE_STAFF_NAMES = [
    "郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", 
    "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", 
    "汪家容", "林欣儀", "林怡薇"
]

# --- 1. 基本班表解析 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    for i in range(len(df)):
        row_str = "".join(str(v) for v in df.iloc[i].values)
        matched_name = next((name for name in CORE_STAFF_NAMES if name in row_str), None)
        if matched_name:
            # 簡化權限解析：預設 DEN，你可以根據 Excel 內容擴充
            configs[matched_name] = {"perm": "DEN", "is_part_time": (matched_name == "郭珍君")}
    return configs

st.title("🏥 2F 護理排班系統 (循環輪替版)")

# --- 2. 側邊欄設定 ---
with st.sidebar:
    st.header("📅 排班設定")
    start_date = st.date_input("開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("結束日期", datetime.date(2026, 6, 30))
    num_days = (end_date - start_date).days + 1
    date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in [(start_date + datetime.timedelta(days=x)) for x in range(num_days)]]
    
    file_a = st.file_uploader("1. 上傳【基本班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])

# --- 3. 主程式邏輯 ---
if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        display_names = list(staff_configs.keys())
        
        # 解析預排休 (bg_vacation)
        bg_vacation = {n: [""] * num_days for n in display_names}
        xl = pd.ExcelFile(file_b)
        for sheet_name in xl.sheet_names:
            if any(k in sheet_name for k in ["規範", "說明", "填寫"]): continue
            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)
            # 自動搜尋「姓名」欄位
            for r in range(min(5, len(df_b))):
                vals = [str(v).strip() for v in df_b.iloc[r].values]
                if "姓名" in vals:
                    name_col = vals.index("姓名")
                    for i in range(r + 1, len(df_b)):
                        name = str(df_b.iloc[i, name_col]).strip()
                        target = next((n for n in display_names if n in name), None)
                        if target:
                            for d in range(num_days):
                                if name_col + 1 + d < len(df_b.columns):
                                    cell = str(df_b.iloc[i, name_col + 1 + d]).upper()
                                    if "R" in cell: bg_vacation[target][d] = "R"
            break

        st.info("系統已讀取班表與預排休，點擊下方按鈕開始產生循環班表。")
        
        # 循環模式序列
        cycle_patterns = ["D", "D", "E", "E", "N", "N", "off", "off"]
        
        if st.button("🚀 啟動循環輪替排班", type="primary", use_container_width=True):
            final_res = {}
            for idx, n in enumerate(display_names):
                shift_offset = idx * 2  # 位移量，確保每人班表不同
                person_schedule = []
                for d in range(num_days):
                    # 循環計算
                    shift = cycle_patterns[(d + shift_offset) % len(cycle_patterns)]
                    
                    # 權限過濾
                    perm = staff_configs[n]["perm"]
                    if shift not in perm and shift != "off":
                        shift = "D" if "D" in perm else "off"
                    
                    # 預排休覆蓋
                    if bg_vacation.get(n, [""] * num_days)[d] == "R":
                        shift = "off"
                        
                    person_schedule.append(shift)
                final_res[n] = person_schedule

            # 顯示與下載
            final_df = pd.DataFrame(final_res).T
            final_df.columns = date_headers
            st.success("🎉 循環班表產生完畢！")
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                final_df.to_excel(w, sheet_name="循環班表")
            st.download_button("📥 下載 Excel 班表", data=out.getvalue(), file_name="2F_Cycle_Schedule.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統運行錯誤: {e}")
