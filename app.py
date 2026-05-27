import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析與格式防呆 (完全改用名字識別) ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    
    start_row = 0
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    headers_row = df.iloc[start_row].tolist()
    
    hist_col_idx = -1
    streak_col_idx = -1
    for idx, h in enumerate(headers_row):
        h_str = str(h).strip()
        if "系統接續_最後班別" in h_str: hist_col_idx = idx
        if "系統接續_連續天數" in h_str: streak_col_idx = idx

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        c0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        c1 = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        c2 = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        combined_text = f"{c0}{c1}{c2}"
        if any(k in combined_text for k in ["---", "每日人力", "總人數", "核對", "白班", "小夜", "大夜", "下月接續", "統計", "合計"]):
            continue

        staff_name = ""
        for cell_val in [c2, c1, c0]:
            if cell_val and not cell_val.replace(".0", "").isdigit() and "半職" not in cell_val and cell_val != "nan":
                staff_name = cell_val
                break
        
        if not staff_name: 
            continue
            
        pure_name = re.sub(r'[\s\u3000]', '', staff_name)
        is_pt = (pure_name == "郭珍君")
        
        pure_perm = "DEN"
        for p_check in [c0, c1]:
            p_check_upper = str(p_check).upper()
            if any(s in p_check_upper for s in ["D", "E", "N"]) and not str(p_check).replace(".0", "").isdigit():
                pure_perm = p_check_upper
                break

        last_day = "off"
        loaded_streak = 0

        if hist_col_idx != -1 and hist_col_idx < len(row) and pd.notna(row.iloc[hist_col_idx]):
            last_day = str(row.iloc[hist_col_idx]).strip()
        if streak_col_idx != -1 and streak_col_idx < len(row) and pd.notna(row.iloc[streak_col_idx]):
            try: loaded_streak = int(float(row.iloc[streak_col_idx]))
            except: loaded_streak = 0

        if last_day not in ["D", "E", "N", "off", "v", "R"]: last_day = "off"

        configs[pure_name] = {
            "perm": pure_perm,
            "last_day": last_day,
            "streak": loaded_streak,
            "is_part_time": is_pt
        }
    return configs

# --- 2. 區塊循環排班核心演算法 ---
def schedule_part_time(num_days):
    for _ in range(1000):
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

def schedule_full_time_blocks(num_days, max_off_target):
    work_target = num_days - max_off_target
    for _ in range(1500):
        days = ["off"] * num_days
        current_idx = random.randint(0, 1)
        total_work_assigned = 0
        
        while total_work_assigned < work_target and current_idx < num_days:
            rem = work_target - total_work_assigned
            if rem >= 5:
                block = random.randint(2, 5)
            elif rem >= 2:
                block = random.randint(2, rem)
            else:
                block = rem
                
            if current_idx + block > num_days:
                break
                
            for i in range(block):
                days[current_idx + i] = "WORK"
                
            total_work_assigned += block
            current_idx += block + random.randint(1, 3)
            
        if days.count("WORK") == work_target:
            days_str = "".join(["1" if d == "WORK" else "0" for d in days])
            if "010" not in days_str and "111111" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    backup_days = []
    pattern = ["WORK", "WORK", "WORK", "WORK", "off", "off"]
    for i in range(num_days):
        backup_days.append(pattern[i % len(pattern)])
    return backup_days


st.title("🏥 護理排班系統 (智慧欄位修正版)")

with st.sidebar:
    st.header("📂 檔案上傳與日期設定")
    start_date = st.date_input("排班開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("排班結束日期", datetime.date(2026, 6, 30))
    
    if start_date <= end_date:
        date_objects = [start_date + datetime.timedelta(days=x) for x in range((end_date - start_date).days + 1)]
        num_days = len(date_objects)
        date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in date_objects]
        st.info(f"📅 本次排班共計：{num_days} 天")
    else:
        st.error("⚠️ 錯誤：結束日期不能早於開始日期！")
        num_days = 0

    file_a = st.file_uploader("1. 上傳【班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])

if file_a and file_b and num_days > 0:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        
        full_time_names = sorted([n for n in all_names if not staff_configs[n]["is_part_time"]])
        part_time_names = [n for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        # 智慧切換頁籤
        xl = pd.ExcelFile(file_b)
        target_sheet = xl.sheet_names[0]
        for sheet in xl.sheet_names:
            if "範本" in sheet or "預排" in sheet or len(xl.sheet_names) > 1 and sheet != xl.sheet_names[0]:
                target_sheet = sheet
                break
        df_b = pd.read_excel(file_b, sheet_name=target_sheet, header=None)
        
        # --- ⚡ 關鍵修正：智慧動態錨定姓名欄與日期起點 ⚡ ---
        name_col_idx = 2  # 預設為第三欄 (C欄)
        date_start_col_idx = 3 # 預設為第四欄 (D欄)
        
        # 掃描前 10 列，找出哪一欄寫了「姓名」，並找出數字 1 (代表1號) 在哪裡
        found_anchor = False
        for r in range(min(10, len(df_b))):
            row_vals = [str(v).strip() for v in df_b.iloc[r].values]
            if "姓名" in row_vals:
                name_col_idx = row_vals.index("姓名")
                # 在同一列往後找第一個出現 "1" 或 "1.0" 的欄位
                for c_idx in range(name_col_idx + 1, len(row_vals)):
                    if row_vals[c_idx] in ["1", "1.0"]:
                        date_start_col_idx = c_idx
                        found_anchor = True
                        break
            if found_anchor: break

        bg_vacation = {n: [""] * num_days for n in display_names}
        
        for i in range(len(df_b)):
            # 動態根據剛剛找到的 name_col_idx 取出姓名
            raw_b_name = str(df_b.iloc[i, name_col_idx]) if name_col_idx < len(df_b.columns) else ""
            b_name = re.sub(r'[\s\u3000]', '', raw_b_name)
            
            # 去除可能殘留的職級文字 (例如 "李雅慧PN3" 轉化為能與 "李雅慧" 比對)
            matched_name = None
            for n in display_names:
                if n in b_name or b_name in n:
                    matched_name = n
                    break
            
            if matched_name:
                for d in range(num_days):
                    # 動態根據剛剛找到的 date_start_col_idx 往後推算日期
                    col_pos = date_start_col_idx + d
                    val = str(df_b.iloc[i, col_pos]).strip().upper() if col_pos < len(df_b.columns) else ""
                    if val in ["D", "E", "N"]: 
                        if matched_name not in part_time_names:
                            bg_vacation[matched_name][d] = val
                    elif val in ["OFF", "R", "V", "開會"] or pd.isna(df_b.iloc[i, col_pos]) or val == "NAN" or val == "":
                        bg_vacation[matched_name][d] = "R"

        st.success(f"✅ 成功辨識全科共 {len(display_names)} 位人員。欄位智慧錨定：【姓名】位於第 {name_col_idx+1} 欄，【1號】位於第 {date_start_col_idx+1} 欄。")

        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"👤 **同仁姓名：{n}**")
                    raw_perm = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    perm_final[n] = raw_perm.strip().upper().replace(",", "").replace(" ", "")
                    if not perm_final[n]: perm_final[n] = "DEN"
                    
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                   index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                   key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, int(staff_configs[n]["streak"]), key=f"c_{n}")

        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row = {}
            next_month_streak_row = {}
            
            ft_off_target = 9 if num_days >= 31 else 8
            
            for attempt in range(2000):
                valid_month = True
                res = {k: [""] * num_days for k in display_names}
                
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)
                
                ft_block_skeletons = {}
                for ft_name in full_time_names:
                    ft_block_skeletons[ft_name] = schedule_full_time_blocks(num_days, ft_off_target)

                total_off_counts = {n: 0 for n in full_time_names}
                
                for d in range(num_days):
                    if not valid_month: break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    pool = []
                    for n in full_time_names:
                        if ft_block_skeletons[n][d] == "WORK":
                            pool.append(n)
                        else:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                    
                    for n in pool.copy():
                        if bg_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                    
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[n]:
                                res[n][d] = v
                                target[v] -= 1
                                pool.remove(n)
                            else:
                                valid_month = False 
                    
                    if not valid_month: break
                    random.shuffle(pool)
                    
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in perm_final[n]:
                                prev_1 = res[n][d-1] if d > 0 else history_final[n]
                                prev_2 = res[n][d-2] if d > 1 else "off"
                                if shift == "D" and (prev_1 in ["N", "E"] or prev_2 == "N"): continue
                                if shift == "E" and prev_1 == "N": continue
                                qualified.append(n)
                                
                        for _ in range(max(0, target[shift])):
                            if qualified:
                                chosen = qualified.pop(0)
                                res[chosen][d] = shift
                                pool.remove(chosen)
                            else:
                                valid_month = False
                                break
                        if not valid_month: break
                                
                    for n in pool:
                        if target["D"] > 0:
                            res[n][d] = "D"
                            target["D"] -= 1
                        else:
                            valid_month = False

                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] != ft_off_target:
                            valid_month = False; break

                if valid_month:
                    final_res = {k: v for k, v in res.items()}
                    for n in display_names:
                        next_month_history_row[n] = res[n][-1]
                        s_count = 0
                        for cell_b in reversed(res[n]):
                            if cell_b in ["D", "E", "N"]: s_count += 1
                            else: break
                        next_month_streak_row[n] = s_count
                    success_schedule = True
                    break
            
            if not success_schedule or not final_res:
                st.error("⚠️ 原始純區塊條件非常嚴格。請確保預排休表中每日空白放假人數控制在4人以內（不含郭珍君），確認後再次嘗試！")
            else:
                st.success("🎉 純區塊循環班表成功產出！已自動相容新編排的欄位。")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                
                def count_off_days(row):
                    return sum(1 for cell in row if str(cell).lower() in ["off", "v", "r"])
                
                final_df["總休假天數"] = final_df.apply(count_off_days, axis=1)
                final_df["系統接續_最後班別"] = [next_month_history_row[n] for n in display_names]
                final_df["系統接續_連續天數"] = [next_month_streak_row[n] for n in display_names]
                
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
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    download_df.to_excel(w, sheet_name="2F綜合建議班表")
                    
                st.markdown("---")
                st.subheader("📥 完整排班結果輸出")
                st.download_button(
                    label="📥 下載完整 Excel 班表", 
                    data=out.getvalue(), 
                    file_name=f"2F_Schedule_Final_{start_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                st.balloons()

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
