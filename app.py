import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        c1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        c2 = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        combined_text = f"{c0}{c1}{c2}"
        if any(k in combined_text for k in ["---", "每日人力", "總人數", "核對", "白班", "小夜", "大夜", "下月接續", "統計", "合計"]):
            continue

        is_valid_staff = False
        target_label = ""
        staff_name = ""
        
        for cell_val in [c0, c1, c2]:
            clean_cell = cell_val.replace(".0", "")
            if clean_cell.isdigit() and 1 <= int(clean_cell) <= 13:
                is_valid_staff = True
                target_label = str(clean_cell)
                break
            elif "半職" in cell_val:
                is_valid_staff = True
                target_label = "半職1"
                break
                
        if not is_valid_staff: continue

        for cell_val in [c2, c1, c0]:
            if cell_val and not cell_val.replace(".0", "").isdigit() and "半職" not in cell_val and cell_val != "nan":
                staff_name = cell_val
                break
        if not staff_name: staff_name = target_label

        display_label = str(target_label)
        is_pt = "半職" in display_label or "13" in display_label
        
        pure_perm = "DEN"
        for p_check in [c0, c1]:
            p_check_upper = p_check.upper()
            if any(s in p_check_upper for s in ["D", "E", "N"]) and not p_check.replace(".0", "").isdigit():
                pure_perm = p_check_upper
                break

        configs[display_label] = {
            "pure_id": re.sub(r'[\s\u3000]', '', staff_name),
            "perm": pure_perm,
            "last_day": "off",
            "streak": 0,
            "is_part_time": is_pt
        }
    return configs

def schedule_part_time(num_days):
    # 半職固定上10天
    days = ["off"] * num_days
    # 優先把半職排在非連假期間，釋放連假人力
    available_days = [i for i in range(num_days) if i not in [18, 19, 20]] # 避開6/19~6/21
    random.shuffle(available_days)
    for idx in available_days[:10]:
        days[idx] = "D"
    return days

st.title("🏥 護理排班系統 (精準調度版)")

with st.sidebar:
    st.header("📂 檔案上傳與日期設定")
    today = datetime.date.today()
    start_date = st.date_input("排班開始日期", today.replace(day=1))
    end_date = st.date_input("排班結束日期", today.replace(day=30))
    
    if start_date <= end_date:
        date_objects = [start_date + datetime.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        num_days = len(date_objects)
        date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in date_objects]
        st.info(f"📅 本次排班共計：{num_days} 天")
    else:
        st.error("⚠️ 錯誤：結束日期不能早於開始日期！")
        num_days = 0

    file_a = st.file_uploader("1. 上傳【班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】", type=["xlsx"])

if file_a and file_b and num_days > 0:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        
        full_time_names = sorted([str(n) for n in all_names if not staff_configs[n]["is_part_time"]], key=lambda x: int(x))
        part_time_names = [str(n) for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        df_b = pd.read_excel(file_b, header=None)
        bg_vacation = {n: [""] * num_days for n in display_names}
        for i in range(len(df_b)):
            b_name = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            for n in display_names:
                if staff_configs[n]["pure_id"] == b_name or n == b_name:
                    for d in range(num_days):
                        val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                        if val in ["R", "OFF", "V", "開會", "0", "●", "公假", "特休"]: bg_vacation[n][d] = "R"
                    break

        st.success(f"✅ 成功辨識全科共 {len(display_names)} 位人員。")

        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            ft_off_target = 8 # 6月30天休8天
            
            for attempt in range(5000):
                valid_month = True
                res = {str(n): [""] * num_days for n in display_names}
                
                # 半職智慧調度
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)

                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): 0 for n in full_time_names}
                
                # 連假特殊放寬機制
                allow_break_streak = (attempt > 1500)

                for d in range(num_days):
                    if not valid_month: break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[n][d-1] == "off": streak_tracker[n] = 0

                    pool = [str(n) for n in full_time_names]
                    
                    # 1. 滿 5 連班斷班
                    for n in pool.copy():
                        if streak_tracker[n] >= 5:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)

                    # 2. 處理預約假
                    for n in pool.copy():
                        if bg_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)

                    # 3. 碎班過濾（非連假期間嚴格執行）
                    if not allow_break_streak:
                        for n in pool.copy():
                            if d > 0 and d < num_days - 1:
                                if res[n][d-1] == "off" and bg_vacation[n][d+1] == "R":
                                    res[n][d] = "off"
                                    total_off_counts[n] += 1
                                    pool.remove(n)

                    random.shuffle(pool)
                    # 優先讓正在連班、或假休太多的人來上班平衡
                    pool.sort(key=lambda x: (streak_tracker[x] > 0, total_off_counts[x]), reverse=True)

                    # 指派班別
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in staff_configs[n]["perm"]:
                                prev_1 = res[n][d-1] if d > 0 else "off"
                                if shift == "D" and prev_1 in ["N", "E"]: continue
                                if shift == "E" and prev_1 == "N"]: continue
                                qualified.append(n)
                                
                        for _ in range(max(0, target[shift])):
                            if qualified:
                                chosen = qualified.pop(0)
                                res[chosen][d] = shift
                                streak_tracker[chosen] += 1
                                pool.remove(chosen)
                            else:
                                valid_month = False
                                break
                        if not valid_month: break
                                
                    for n in pool:
                        res[n][d] = "off"
                        total_off_counts[n] += 1

                # 總休假檢查
                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] != ft_off_target:
                            valid_month = False; break
                        
                        if not allow_break_streak:
                            days_str = "".join(["0" if res[n][x] == "off" else "1" for x in range(num_days)])
                            if "010" in days_str:
                                valid_month = False; break

                if valid_month:
                    final_res = res
                    success_schedule = True
                    break
            
            if not success_schedule:
                st.error("⚠️ 系統正在極限排列組合中，請再次點擊按鈕重試！")
            else:
                st.success("🎉 排班成功！已成功解開端午連假人力的極限交織。")
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers
                final_df["總休假天數"] = final_df.apply(lambda r: sum(1 for c in r if c == "off"), axis=1)
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w:
                    final_df.to_excel(w, sheet_name="2F建議班表")
                st.download_button("📥 下載 Excel 班表", data=out.getvalue(), file_name="Schedule_2F.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
