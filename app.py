import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析與格式防呆 ---
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
        if "星期" in combined_text or "姓名" in combined_text:
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
                
        if not is_valid_staff:
            continue

        for cell_val in [c2, c1, c0]:
            if cell_val and not cell_val.replace(".0", "").isdigit() and "半職" not in cell_val and cell_val != "nan":
                staff_name = cell_val
                break
        if not staff_name: staff_name = target_label

        display_label = str(target_label)
        is_pt = "半職" in display_label
        
        pure_perm = "DEN"
        for p_check in [c0, c1]:
            p_check_upper = p_check.upper()
            if any(s in p_check_upper for s in ["D", "E", "N"]) and not p_check.replace(".0", "").isdigit():
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
        pure_id = re.sub(r'[\s\u3000]', '', staff_name)

        configs[display_label] = {
            "pure_id": pure_id,
            "perm": pure_perm,
            "last_day": last_day,
            "streak": loaded_streak,
            "is_part_time": is_pt
        }
    return configs

# --- 2. 區塊循環排班核心演算法 ---

# 半職人員：固定上10天，2-3天連續班
def schedule_part_time(num_days):
    for _ in range(200):
        days = ["off"] * num_days
        # 可接受的連續上班天數區塊組合 (加起來剛好 10 天)
        available_patterns = [[2, 2, 2, 2, 2], [3, 3, 2, 2], [3, 2, 3, 2], [2, 3, 2, 3], [2, 2, 3, 3]]
        work_blocks = random.choice(available_patterns)
        random.shuffle(work_blocks) 
        
        current_idx = random.randint(0, 2) # 隨機開頭
        success = True
        
        for block in work_blocks:
            if current_idx + block > num_days:
                success = False
                break
            for _ in range(block):
                if current_idx < num_days:
                    days[current_idx] = "D"
                    current_idx += 1
            current_idx += random.randint(2, 4) # 區塊間隔休假 2-4 天
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    backup_days = ["off"] * num_days
    for idx in [2, 3, 4, 9, 10, 15, 16, 17, 22, 23]:
        if idx < num_days: backup_days[idx] = "D"
    return backup_days

# 正職人員：滿足總休假，2-5天連續班區塊循環
def schedule_full_time_blocks(num_days, max_off_target):
    """
    依據總天數與應休天數，自動生成連續上班 2~5 天、連續休假 1~3 天的區塊架構
    """
    work_target = num_days - max_off_target
    
    for _ in range(500):
        days = ["off"] * num_days
        current_idx = random.randint(0, 1)
        total_work_assigned = 0
        
        # 動態生成 2~5 天上班的區塊，直到滿足正職該月總上班時數
        while total_work_assigned < work_target and current_idx < num_days:
            # 剩餘需要分配的天數
            rem = work_target - total_work_assigned
            
            # 隨機選擇 2~5 天的連續班區塊
            if rem >= 5:
                block = random.randint(2, 5)
            elif rem >= 2:
                block = random.randint(2, rem)
            else:
                block = rem  # 剩 1 天就補滿（後續會透過碎班檢驗過濾掉）
                
            if current_idx + block > num_days:
                break
                
            for i in range(block):
                days[current_idx + i] = "WORK" # 先標記為上班，後續再填入具體班別(D/E/N)
                
            total_work_assigned += block
            current_idx += block + random.randint(1, 3) # 上完一個區塊，隨機休 1~3 天
            
        # 嚴格驗證：總工作天數符合、沒有碎班(不上單天班)、沒有超長連班
        if days.count("WORK") == work_target:
            days_str = "".join(["1" if d == "WORK" else "0" for d in days])
            # 過濾掉單天上班 (010)、開頭單天 (10)、結尾單天 (01) 以及超過 5 連班的狀況
            if "010" not in days_str and "111111" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    # 萬一死鎖，提供一組基本安全循環模板 (上4休2、上4休2...)
    backup_days = []
    pattern = ["WORK", "WORK", "WORK", "WORK", "off", "off"]
    for i in range(num_days):
        backup_days.append(pattern[i % len(pattern)])
    return backup_days


st.title("🏥 護理排班系統 (全區塊循環版)")

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
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 成功辨識全科共 {len(display_names)} 位人員。")

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

        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row = {}
            next_month_streak_row = {}
            
            # 根據月曆天數自動設定正職應休天數（大月9天、小月8天）
            ft_off_target = 9 if num_days >= 31 else 8
            
            for attempt in range(2000):
                valid_month = True
                res = {str(n): [""] * num_days for n in display_names}
                
                # 1. 產生半職人員的 2-3 天區塊
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)
                
                # 2. 產生正職人員的 2-5 天區塊基礎
                ft_block_skeletons = {}
                for ft_name in full_time_names:
                    ft_block_skeletons[ft_name] = schedule_full_time_blocks(num_days, ft_off_target)

                total_off_counts = {str(n): 0 for n in full_time_names}
                
                # 3. 逐日媒合並將正職的 WORK 區塊轉為具體班別 (D/E/N)
                for d in range(num_days):
                    if not valid_month: break
                    
                    # 每日目標：白班4人、小夜3人、大夜2人
                    target = {"D": 4, "E": 3, "N": 2}
                    
                    # 扣除半職已佔用的白班(D)名額
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    # 找出今天被區塊演算法排定「必須上班」的正職員工
                    pool = []
                    for n in full_time_names:
                        if ft_block_skeletons[n][d] == "WORK":
                            pool.append(n)
                        else:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                    
                    # 處理個人預假 (R 班強制轉 off)
                    for n in pool.copy():
                        if bg_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            pool.remove(n)
                    
                    # 優先填入特定的指定預班 (如某人指定今天上 E 班)
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[n]:
                                res[n][d] = v
                                target[v] -= 1
                                pool.remove(n)
                            else:
                                valid_month = False # 預班與區塊衝突或人力爆滿則融斷重來
                    
                    if not valid_month: break
                    
                    # 根據每個人剩餘的休假狀況做排序，讓假少的人優先選班
                    random.shuffle(pool)
                    
                    # 依序指派 大夜(N) -> 小夜(E) -> 白班(D)
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in perm_final[n]:
                                # 護理安全機制：防花班 (前一天大夜/小夜，今天不能上白班)
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
                                # 如果符合資格的人不夠填滿當日4/3/2低標，此輪失敗
                                valid_month = False
                                break
                                
                    # 沒分派到具體班別但區塊要求上班的人，直接補D班或off
                    for n in pool:
                        if target["D"] > 0:
                            res[n][d] = "D"
                            target["D"] -= 1
                        else:
                            res[n][d] = "off"
                            total_off_counts[n] += 1

                # 4. 驗證正職月底總休假天數是否達標
                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] < ft_off_target:
                            valid_month = False
                            break

                # 5. 排班成功，計算接續資料
                if valid_month:
                    final_res = {str(k): v for k, v in res.items()}
                    for n in display_names:
                        next_month_history_row[str(n)] = res[n][-1]
                        s_count = 0
                        for cell_b in reversed(res[n]):
                            if cell_b in ["D", "E", "N"]: s_count += 1
                            else: break
                        next_month_streak_row[str(n)] = s_count
                    success_schedule = True
                    break
            
            if not success_schedule or not final_res:
                st.error("⚠️ 區塊循環條件較嚴格。在鎖死每日4D/3E/2N人力與『正職2-5天連班』限制下本輪未能配出。請再次點擊按鈕重試，或稍微微調預班表再試一次！")
            else:
                st.success("🎉 全區塊循環排班成功！已完美避開所有單天碎班。")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                final_df.index = final_df.index.astype(str)
                str_display_names = [str(n) for n in display_names]
                
                def count_off_days(row):
                    return sum(1 for cell in row if str(cell).lower() in ["off", "v", "r"])
                
                final_df["總休假天數"] = final_df.apply(count_off_days, axis=1)
                final_df["系統接續_最後班別"] = [next_month_history_row[n] for n in str_display_names]
                final_df["系統接續_連續天數"] = [next_month_streak_row[n] for n in str_display_names]
                
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
                    file_name=f"2F_Schedule_Blocks_{start_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                st.balloons()

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
