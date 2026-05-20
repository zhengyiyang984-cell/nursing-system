import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統-跨月終極對齊版", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 背景解析與格式防呆（終極修復：精準跨月轉置讀取，隔離所有統計方塊） ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    
    # 定位包含「姓名」或「職級」的標頭起始行
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    # 【跨月對齊核心】智慧偵測：這份檔案是不是上個月系統產出的合併報表？
    has_next_month_history = False
    history_row_idx = -1
    streak_row_idx = -1
    
    for idx in range(len(df)):
        cell_val = str(df.iloc[idx, 0]).strip()
        if "下月接續_最後班別" in cell_val:
            has_next_month_history = True
            history_row_idx = idx
        if "下月接續_連續天數" in cell_val:
            streak_row_idx = idx

    # 如果是上月產出的報表，先建立一個對照字典，用來橫向提取接續資料
    excel_connect_data = {}
    if has_next_month_history:
        # 第一列（Index start_row）是標頭，也就是人員序號（1, 2, 3... 半職1）
        headers_row = df.iloc[start_row]
        for col_idx in range(1, len(df.columns)):
            h_val = str(headers_row.iloc[col_idx]).strip()
            if h_val and h_val != "nan" and "總休假" not in h_val:
                last_shift = str(df.iloc[history_row_idx, col_idx]).strip() if history_row_idx != -1 else "off"
                try:
                    streak_days = int(float(df.iloc[streak_row_idx, col_idx])) if streak_row_idx != -1 else 0
                except:
                    streak_days = 0
                excel_connect_data[h_val] = {"last_day": last_shift, "streak": streak_days}

    # 開始逐列抓取人員
    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        # 讀取基本欄位
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 雜訊過濾第一道：如果是空白列或是分隔線，直接封殺
        if (no == "" or no == "nan") and (name == "" or name == "nan"): continue
        col0_str = str(row.iloc[0]).strip()
        if "---" in col0_str or "下月接續" in col0_str: continue
        
        # 決定卡片上要顯示的人員識別證名稱（優先用序號，沒有用姓名）
        display_label = no if (no != "nan" and no != "") else name
        if display_label == "" or display_label == "nan": continue 

        # 雜訊過濾第二道：嚴格封殺任何可能出現在左側的統計關鍵字，確保幽靈卡片絕對不生成
        clean_check = display_label.replace(" ", "").upper()
        if any(k in clean_check for k in ["OFF", "R", "V", "ALL", "TOTAL", "統計", "D4", "E3", "N2", "白班", "小夜", "大夜", "每日人力", "人員"]): 
            continue
        if "---" in display_label: continue

        is_pt = "半職" in display_label or "半職" in no or "半職" in name

        # 決定衔接狀態與連續天數（防呆接軌核心）
        last_day = "off"
        loaded_streak = 0

        if has_next_month_history and display_label in excel_connect_data:
            # 方案 A：直接從上個月底埋下的「數據鏈」中隔空抓取，達成 100% 全自動銜接
            last_day = excel_connect_data[display_label]["last_day"]
            loaded_streak = excel_connect_data[display_label]["streak"]
            # 如果上個月自動輸出的權限還在，就沿用
            if perm == "DEN" or perm == "NAN" or not perm:
                perm = "DEN"
        else:
            # 方案 B：如果是一般常規空白原始班表，則走常規的倒數 5 天自動掃描邏輯
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

st.title("🏥 2F 護理排班系統 (跨月無縫接軌版)")

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

    file_a = st.file_uploader("1. 上傳【班表】(檔案 A - 支援直接投入上月結果)", type=["xlsx"])
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
                        if val in ["R", "OFF", "V", "開會", "0", "●", "公假", "特休"]: bg_vacation[n][d] = "R"
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 成功辨識 {len(display_names)} 位有效人員（已隔離報表統計區）。")

        # --- 核對區 ---
        st.subheader("⚙️ 核對權限與銜接狀態 (已自動對齊上月銜接數據)")
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
            
            for attempt in range(500):
                res = {n: [""] * num_days for n in display_names}
                
                for pt_name in part_time_names:
                    res[pt_name] = schedule_part_time(num_days)

                total_off_counts = {n: 0 for n in full_time_names}
                streak_tracker = {n: int(cont_days_final[n]) for n in full_time_names}
                
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

                    # 處理預約班別
                    for n in pool.copy():
                        v = bg_vacation[n][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0:
                                prev = res[n][d-1] if d > 0 else history_final[n]
                                if prev == "E" and v == "D":
                                    valid_month = False
                                else:
                                    res[n][d] = v
                                    target[v] -= 1
                                    streak_tracker[n] += 1
                                    pool.remove(n)
                            else:
                                valid_month = False

                    # 動態融斷機制
                    needed_slots = sum(max(0, target[s]) for s in ["N", "E", "D"])
                    if len(pool) < needed_slots:
                        while len(pool) < (target["N"] + target["E"] + target["D"]):
                            if target["D"] > 0: target["D"] -= 1
                            elif target["E"] > 0: target["E"] -= 1
                            elif target["N"] > 0: target["N"] -= 1
                            else: break

                    random.shuffle(pool)
                    pool.sort(key=lambda x: total_off_counts[x], reverse=True)

                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in pool:
                            if shift in perm_final[n]:
                                prev = res[n][d-1] if d > 0 else history_final[n]
                                if not (prev == "E" and shift == "D"):
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
                        
                if valid_month and all(total_off_counts[n] >= 8 for n in full_time_names):
                    final_res = res
                    next_month_history_row = {}
                    next_month_streak_row = {}
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
                st.error("⚠️ 無法算出符合安全防呆與休假規定的班表。請嘗試重試或放寬權限。")
            else:
                st.success("🎉 排班成功！已成功注入並導出下月無縫接軌數據鏈。")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers
                
                # 橫向統計
                def count_off_days(row):
                    return sum(1 for cell in row if str(cell).lower() in ["off", "v", "r"])
                final_df["總休假天數"] = final_df.apply(count_off_days, axis=1)
                
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
                
                # 合併上下拼接
                export_df = final_df.copy()
                empty_row = pd.Series([None] * len(export_df.columns), index=export_df.columns)
                df_stats_extended = df_stats.copy()
                df_stats_extended["總休假天數"] = "" 
                
                # 建立接續資料行
                df_next_connect = pd.DataFrame(columns=export_df.columns)
                history_list = [next_month_history_row[n] for n in display_names] + [""]
                streak_list = [next_month_streak_row[n] for n in display_names] + [""]
                df_next_connect.loc["下月接續_最後班別"] = history_list
                df_next_connect.loc["下月接續_連續天數"] = streak_list
                
                # 最終大拼裝
                download_df = pd.concat([
                    export_df,
                    pd.DataFrame([empty_row, empty_row], columns=export_df.columns), 
                    pd.DataFrame([["--- 每日人力總人數核對 ---"] + [""] * (len(export_df.columns)-1)], columns=export_df.columns), 
                    df_stats_extended,
                    pd.DataFrame([empty_row, empty_row], columns=export_df.columns), 
                    pd.DataFrame([["--- 下月接續專用區 (系統自動識別，請勿刪除) ---"] + [""] * (len(export_df.columns)-1)], columns=export_df.columns),
                    df_next_connect
                ])

                out = BytesIO()
                with pd.ExcelWriter(out) as w: 
                    download_df.to_excel(w, sheet_name="2F綜合建議班表")
                    
                st.download_button(
                    label="📥 下載【相容下月接軌+人數核對】合併 Excel 檔", 
                    data=out.getvalue(), 
                    file_name=f"2F_Schedule_Final_{start_date}.xlsx",
                    use_container_width=True
                )

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
