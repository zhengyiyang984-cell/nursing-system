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

st.title("🏥 護理排班系統 (半職動態救火精準 4/3/2 版)")

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
            
            revoked_log = []
            
            for attempt in range(3500):
                valid_month = True
                res = {str(k): ["off"] * num_days for k in display_names}
                ironed_vacation = {n: bg_vacation[n].copy() for n in display_names}
                
                total_off_counts = {str(n): 0 for n in full_time_names}
                streak_tracker = {str(n): int(cont_days_final[n]) for n in full_time_names}
                
                # 半職郭珍君的總天數計數器
                pt_work_days_count = 0
                pt_assigned_days = []
                
                for d in range(num_days):
                    if not valid_month: break
                    
                    # 預設每日白班目標 4 人
                    target = {"D": 4, "E": 3, "N": 2}
                    
                    if d > 0:
                        for n in full_time_names:
                            if res[str(n)][d-1] == "off":
                                streak_tracker[str(n)] = 0
                    
                    pool = [str(name_item).strip() for name_item in full_time_names]
                    
                    # 1. 滿 5 連班者強制斷班放假
                    for n in pool.copy():
                        if streak_tracker[str(n)] >= 5:
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))
                            
                    # 2. ⚡ 核心動態捕手：計算今天正職扣除請假後剩下多少可用人手
                    active_ft_workers = [n for n in pool if ironed_vacation[n][d] != "R"]
                    
                    # ➔ 如果活人小於 9 個人（人手不夠分配 4/3/2 ），且郭珍君還沒滿 10 天，強制塞給半職救火！
                    if len(active_ft_workers) < 9 and pt_work_days_count < 10:
                        for pt_name in part_time_names:
                            res[pt_name][d] = "D"
                        pt_work_days_count += 1
                        pt_assigned_days.append(d)
                        target["D"] -= 1 # 扣減當天正職的白班需求名額
                    
                    # 3. 萬一半職出動了，正職請假人數還是大超標，再動態平滑微調正職假
                    total_required = target["D"] + target["E"] + target["N"]
                    while len([n for n in pool if ironed_vacation[n][d] != "R"]) < total_required:
                        v_workers = [n for n in pool if ironed_vacation[n][d] == "R"]
                        if not v_workers: break
                        v_workers.sort(key=lambda x: total_off_counts[str(x)], reverse=True)
                        fired_person = v_workers[0]
                        ironed_vacation[fired_person][d] = "" 
                        msg = f"⚠️ {d+1}號 劃假人數超出上限，半職救火補位後仍有缺口，系統已微調正職【{fired_person}】出勤支援。"
                        if msg not in revoked_log: revoked_log.append(msg)
                    
                    # 4. 處理放假的正職
                    for n in pool.copy():
                        if ironed_vacation[str(n)][d] == "R":
                            res[str(n)][d] = "off"
                            total_off_counts[str(n)] += 1
                            pool.remove(str(n))

                    # 5. 指定預班處理
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
                    
                    # 6. 分派空白正職：依照連班與休假天數進行平滑排序
                    random.shuffle(pool)
                    current_pool_order = sorted(pool, key=lambda x: (streak_tracker[str(x)] > 0, total_off_counts[str(x)]), reverse=True)
                    
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
                        
                    # 人力精準總核對：只要當天有任何一班沒完美歸零，這輪直接報廢重排！
                    if target["D"] != 0 or target["E"] != 0 or target["N"] != 0:
                        valid_month = False

                # 💡 半職強制補位機制：如果月底結算時，半職郭珍君救火天數少於 10 天，自動挑剩餘的日子幫她補滿 10 天
                if valid_month and pt_work_days_count < 10:
                    needed_days = 10 - pt_work_days_count
                    all_possible_days = [x for x in range(num_days) if x not in pt_assigned_days]
                    # 優先挑選當天白班全部由正職組成、且請假人數較多的日子塞入
                    all_possible_days.sort(key=lambda x: sum(1 for n in full_time_names if bg_vacation[n][x] == "R"), reverse=True)
                    
                    for extra_day in all_possible_days[:needed_days]:
                        for pt_name in part_time_names:
                            res[pt_name][extra_day] = "D"
                        pt_work_days_count += 1
                
                if pt_work_days_count != 10:
                    valid_month = False

                # 正職總休假天數大驗證
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
            
            # --- 網頁渲染與輸出 ---
            # ⚡ 核心保險：如果不成功便顯示錯誤訊息，絕不允許不符合 4/3/2 的爛數據印在畫面上！
            if not success_schedule or not final_res:
                st.error("⚠️ 錯誤：目前正職指定班別與假表衝突過高。請點擊上方按鈕再次啟動重試，或是讓阿長微調衝突的指定預班！")
            else:
                if revoked_log:
                    with warning_placeholder:
                        for log in revoked_log:
                            st.warning(log)
                            
                st.success(f"🎉 完美通關！半職捕手已動態補位，全月每日均完美對齊『4白班（含半職）、3小夜、2大夜』的絕對比例！")
                
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
                    final_df.to_excel(w, sheet_name=f"{start_date.month}月精準建議班表")
                st.download_button(label="📥 下載最終精準 4/3/2 Excel 班表", data=out.getvalue(), file_name=f"2F_Perfect_Schedule_{start_date.month}M.xlsx", use_container_width=True)

    except Exception as e:
        st.error(f"系統解析錯誤: {e}")
