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

# --- 2. 半職區塊循環產生器 ---
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


st.title("🏥 護理排班系統 (精準 4/3/2 人力智慧版)")

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
            
            revoked_vacations_log = [] 
            
            # 提高嘗試次數進行深度求解
            for attempt in range(3000):
                valid_month = True
                res = {str(k): ["off"] * num_days for k in display_names}
                
                # 複製一個局部假表
                local_vacation = {n: bg_vacation[n].copy() for n in display_names}
                
                # 先排半職（固定 10 天 D 班）
                for pt_name in part_time_names: 
                    res[str(pt_name)] = schedule_part_time(num_days)
                    
                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): int(cont_days_final[n]) for n in full_time_names}
                
                for d in range(num_days):
                    if not valid_month: break
                    
                    # 👈 核心修正：嚴格卡死當天的出勤人數目標
                    target = {"D": 4, "E": 3, "N": 2}
                    for pt_name in part_time_names:
                        if res[str(pt_name)][d] == "D": 
                            target["D"] -= 1 # 半職分擔白班
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[str(n)][d-1] == "off":
                                streak_tracker[str(n)] = 0
                    
                    # 初始化今天可以動用的正職名單
                    pool = [str(name_item).strip() for name_item in full_time_names]
                    
                    # 1. 滿 5 連班者強制斷班放假
                    for n in pool.copy():
                        if streak_tracker[str(n)] >= 5:
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))
                            
                    # 2. 智慧軟化機制：檢查當天劃假人數是否過多，若 pool 剩下的人不夠填滿當天 target
                    total_required = target["D"] + target["E"] + target["N"]
                    
                    # 算出此時 pool 裡面，扣掉堅持要請假（R）的人之後，還剩幾個人可用
                    available_workers = [n for n in pool if local_vacation[str(n)][d] != "R"]
                    
                    # 如果可用人數不夠填滿 4/3/2，由系統從今天請假的人中，抓假休最多或隨機的人出來上班
                    while len(available_workers) < total_required and len(pool) >= total_required:
                        v_workers = [n for n in pool if local_vacation[str(n)][d] == "R"]
                        if not v_workers: break
                        # 依照已休假天數排序，優先拉出假休比較多的人
                        v_workers.sort(key=lambda x: total_off_counts[str(x)], reverse=True)
                        pulled_person = v_workers[0]
                        local_vacation[pulled_person][d] = "" # 沒收請假
                        available_workers.append(pulled_person)
                        msg = f"⚠️ 偵測到 {d+1}號 劃假大塞車，系統已調度【{pulled_person}】支援當日出勤以維持 4/3/2 人力標準。"
                        if msg not in revoked_vacations_log: revoked_vacations_log.append(msg)
                    
                    # 3. 處理留下來請假的人
                    for n in pool.copy():
                        if local_vacation[str(n)][d] == "R":
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))

                    # 4. 優先處理同仁自己指定的預班 (D, E, N)
                    for n in pool.copy():
                        v = local_vacation[str(n)][d]
                        if v in ["D", "E", "N"]:
                            if target[v] > 0 and v in perm_final[str(n)]:
                                res[str(n)][d] = v
                                target[v] -= 1
                                streak_tracker[str(n)] += 1
                                pool.remove(str(n))
                            else:
                                valid_month = False
                    
                    if not valid_month: break
                    
                    # 5. 分派其餘空白正職：依照連班與休假天數排序
                    random.shuffle(pool)
                    current_pool_order = sorted(pool, key=lambda x: (streak_tracker[str(x)] > 0, total_off_counts[str(x)]), reverse=True)
                    
                    # 嚴格分派大夜(N) -> 小夜(E) -> 白班(D)，不符合花班則跳過
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
                                # 💡 花班寬鬆防線：若因為花班限制導致 4/3/2 補不滿，強行打破限制補齊人力
                                if pool:
                                    fallback = pool.pop(0)
                                    res[str(fallback)][d] = shift
                                    streak_tracker[str(fallback)] += 1
                                    target[shift] -= 1
                                else:
                                    valid_month = False; break
                        if not valid_month: break
                                
                    # 6. 當天所有名額都分派完後，剩餘的人全部休假
                    for n in pool:
                        res[str(n)][d] = "off"
                        total_off_counts[str(n)] += 1
                        
                    # ⚡ 雙重終極核對：如果今天結束後，target 還有任何一個沒歸零，代表當天人數沒對齊 4/3/2！
                    if target["D"] != 0 or target["E"] != 0 or target["N"] != 0:
                        valid_month = False

                # 月底總假驗證
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
            
            # --- 3. 輸出渲染區塊 ---
            if not success_schedule or not final_res:
                st.error("⚠️ 無法配出完美對齊 4/3/2 天數的區塊班表。請檢查預排休表，是否有些日子大家集體指定了衝突的班別（例如某天5人指定上大夜）？")
            else:
                # 列印出調度警告
                if revoked_vacations_log:
                    with warning_placeholder:
                        for log in revoked_vacations_log[:4]:
                            st.warning(log)
                            
                st.success(f"🎉 成功！班表已完全符合每日白班4人（含半職）、小夜3人、大夜2人的絕對標準！")
                
                final_df = pd.DataFrame(final_res).T
                final_df.columns = date_headers    
                
                final_df["總休假天數"] = final_df.apply(lambda row: sum(1 for c in row if str(c).lower() in ["off", "v", "r"]), axis=1)
                
                last_day_list = []
                streak_list = []
                for n in final_df.index:
                    raw_last = next_month_history_row.get(str(n), "off")
                    if raw_last in ["D", "E", "N"]: last_day_list.append(raw_last)
                    else: last_day_list.append("off")
                    streak_list.append(next_month_streak_row.get(str(n), 0))
                        
                final_df["系統接續_最後班別"] = last_day_list
                final_df["系統接續_連續天數"] = streak_list
                
                st.dataframe(final_df, use_container_width=True)
                
                out = BytesIO()
                with pd.ExcelWriter(out, engine='xlsxwriter') as w: 
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月精準班表")
                st.download_button(label="📥 下載最終精準 4/3/2 Excel 班表", data=out.getvalue(), file_name=f"2F_Perfect_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
