import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析邏輯 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    
    # 定位起始行
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 基礎過濾
        if (no == "" or no == "nan") and (name == "" or name == "nan"): continue
        if "星期" in no or "星期" in name or "姓名" in name: continue
        
        # 決定顯示的 Key
        display_label = no if (no != "nan" and no != "") else name
        if display_label == "" or display_label == "nan": continue 

        # 強力封殺結尾的統計與編號雜訊欄位
        clean_check = display_label.replace(" ", "").upper()
        if clean_check in ["OFF", "R", "V", "ALL", "TOTAL", "統計", "D4", "E3", "N2"]: 
            continue

        is_pt = "半職" in no or "半職" in name

        last_day = "off"
        for cell in reversed(row.values[3:8]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_day = c if c in ["D", "E", "N", "R"] else c.lower()
                break
        if last_day not in ["D", "E", "N", "off", "v", "R"]: last_day = "off"

        pure_id = re.sub(r'[\s\u3000]', '', name) if (name != "nan" and name != "") else display_label

        configs[display_label] = {
            "pure_id": pure_id,
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": last_day,
            "is_part_time": is_pt
        }
    return configs

# --- 2. 半職專用排班演算 ---
def schedule_part_time(num_days):
    for _ in range(100):
        days = ["off"] * num_days
        available_patterns = [
            [2, 2, 2, 2, 2],
            [3, 3, 2, 2],
            [3, 2, 3, 2],
            [2, 3, 2, 3],
            [2, 2, 3, 3]
        ]
        work_blocks = random.choice(available_patterns)
        random.shuffle(work_blocks) 
        
        current_idx = random.randint(0, 2) 
        success = True
        
        for block in work_blocks:
            if current_idx + block > num_days:
                success = False
                break
            
            for _ in range(block):
                days[current_idx] = "D"
                current_idx += 1
            
            current_idx += random.randint(2, 4)
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    backup_days = ["off"] * num_days
    safe_indices = [2, 3, 4, 9, 10, 15, 16, 17, 22, 23] 
    for idx in safe_indices:
        if idx < num_days: backup_days[idx] = "D"
    return backup_days

st.title("🏥 2F 護理排班系統")

# --- 3. 側邊欄自訂日期設定 ---
with st.sidebar:
    st.header("📂 檔案上傳與日期設定")
    
    today = datetime.date.today()
    start_date = st.date_input("排班開始日期", today.replace(day=1))
    end_date = st.date_input("排班結束日期", today.replace(day=28) + datetime.timedelta(days=3))
    
    if start_date <= end_date:
        date_objects = [start_date + datetime.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        num_days = len(date_objects)
        date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in date_objects]
        st.info(f"📅 本次排班共計：{num_days} 天")
    else:
        st.error("⚠️ 錯誤：結束日期不能早於開始日期！")
        num_days = 0

    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b and num_days > 0:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        
        full_time_names = [n for n in all_names if not staff_configs[n]["is_part_time"]]
        part_time_names = [n for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        # 背景自動掃描檔案 B
        df_b = pd.read_excel(file_b, header=None)
        bg_vacation = {n: [""] * num_days for n in display_names}
        for i in range(len(df_b)):
            b_name = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            for n in display_names:
                if staff_configs[n]["pure_id"] == b_name or n == b_name:
                    for d in range(num_days):
                        val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                        if val in ["R", "OFF", "V", "開會", "0", "●"]: bg_vacation[n][d] = "R"
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 成功辨識 {len(display_names)} 位有效人員。")

        # --- 核對區 ---
        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"🔢 **序號：{n}**")
                    perm_final[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                   index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                   key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        # --- 4. 啟動自動排班 ---
        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            
            for attempt in range(500):
                res = {n: [""] * num_days for n in display_names}
                
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)

                total_off_counts = {n: 0 for n in full_time_names}
                
                for d in range(num_days):
                    for n in full_time_names:
                        v = bg_vacation[n][d]
                        if v == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                        else:
                            prev = res[n][d-1] if d > 0 else history_final[n]
                            if prev == "N" and v not in ["D", "E", "N"]:
                                res[n][d] = "v"
                                total_off_counts[n] += 1

                valid_month = True
                for d in range(num_days):
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": 
                            target["D"] -= 1
                    
                    pool = [n for n in full_time_names if res[n][d] not in ["off", "v"]]
                    
                    real_day = d + 1
                    current_week_start_idx = (d // 7) * 7
                    if real_day % 7 == 0:
                        for n in full_time_names:
                            if n not in pool: continue
                            has_off_this_week = any(res[n][w_d] in ["off", "v", "R"] for w_d in range(current_week_start_idx, d))
                            if not has_off_this_week:
                                res[n][d] = "off"
                                total_off_counts[n] += 1
                                if n in pool: pool.remove(n)

                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0:
                                res[n][d] = v
                                target[v] -= 1
                                pool.remove(n)
                            else:
                                valid_month = False

                    random.shuffle(pool)
                    pool.sort(key=lambda x: total_off_counts[x], reverse=True)

                    for shift in ["N", "E", "D"]:
                        qualified = [n for n in pool if shift in perm_final[n]]
                        for _ in range(max
