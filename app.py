import streamlit as st
import pandas as pd
import random
from io import BytesIO
import datetime
import re

st.set_page_config(page_title="2F 護理排班系統", layout="wide")

# 中文星期對照表
WEEKDAYS_CHINESE = ["一", "二", "三", "四", "五", "六", "日"]

# 2F 全科室標準 13 人核心真名白名單
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
        if any(k in row_str for k in ["---", "每日人力", "總人數", "核對", "統計", "合計"]):
            continue
            
        matched_name = None
        for name in CORE_STAFF_NAMES:
            if name in row_str:
                matched_name = name; break
                
        if matched_name:
            row_cells = [str(v).strip() for v in df.iloc[i].values if pd.notna(v)]
            row_cells_upper = [c.upper() for c in row_cells]
            
            pure_perm = "DEN"
            for cell in row_cells_upper:
                if any(s in cell for s in ["D", "E", "N"]) and not cell.replace(".0", "").isdigit() and len(cell) <= 4:
                    if cell in ["DEN", "DE", "EN", "DN", "D", "E", "N"]:
                        pure_perm = cell; break
            
            is_pt = (matched_name == "郭珍君")
            configs[matched_name] = {
                "perm": pure_perm,
                "last_day": "off",
                "streak": 0,
                "is_part_time": is_pt
            }
    return configs


st.title("🏥 護理排班系統 (半職智慧調度精準 4/3/2 版)")

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
        full_time_names = [str(n) for n in all_names if not staff_configs[n]["is_part_time"]]
        part_time_names = [str(n) for n in all_names if staff_configs[n]["is_part_time"]]
        display_names = full_time_names + part_time_names

        bg_vacation = {n: [""] * num_days for n in display_names}
        
        xl = pd.ExcelFile(file_b)
        active_sheet_name = "未指定分頁" 
        found_sheet = False
        
        for sheet_name in xl.sheet_names:
            if any(k in sheet_name for k in ["規範", "說明", "填寫", "使用", "欄位"]):
                continue
                
            df_b = pd.read_excel(file_b, sheet_name=sheet_name, header=None)
            
            name_col_idx = 1       
            date_start_idx = 2     
            header_row_idx = 0     
            
            for r in range(min(10, len(df_b))):
                vals = [str(v).strip() for v in df_b.iloc[r].values]
                if "姓名" in vals:
                    name_col_idx = vals.index("姓名")
                    date_start_idx = name_col_idx + 1
                    header_row_idx = r
                    found_sheet = True
                    active_sheet_name = sheet_name 
                    break
                    
            if found_sheet:
                for i in range(header_row_idx + 1, len(df_b)):
                    raw_cell_name = str(df_b.iloc[i, name_col_idx]).strip()
                    if not raw_cell_name or raw_cell_name == "nan" or "序號" in raw_cell_name: continue
                    clean_b_name = re.sub(r'[\s\u3000]', '', raw_cell_name)
                    
                    target_person = None
                    for name in display_names:
                        if name in clean_b_name:
                            target_person = name; break
                    
                    if target_person:
                        for d in range(num_days):
                            col_pos = date_start_idx + d
                            if col_pos < len(df_b.columns):
                                cell_val = str(df_b.iloc[i, col_pos]).strip().upper()
                                if "D" in cell_val and "R" not in cell_val:
                                    bg_vacation[target_person][d] = "D"
                                elif "E" in cell_val:
                                    bg_vacation[target_person][d] = "E"
                                elif "N" in cell_val:
                                    bg_vacation[target_person][d] = "N"
                                elif "R" in cell_val or "OFF" in cell_val or "V" in cell_val or "●" in cell_val or cell_val == "NAN" or cell_val == "":
                                    bg_vacation[target_person][d] = "R"
                break

        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        standard_shifts = ["D", "E", "N", "off", "v", "R"]
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"👤 **同仁姓名：{n}**")
                    raw_perm = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    perm_final[n] = raw_perm.strip().upper().replace(",", "").replace(" ", "")
                    if not perm_final[n]: perm_final[n] = "DEN"
                    
                    history_final[n] = st.selectbox(f"上次班別", standard_shifts, index=3, key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        st.markdown("---")
        
        warning_placeholder = st.container()
        
        if st.button("🚀 啟動精準 4/3/2 排班", type="primary", use_container_width=True):
            success_schedule = False
            final_res = {}
            next_month_history_row, next_month_streak_row = {}, {}
            ft_off_target = 9 if num_days >= 31 else 8
            
            # ⚡ 智慧半職調度與前置熨平機制 ⚡
            # 1. 計算每天正職的請假人數缺口
            daily_danger_list = []
            for d in range(num_days):
                ft_off_today = sum(1 for n in full_time_names if bg_vacation[n][d] == "R")
                daily_danger_list.append((d, ft_off_today))
            
            # 2. 找出全月「正職請假最多、人手最危險」的前 10 天
            daily_danger_list.sort(key=lambda x: x[1], reverse=True)
            top_10_dangerous_days = [item[0] for item in daily_danger_list[:10]]
            
            # 3. 核心修正：將半職（郭珍君）的 10 天 D 班，精準鎖死在這些缺人手的日子
            pt_schedule_dict = {}
            for pt_name in part_time_names:
                pt_schedule_dict[pt_name] = ["off"] * num_days
                for day_idx in top_10_dangerous_days:
                    pt_schedule_dict[pt_name][day_idx] = "D"
            
            # 4. 熨平系統：在半職加入後，若部分天數依然突破 12-9=3 人的請假上限，自動進行微調
            ironed_vacation = {n: bg_vacation[n].copy() for n in display_names}
            revoked_log = []
            
            for d in range(num_days):
                ft_off_today_list = [n for n in full_time_names if ironed_vacation[n][d] == "R"]
                pt_support = 1 if d in top_10_dangerous_days else 0
                
                # 數學死結：12 - 正職請假人數 < 9 - 半職支援名額
                while (12 - len(ft_off_today_list)) < (9 - pt_support):
                    if not ft_off_today_list: break
                    # 優先徵調已經休比較多假的人回來
                    ft_off_today_list.sort(key=lambda x: ironed_vacation[x].count("R"), reverse=True)
                    fired_person = ft_off_today_list.pop(0)
                    ironed_vacation[fired_person][d] = "" 
                    msg = f"⚠️ 偵測到 {d+1}號 劃假人數超出上限，半職空降支援後仍有缺口，系統已微調正職【{fired_person}】支援當日出勤。"
                    if msg not in revoked_log: revoked_log.append(msg)

            # 進入滑動視窗演算主體
            for attempt in range(2500):
                valid_month = True
                res = {str(k): ["off"] * num_days for k in display_names}
                
                # 指派算好的半職救火班表
                for pt_name in part_time_names:
                    res[str(pt_name)] = pt_schedule_dict[pt_name].copy()
                    
                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): int(cont_days_final[n]) for n in full_time_names}
                
                for d in range(num_days):
                    if not valid_month: break
                    
                    # 強制卡死當天 4D / 3E / 2N 的目標
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[str(pt_name)][d] == "D": 
                            target["D"] -= 1 # 半職扣減白班名額
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[str(n)][d-1] == "off":
                                streak_tracker[str(n)] = 0
                    
                    pool = [str(name_item).strip() for name_item in full_time_names]
                    
                    # 連班限制斷班
                    for n in pool.copy():
                        if streak_tracker[str(n)] >= 5:
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))
                            
                    # 處理預約假
                    for n in pool.copy():
                        if ironed_vacation[str(n)][d] == "R":
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))

                    # 指定預班處理
                    for n in pool.copy():
                        v = ironed_vacation[str(n)][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[str(n)]:
                                res[str(n)][d] = v
                                target[v] -= 1
                                streak_tracker[str(n)] += 1
                                pool.remove(str(n))
                            else:
                                valid_month = False
                    
                    if not valid_month: break
                    
                    random.shuffle(pool)
                    current_pool_order = sorted(pool, key=lambda x: (streak_tracker[str(x)] > 0, total_off_counts[str(x)]), reverse=True)
                    
                    # 分派夜班與白班
                    for shift in ["N", "E", "D"]:
                        qualified = []
                        for n in current_pool_order:
                            if str(n) in pool and shift in perm_final[str(n)]:
                                prev_1 = res[str(n)][d-1] if d > 0 else history_final[str(n)]
                                if shift == "D" and prev_1 in ["N", "E"]: continue
                                if shift == "E" and prev_1 == "N": continue
                                qualified.append(str(n))
                                
                        for _ in range(max(0, target[shift])):
                            if qualified:
                                chosen = qualified.pop(0)
                                res[str(chosen)][d] = shift
                                streak_tracker[str(chosen)] += 1
                                pool.remove(str(chosen))
                                target[shift] -= 1
                            else:
                                if pool:
                                    fallback = pool.pop(0)
                                    res[str(fallback)][d] = shift
                                    streak_tracker[str(fallback)] += 1
                                    target[shift] -= 1
                                else:
                                    valid_month = False; break
                        if not valid_month: break
                                
                    for n in pool:
                        res[str(n)][d] = "off"
                        total_off_counts[str(n)] += 1
                        
                    # 人力精準總核對：只要當天有任何一班沒對齊 4/3/2，此輪直接報廢重算！
                    if target["D"] != 0 or target["E"] != 0 or target["N"] != 0:
                        valid_month = False

                # 月底大驗證
                if valid_month:
                    for n in full_time_names:
                        if total_off_counts[str(n)] != ft_off_target: 
                            valid_month = False; break
                        
                        days_str = "".join(["0" if res[str(n)][x] == "off" else "1" for x in range(num_days)])
                        if "010" in days_str or days_str.startswith("10") or days_str.endswith("01"):
                            valid_month = False; break

                if valid_month:
                    final_res = {str(k): v for k, v in res.items()}
                    for n in display_names:
                        next_month_history_row[str(n)] = str(res[str(n)][-1])
                        s_count = 0
                        for cell_b in reversed(res[str(n)]):
                            if cell_b in ["D", "E", "N"]: s_count += 1
                            else: break
                        next_month_streak_row[str(n)] = s_count
                    success_schedule = True
                    break
            
            # --- 渲染與輸出 ---
            # ⚡ 徹底拔除會損壞人數的盲目保底，只輸出完全合法的結果
            if not success_schedule or not final_res:
                st.error("⚠️ 無法在維持正職每人剛好休 8/9 天與 4/3/2 人力的限制下配平。請確認是否有同仁在同一天指定了衝突的班別。")
            else:
                if revoked_log:
                    with warning_placeholder:
                        for log in revoked_log:
                            st.warning(log)
                            
                st.success(f"🎉 完美成功！半職已自動空降至重災區天數，班表已完全符合每日 4D / 3E / 2N 的絕對標準！")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                
                last_day_list, streak_list = [], []
                for n in final_df.index:
                    raw_last = next_month_history_row.get(str(n), "off")
                    last_day_list.append(raw_last if raw_last in ["D", "E", "N"] else "off")
                    streak_list.append(next_month_streak_row.get(str(n), 0))
                        
                final_df["系統接續_最後班別"] = last_day_list
                final_df["系統接續_連續天數"] = streak_list
                
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月精準建议班表")
                st.download_button(label="📥 下載最終精準 4/3/2 Excel 班表", data=out.getvalue(), file_name=f"2F_Perfect_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
