import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析與格式防呆（地毯式無條件白名單掃描，保證 100% 抓全所有人） ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    # 定位包含「姓名」或「職級」的標頭起始行
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    headers_row = df.iloc[start_row].tolist()
    
    # 自動尋找橫向架構中埋在右側的接續資料欄位 index
    hist_col_idx = -1
    streak_col_idx = -1
    for idx, h in enumerate(headers_row):
        h_str = str(h).strip()
        if "系統接續_最後班別" in h_str: hist_col_idx = idx
        if "系統接續_連續天數" in h_str: streak_col_idx = idx

    # 逐列讀取人員名單
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        # 抓取前三個欄位文字進行大數據掃描
        c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        c1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        c2 = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 【強力過濾防線 1】只要這一行含有任何總人數核對的統計中文字，當場整行丟棄！
        combined_text = f"{c0}{c1}{c2}"
        if any(k in combined_text for k in ["---", "每日人力", "總人數", "核對", "白班", "小夜", "大夜", "下月接續", "統計"]):
            continue
        if "星期" in combined_text or "姓名" in combined_text:
            continue

        # 【地毯式白名單判定】只要前三欄裡面有任何一格是 1~13 的數字，或者寫著「半職」，他就是我們要的人！
        is_valid_staff = False
        target_label = ""
        staff_name = ""
        
        for cell_val in [c0, c1, c2]:
            clean_cell = cell_val.replace(".0", "")
            if clean_cell.isdigit() and 1 <= int(clean_cell) <= 13:
                is_valid_staff = True
                target_label = clean_cell
                break
            elif "半職" in cell_val:
                is_valid_staff = True
                target_label = "半職1"
                break
                
        if not is_valid_staff:
            continue

        for cell_val in [c2, c1, c0]:
            if cell_val and not cell_val.replace(".0", "").isdigit() and "半職" not in cell_val and cell_val != "nan":
                staff_name = cell_val
                break
        if not staff_name: staff_name = target_label

        display_label = target_label
        is_pt = "半職" in display_label
        
        # 權限相容防呆
        pure_perm = "DEN"
        for p_check in [c0, c1]:
            p_check_upper = p_check.upper()
            if any(s in p_check_upper for s in ["D", "E", "N"]) and not p_check.replace(".0", "").isdigit():
                pure_perm = p_check_upper
                break

        # 3. 決定銜接狀態與連續上班天數
        last_day = "off"
        loaded_streak = 0

        if hist_col_idx != -1 and hist_col_idx < len(row) and pd.notna(row.iloc[hist_col_idx]):
            last_day = str(row.iloc[hist_col_idx]).strip()
        if streak_col_idx != -1 and streak_col_idx < len(row) and pd.notna(row.iloc[streak_col_idx]):
            try: loaded_streak = int(float(row.iloc[streak_col_idx]))
            except: loaded_streak = 0
            
        if last_day == "off" and loaded_streak == 0:
            valid_cells = [str(c).strip().upper() for c in row.values[3:] if pd.notna(c) and str(c).strip().upper() in ["D", "E", "N", "OFF", "V", "R"]]
            if valid_cells:
                pure_shifts = [c for c in valid_cells if c in ["D", "E", "N", "OFF", "V", "R"] and not c.isdigit()][:31]
                if pure_shifts:
                    last_c = pure_shifts[-1]
                    last_day = last_c if last_c in ["D", "E", "N", "R"] else last_c.lower()
                    
                    s_count = 0
                    for cell_val in reversed(pure_shifts):
                        if cell_val in ["D", "E", "N"]: s_count += 1
                        else: break
                    loaded_streak = s_count

        if last_day not in ["D", "E", "N", "off", "v", "R"]: last_day = "off"
        pure_id = re.sub(r'[\s\u3000]', '', staff_name)

        configs[display_label] = {
            "pure_id": pure_id,
            "perm": pure_perm,
            "last_day": last_day,
            "streak": loaded_streak,
            "is_part_time": is_pt
        }
    return configs

# --- 2. 半職專用排班演算 ---
def schedule_part_time(num_days):
    for _ in range(100):
        days = ["off"] * num_days
        available_patterns = [[2, 2, 2, 2, 2], [3, 3, 2, 2], [3, 2, 3, 2], [2, 3, 2, 3], [2, 2, 3, 3]]
        work_blocks = random.choice(available_patterns)
        random.shuffle(work_blocks) 
        
        current_idx = random.randint(0, 2) 
        success = True
        
        for block in work_blocks:
            if current_idx + block > num_days:
                success = False
                break
            for _ in range(block):
                if current_idx < num_days:
                    days[current_idx] = "D"
                    current_idx += 1
            current_idx += random.randint(2, 4)
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    backup_days = ["off"] * num_days
    for idx in [2, 3, 4, 9, 10, 15, 16, 17, 22, 23]:
        if idx < num_days: backup_days[idx] = "D"
    return backup_days

st.title("🏥 2F 護理排班系統")

# --- 3. 側邊欄日期與檔案設定 ---
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

    file_a = st.file_uploader("1. 上傳【班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】", type=["xlsx"])

if file_a and file_b and num_days > 0:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        
        full_time_names = sorted([n for n in all_names if not staff_configs[n]["is_part_time"]], key=lambda x: int(x))
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
                        if val in ["R", "OFF", "V", "開會", "0", "●", "公假", "特休"]: bg_vacation[n][d] = "R"
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 成功辨識全科共 {len(display_names)} 位人員。")

        # --- 核對區 ---
        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"🔢 **人員序號：{n}**")
                    raw_perm = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    perm_final[n] = raw_perm.strip().upper().replace(",", "").replace(" ", "")
                    if not perm_final[n]: perm_final[n] = "DEN"
                    
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                   index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                   key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, int(staff_configs[n]["streak"]), key=f"c_{n}")

        # --- 4. 啟動自動排班 ---
        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row = {}
            next_month_streak_row = {}
            
            for attempt in range(500):
                # 【核心修復點 1】valid_month 的最高起點必須死死鎖在 attempt 迴圈的最頂端
                valid_month = True
                
                res = {n: [""] * num_days for n in display_names}
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)

                total_off_counts = {n: 0 for n in full_time_names}
                streak_tracker = {n: int(cont_days_final[n]) for n in full_time_names}
                
                # --- 大夜班（N）跨月預約隔斷處理（短路保護鎖） ---
                for n in full_time_names:
                    if history_final[n] == "N":
                        if num_days > 0 and bg_vacation[n][0] == "D": valid_month = False
                        if num_days > 1 and bg_vacation[n][1] == "D": valid_month = False
                
                if not valid_month:
                    continue

                for d in range(num_days):
                    if not valid_month: 
                        break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    pool = [n for n in full_time_names if res[n][d] not in ["off", "v"]]
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[n][d-1] in ["off", "v", "R"]:
                                streak_tracker[n] = 0

                    # 5連班過勞防呆
                    for n in pool.copy():
                        if streak_tracker[n] >= 5: 
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            if n in pool: pool.remove(n)

                    # 阻斷單天班 (不上單天班)
                    for n in pool.copy():
                        prev_is_off = (res[n][d-1] in ["off", "v", "R"]) if d > 0 else (history_final[n] in ["off", "v", "R"])
                        next_is_off = (bg_vacation[n][d+1] == "R") if d < (num_days - 1) else False
                        if prev_is_off and next_is_off:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            if n in pool: pool.remove(n)

                    # 每週一休檢查
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

                    # 處理預約班別（含 N 接 D 間隔兩天防呆）
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0:
                                prev_1 = res[n][d-1] if d > 0 else history_final[n]
                                prev_2 = res[n][d-2] if d > 1 else "off"
                                
                                if (prev_1 == "N" or prev_2 == "N") and v == "D":
                                    valid_month = False
                                elif prev_1 == "E" and v == "D":
                                    valid_month = False
                                else:
                                    res[n][d] = v
                                    target[v] -= 1
                                    streak_tracker[n] += 1
                                    pool.remove(n)
                            else:
                                valid_month = False

                    if not valid_month: 
                        break

                    # 動態融斷
                    needed_slots = sum(max(0, target[s]) for s in ["N", "E", "D"])
                    if len(pool) < needed_slots:
                        while len(pool) < (target["N"] + target["E"] + target["D"]):
                            if target["D"] > 0: target["D"] -= 1
                            elif target["E"] > 0: target["E"] -= 1
                            elif target["N"] > 0: target["N"] -= 1
                            else: break

                    random.shuffle(pool)
                    pool.sort(key=lambda x: total_off_counts[x], reverse=True)

                    # 系統自動分派班別
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in perm_final[n]:
                                prev_1 = res[n][d-1] if d > 0 else history_final[n]
                                prev_2 = res[n][d-2] if d > 1 else "off"
                                
                                if shift == "D" and (prev_1 == "N" or prev_2 == "N"): continue
                                if shift == "D" and prev_1 == "E": continue
                                    
                                qualified.append(n)
                                    
                        for _ in range(max(0, target[shift])):
                            if qualified:
                                chosen = qualified.pop(0)
                                res[chosen][d] = shift
                                streak_tracker[chosen] += 1
                                if chosen in pool: pool.remove(chosen)
                    
                    for n in pool:
                        res[n][d] = "off"
                        total_off_counts[n] += 1
                        
                # 【核心修復點 2】將最終單天班大檢驗移到每日排班結束後，若不通過則果斷重新碰撞
                if valid_month:
                    for n in full_time_names:
                        days_str = "".join(["0" if res[n][x] in ["off", "v", "R"] else "1" for x in range(num_days)])
                        if "010" in days_str or days_str.startswith("10") or days_str.endswith("01"):
                            valid_month = False
                            break

                if valid_month and all(total_off_counts[n] >= 8 for n in full_time_names):
                    final_res = res
                    for n in display_names:
                        next_month_history_row[n] = res[n][-1]
                        s_count = 0
                        for cell_b in reversed(res[n]):
                            if cell_b in ["D", "E", "N"]: s_count += 1
                            else: break
                        if s_count == num_days and res[n][0] in ["D", "E", "N"]:
                            s_count += int(cont_days_final[n])
                        next_month_streak_row[n] = s_count
                    success_schedule = True
                    break
            
            if not success_schedule:
                st.error("⚠️ 當前各人員的預約假過於密集。在鎖定4D/3E/2N人力與『正職不上單天班』的法規限制下本輪未能配出。請重試或微調預班表再按一次！")
            else:
                st.success("🎉 排班大成功！已通過所有防呆安全規範（無花班、不上單天班、大夜隔開2天）。")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers
                
                # 橫向統計
                def count_off_days(row):
                    return sum(1 for cell in row if str(cell).lower() in ["off", "v", "r"])
                    
                final_df["總休假天數"] = final_df.apply(count_off_days, axis=1)
                final_df["系統接續_最後班別"] = [next_month_history_row[n] for n in final_df.index]
                final_df["系統接續_連續天數"] = [next_month_streak_row[n] for n in final_df.index]
                
                # 縱向統計
                stat_rows = {}
                for header in date_headers:
                    col_data = final_df[header]
                    count_d = sum(1 for cell in col_data if str(cell).upper() == "D")
                    count_e = sum(1 for cell in col_data if str(cell).upper() == "E")
                    count_n = sum(1 for cell in col_data if str(cell).upper() == "N")
                    stat_rows[header] = {"白班": count_d, "小夜": count_e, "大夜": count_n}
                df_stats = pd.DataFrame(stat_rows)
                
                st.subheader("🎉 最終排班結果")
                st.dataframe(final_df, use_container_width=True)
                
                df_stats_extended = df_stats.copy()
                df_stats_extended["總休假天數"] = ""
                df_stats_extended["系統接續_最後班別"] = ""
                df_stats_extended["系統接續_連續天數"] = ""
                
                empty_row = pd.Series([None] * len(final_df.columns), index=final_df.columns)
                
                download_df = pd.concat([
                    final_df,
                    pd.DataFrame([empty_row], columns=final_df.columns),
                    pd.DataFrame([["--- 每日人力總人數核對 ---"] + [""] * (len(final_df.columns)-1)], columns=final_df.columns),
                    df_stats_extended
                ])

                out = BytesIO()
                with pd.ExcelWriter(out) as w: 
                    download_df.to_excel(w, sheet_name="2F綜合建議班表")
                    
                st.download_button(
                    label="📥 下載【高階連班優化版】合併 Excel 檔", 
                    data=out.getvalue(), 
                    file_name=f"2F_Schedule_Final_{start_date}.xlsx",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
