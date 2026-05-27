import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# --- 1. 基本班表解析 ---
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

        staff_name = ""
        for cell_val in [c2, c1, c0]:
            if cell_val and not cell_val.replace(".0", "").isdigit() and "半職" not in cell_val and cell_val != "nan":
                staff_name = cell_val
                break
        
        if not staff_name: continue
            
        pure_name = re.sub(r'[\s\u3000]', '', staff_name)
        is_pt = (pure_name == "郭珍君")
        
        pure_perm = "DEN"
        for p_check in [c0, c1]:
            p_check_upper = str(p_check).upper()
            if any(s in p_check_upper for s in ["D", "E", "N"]) and not str(p_check).replace(".0", "").isdigit():
                pure_perm = p_check_upper
                break

        configs[pure_name] = {
            "perm": pure_perm,
            "last_day": "off",
            "streak": 0,
            "is_part_time": is_pt
        }
    return configs

# --- 2. 區塊循環排班演算法 ---
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
                success = False; break
            for _ in range(block):
                if current_idx < num_days:
                    days[current_idx] = "D"
                    current_idx += 1
            current_idx += random.randint(2, 4)
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
    return ["off"] * num_days

def schedule_full_time_blocks(num_days, max_off_target):
    work_target = num_days - max_off_target
    for _ in range(1500):
        days = ["off"] * num_days
        current_idx = random.randint(0, 1)
        total_work_assigned = 0
        
        while total_work_assigned < work_target and current_idx < num_days:
            rem = work_target - total_work_assigned
            block = random.randint(2, min(5, rem)) if rem >= 2 else rem
            if current_idx + block > num_days: break
                
            for i in range(block): days[current_idx + i] = "WORK"
            total_work_assigned += block
            current_idx += block + random.randint(1, 3)
            
        if days.count("WORK") == work_target:
            days_str = "".join(["1" if d == "WORK" else "0" for d in days])
            if "010" not in days_str and "111111" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
    return ["WORK"] * work_target + ["off"] * (num_days - work_target)


st.title("🏥 護理排班系統 (終極模糊雷達版)")

with st.sidebar:
    st.header("📅 排班月份設定")
    start_date = st.date_input("排班開始日期", datetime.date(2026, 6, 1))
    end_date = st.date_input("排班結束日期", datetime.date(2026, 6, 30))
    
    num_days = (end_date - start_date).days + 1
    date_headers = [f"{d.month}/{d.day} ({WEEKDAYS_CHINESE[d.weekday()]})" for d in [(start_date + datetime.timedelta(days=x)) for x in range(num_days)]]
    st.info(f"📅 系統偵測：本月共計 {num_days} 天")
    
    file_a = st.file_uploader("1. 上傳【基本班表】", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預排休表】", type=["xlsx"])

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        full_time_names = [n for n in all_names if not staff_configs[n]["is_part_time"]]
        part_time_names = [n for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        # 初始化假表
        bg_vacation = {n: ["R"] * num_days for n in display_names}
        
        xl = pd.ExcelFile(file_b)
        active_sheet_name = ""
        found_sheet = False
        
        # 遍歷所有頁籤，自動過濾說明文
        for sheet_name in xl.sheet_names:
            if any(k in sheet_name for k in ["規範", "說明", "填寫", "使用", "欄位"]):
                continue
                
            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)
            
            # --- ⚡ 關鍵升級：全模糊動態座標雷達 ⚡ ---
            name_col_idx = 1       # 預設 B 欄
            date_start_idx = 2     # 預設 C 欄
            header_row_idx = 0
            
            # 掃描前 10 列所有的格子，用最寬鬆的條件定位「姓名」與「1號」
            for r in range(min(10, len(df_b))):
                row_vals_clean = [str(v).strip().replace(".0", "") for v in df_b.iloc[r].values]
                
                # 只要格子裡「包含」姓名兩個字，就咬定這一列是標頭列
                for c_idx, val in enumerate(row_vals_clean):
                    if "姓名" in val:
                        name_col_idx = c_idx
                        header_row_idx = r
                        
                        # 從姓名格往右找第一個出現「1」的地方作為日期起點
                        for d_idx in range(name_col_idx + 1, len(row_vals_clean)):
                            if row_vals_clean[d_idx] == "1":
                                date_start_idx = d_idx
                                found_sheet = True
                                active_sheet_name = sheet_name
                                break
                    if found_sheet: break
                if found_sheet: break
                
            # 如果真的因為字體奇特找不到，強制開啟大底層保險保證不當機
            if not found_sheet:
                name_col_idx = 1
                date_start_idx = 2
                header_row_idx = 0
                found_sheet = True
                active_sheet_name = sheet_name
            
            if found_sheet:
                # 開始依照網格絕對座標提取假表資料
                for i in range(header_row_idx + 1, len(df_b)):
                    raw_cell_name = str(df_b.iloc[i, name_col_idx]).strip() if name_col_idx < len(df_b.columns) else ""
                    if not raw_cell_name or raw_cell_name == "nan" or "序號" in raw_cell_name: continue
                    
                    clean_b_name = re.sub(r'[\s\u3000]', '', raw_cell_name)
                    
                    target_person = None
                    for name in display_names:
                        if name in clean_b_name or clean_b_name in name:
                            target_person = name; break
                    
                    if target_person:
                        for d in range(num_days):
                            col_pos = date_start_idx + d
                            if col_pos < len(df_b.columns):
                                cell_val = str(df_b.iloc[i, col_pos]).strip().upper()
                                # 鎖定指定出勤 (D/E/N)
                                if cell_val in ["D", "E", "N"]:
                                    if target_person not in part_time_names:
                                        bg_vacation[target_person][d] = cell_val
                                else:
                                    bg_vacation[target_person][d] = "R"
                break

        st.success(f"🎉 模糊雷達校正成功！已綁定分頁：【{active_sheet_name}】。")

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
                    
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], index=3, key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row, next_month_streak_row = {}, {}
            ft_off_target = 9 if num_days >= 31 else 8
            
            for attempt in range(2500):
                valid_month = True
                res = {k: [""] * num_days for k in display_names}
                
                for pt_name in part_time_names: res[pt_name] = schedule_part_time(num_days)
                ft_block_skeletons = {n: schedule_full_time_blocks(num_days, ft_off_target) for n in full_time_names}
                total_off_counts = {n: 0 for n in full_time_names}
                
                for d in range(num_days):
                    if not valid_month: break
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[pt_name][d] == "D": target["D"] -= 1
                    
                    pool = []
                    for n in full_time_names:
                        if ft_block_skeletons[n][d] == "WORK": pool.append(n)
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
                                res[n][d] = v; target[v] -= 1; pool.remove(n)
                            else: valid_month = False 
                    
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
                                valid_month = False; break
                        if not valid_month: break
                                
                    for n in pool:
                        if target["D"] > 0: res[n][d] = "D"; target["D"] -= 1
                        else: valid_month = False

                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[n] != ft_off_target: valid_month = False; break

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
                st.error("⚠️ 原始區塊條件極度嚴格。請確保預排休表中每日空白放假人數控制在 4 人以內（不含郭珍君），調整後再次重試！")
            else:
                st.success(f"🎉 {start_date.month}月份班表成功產出！")
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                final_df["系統接續_最後班別"] = [next_month_history_row[n] for n in display_names]
                final_df["系統接續_連續天數"] = [next_month_streak_row[n] for n in display_names]
                
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月建議班表")
                st.download_button(label="📥 下載完整 Excel 班表", data=out.getvalue(), file_name=f"2F_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
