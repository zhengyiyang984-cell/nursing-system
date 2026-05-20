import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-公平休假平衡版", layout="wide")

# --- 1. 背景解析邏輯 ---
def get_staff_configs(file):
    df = pd.read_excel(file, header=None)
    configs = {}
    start_row = 0
    
    # 定位起始行
    for r in range(min(15, len(df))):
        row_str = "".join(str(v) for v in df.iloc[r].values)
        if "姓名" in row_str or "職級" in row_str:
            start_row = r
            break

    for i in range(start_row + 1, len(df)):
        row = df.iloc[i]
        if len(row) < 3: continue
        
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 基礎過濾
        if (no == "" or no == "nan") and (name == "" or name == "nan"): continue
        if "星期" in no or "星期" in name or "姓名" in name: continue
        
        # 決定顯示的 Key
        display_label = no if (no != "nan" and no != "") else name
        if display_label == "" or display_label == "nan": continue 

        # 強力封殺結尾的統計與編號雜訊欄位
        clean_check = display_label.replace(" ", "").upper()
        if clean_check in ["OFF", "R", "V", "ALL", "TOTAL", "統計", "D4", "E3", "N2"]: 
            continue

        is_pt = "半職" in no or "半職" in name

        last_day = "off"
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
            "is_part_time": is_pt
        }
    return configs

# --- 2. 半職專用排班演算 ---
def schedule_part_time(num_days):
    for _ in range(100):
        days = ["off"] * num_days
        available_patterns = [
            [2, 2, 2, 2, 2],
            [3, 3, 2, 2],
            [3, 2, 3, 2],
            [2, 3, 2, 3],
            [2, 2, 3, 3]
        ]
        work_blocks = random.choice(available_patterns)
        random.shuffle(work_blocks) 
        
        current_idx = random.randint(0, 2) 
        success = True
        
        for block in work_blocks:
            if current_idx + block > num_days:
                success = False
                break
            
            for _ in range(block):
                days[current_idx] = "D"
                current_idx += 1
            
            current_idx += random.randint(2, 4)
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    backup_days = ["off"] * num_days
    safe_indices = [2, 3, 4, 9, 10, 15, 16, 17, 22, 23] 
    for idx in safe_indices:
        if idx < num_days: backup_days[idx] = "D"
    return backup_days

st.title("🏥 2F 護理排班系統")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b:
    try:
        staff_configs = get_staff_configs(file_a)
        all_names = list(staff_configs.keys())
        
        # 排序：正職在前，半職在後
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
                        if val in ["R", "OFF", "V", "開會", "0", "●"]: bg_vacation[n][d] = "R"
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 成功辨識 {len(display_names)} 位有效人員（已成功過濾尾部雜訊）。")

        # --- 3. 專屬核對區代碼 ---
        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"🔢 **序號：{n}**")
                    perm_final[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                   index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                   key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        # --- 4. 啟動自動排班 ---
        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {n: [""] * num_days for n in display_names}
            
            # A. 編排半職人員
            for pt_name in part_time_names:
                res[pt_name] = schedule_part_time(num_days)

            # 用於精準追蹤與平衡每位正職已安排的休假總天數（包含 off, v, R）
            off_counts = {n: 0 for n in full_time_names}

            # B. 正職人員排班邏輯
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                for pt_name in part_time_names:
                    if res[pt_name][d] == "D": 
                        target["D"] -= 1
                
                pool = full_time_names.copy()
                
                # 每週至少一休強制檢查
                real_day = d + 1
                current_week_start_idx = (d // 7) * 7
                if real_day % 7 == 0:
                    for n in full_time_names:
                        has_off_this_week = any(res[n][w_d] in ["off", "v", "R"] for w_d in range(current_week_start_idx, d))
                        if not has_off_this_week:
                            res[n][d] = "off"
                            off_counts[n] += 1
                            if n in pool: pool.remove(n)

                # 優先處理預約假與銜接
                for n in full_time_names.copy():
                    if n not in pool: continue
                    v = bg_vacation[n][d]
                    if v in ["D", "E", "N"]:
                        res[n][d] = v
                        target[v] -= 1
                        pool.remove(n)
                    elif v == "R":
                        res[n][d] = "off"
                        off_counts[n] += 1
                        pool.remove(n)
                    else:
                        prev = res[n][d-1] if d > 0 else history_final[n]
                        if prev == "N":
                            res[n][d] = "v"
                            off_counts[n] += 1
                            pool.remove(n)

                # 【公平平衡核心】依據目前休假次數由多到少排序
                # 讓「休假最少的人」排在池子的最末端（最後沒分到班就會自動變off）
                # 同時在 qualified 分配班別時，讓「假多的人優先抽走工作」，把放假機會留給假少的人
                random.shuffle(pool)
                pool.sort(key=lambda x: off_counts[x], reverse=True) # 假多的人在前面

                for shift in ["N", "E", "D"]:
                    qualified = [n for n in pool if shift in perm_final[n]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop(0) # 優先拔出目前假最多的人去上班
                            res[chosen][d] = shift
                            if chosen in pool: pool.remove(chosen)
                
                # 剩下沒分到班的人轉休假（此時留在 pool 裡的都是目前假比較少的人，成功拉高他們的休假天數）
                for n in pool: 
                    res[n][d] = "off"
                    off_counts[n] += 1

            # 【終極公平校正機制】如果整個月結束後，因為權限限制仍導致假數不均勻
            # 動態把假太多的人的非預約班，與假太少的人的非預約班進行互換，將差距強行抹平
            for _ in range(50):
                max_staff = max(full_time_names, key=lambda x: off_counts[x])
                min_staff = min(full_time_names, key=lambda x: off_counts[x])
                
                # 如果最大與最小休假差距大於 1 天，啟動微調
                if off_counts[max_staff] - off_counts[min_staff] > 1:
                    swapped = False
                    for d in range(num_days):
                        # 找一天：假多的在放假(off)，假少的在上班(D/E/N)，且兩人都沒有預約這天的班
                        if res[max_staff][d] == "off" and res[min_staff][d] in ["D", "E", "N"] and bg_vacation[max_staff][d] == "" and bg_vacation[min_staff][d] == "":
                            current_shift = res[min_staff][d]
                            # 檢查假少的人的權限是否允許上這個班
                            if current_shift in perm_final[max_staff]:
                                res[max_staff][d] = current_shift
                                res[min_staff][d] = "off"
                                off_counts[max_staff] -= 1
                                off_counts[min_staff] += 1
                                swapped = True
                                break
                    if not swapped: break
                else:
                    break

            st.success("🎉 自動排班與人數統計計算完成！已啟動【公平休假天數平衡機制】。")
            
            # 建立含統計資訊的 DataFrame
            final_df = pd.DataFrame(res).T
            final_df.columns = [i for i in range(1, num_days + 1)]
            
            # 橫向統計
            def count_off_days(row):
                return sum(1 for cell in row if str(cell).lower() in ["off", "v", "r"])
            
            final_df["總休假天數"] = final_df.apply(count_off_days, axis=1)
            
            # 縱向統計
            stat_rows = {}
            for d in range(1, num_days + 1):
                col_data = final_df[d]
                count_d = sum(1 for cell in col_data if str(cell).upper() == "D")
                count_e = sum(1 for cell in col_data if str(cell).upper() == "E")
                count_n = sum(1 for cell in col_data if str(cell).upper() == "N")
                
                stat_rows[d] = {
                    "白班 (4人)": f"{count_d}人",
                    "小夜 (3人)": f"{count_e}人",
                    "大夜 (2人)": f"{count_n}人"
                }
            
            df_stats = pd.DataFrame(stat_rows).T
            
            # 顯示合併結果
            st.subheader("🎉 最終排班結果（含休假與每日人力統計）")
            st.dataframe(final_df, use_container_width=True)
            
            st.markdown("### 📊 每日各班別總人數核對")
            st.table(df_stats.T)
            
            # 下載 Excel
            out = BytesIO()
            with pd.ExcelWriter(out) as w: 
                final_df.to_excel(w, sheet_name="建議班表")
                df_stats.T.to_excel(w, sheet_name="每日人數統計")
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Schedule_Final_Balanced.xlsx")

    except Exception as e:
        st.error(f"系統執行失敗: {e}")
