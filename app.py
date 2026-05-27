import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

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

# 半職人員：固定上10天，2-3天連續班
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

st.title("🏥 護理排班系統")

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
            
            ft_off_target = 9 if num_days >= 31 else 8
            
            for attempt in range(1500):
                valid_month = True
                res = {str(n): [""] * num_days for n in display_names}
                
                # 1. 半職先走區塊
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)

                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): int(cont_days_final[n]) for n in full_time_names}
                off_streak_tracker = {str(n): 0 for n in full_time_names} # 追蹤正職連續休假
                
                # 2. 逐日滾動（動態落實 2-5天連班 與 禁碎班防線）
                for d in range(num_days):
                    if not valid_month: break
                    
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    # 昨天的斷班狀況重置
                    if d > 0:
                        for n in full_time_names:
                            if res[n][d-1] in ["off", "v", "R"]:
                                streak_tracker[n] = 0
                            else:
                                off_streak_tracker[n] = 0

                    pool = [str(n) for n in full_time_names]
                    
                    # 【強制熔斷 1】：滿 5 連班者今天必須休假
                    for n in pool.copy():
                        if streak_tracker[n] >= 5:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            off_streak_tracker[n] += 1
                            pool.remove(n)

                    # 【強制熔斷 2】：個人指定預假 (R 班強制轉 off)
                    for n in pool.copy():
                        if bg_vacation[n][d] == "R":
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            off_streak_tracker[n] += 1
                            pool.remove(n)

                    # 【強制熔斷 3】：為了防止正職上「單天碎班」(010)，如果昨天休假，今天上了一天，明天又遇到指定預假R，今天就必須直接一起休！
                    for n in pool.copy():
                        prev_is_off = (res[n][d-1] in ["off", "v", "R"]) if d > 0 else (history_final[n] in ["off", "v", "R"])
                        next_must_off = (bg_vacation[n][d+1] == "R") if d < (num_days - 1) else False
                        if prev_is_off and next_must_off:
                            res[n][d] = "off"
                            total_off_counts[n] += 1
                            off_streak_tracker[n] += 1
                            pool.remove(n)

                    # 【強制熔斷 4】：為了確保連班至少 2 天，如果「昨天休假」且「今天被強迫推入 pool 要上班」，除非他明天也能上班，否則不准上單天班
                    # 我們這裡透過後面的分派與排序來優先滿足

                    # 填入特定指定預班 (D/E/N)
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[n]:
                                # 檢查花班
                                prev_1 = res[n][d-1] if d > 0 else history_final[n]
                                if v == "D" and prev_1 in ["N", "E"]: 
                                    valid_month = False; break
                                
                                res[n][d] = v
                                target[v] -= 1
                                streak_tracker[n] += 1
                                pool.remove(n)
                            else:
                                valid_month = False
                    
                    if not valid_month: break

                    # 排序池子：
                    # 1. 昨天已經在上連班的人優先繼續上（滿足2-5天連班）
                    # 2. 目前總休假落後（假拿太少）的人，今天優先給予 off 
                    random.shuffle(pool)
                    pool.sort(key=lambda x: (streak_tracker[x] > 0, total_off_counts[x]), reverse=True)

                    needed_slots = sum(max(0, target[s]) for s in ["N", "E", "D"])
                    
                    # 開始分派
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
                                streak_tracker[chosen] += 1
                                pool.remove(chosen)
                            else:
                                valid_month = False
                                break
                                
                    # 剩下沒分到班的人，今天全部轉 off
                    for n in pool:
                        res[n][d] = "off"
                        total_off_counts[n] += 1
                        off_streak_tracker[n] += 1

                # 3. 最終大檢驗：正職總休假天數達標、且「絕對不上單天班 (010)」
                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] != ft_off_target:
                            valid_month = False; break
                        
                        # 轉成 01 字串做嚴格碎班與超長連班檢查
                        days_str = "".join(["0" if res[n][x] in ["off", "v", "R"] else "1" for x in range(num_days)])
                        if "010" in days_str or "111111" in days_str or days_str.startswith("10") or days_str.endswith("01"):
                            valid_month = False; break

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
                st.error("⚠️ 當前各人員的預約假過於密集。在死鎖每日人力與『正職不上單天班』的限制下本輪未能配出。請再次點擊按鈕重試，或稍微微調預班表再試一次！")
            else:
                st.success("🎉 全新滾動塊狀演算法排班成功！已為你完美排定正職 2-5 天連班，且絕無單天碎班！")
                
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
                    file_name=f"2F_Schedule_Final_{start_date}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
                st.balloons()

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
