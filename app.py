import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-完美過濾修復版", layout="wide")

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

        # 【精準防禦】強力封殺結尾的統計與編號雜訊欄位，不讓它們變成方塊
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

# --- 2. 半職專用排班演算 (連續上班 2-3 天後休息，嚴格禁止 1 天與 4 天以上，整個月剛好 10 天) ---
def schedule_part_time(num_days):
    for _ in range(100):
        days = ["off"] * num_days
        
        # 由 2 與 3 天工作區塊隨機拼湊成剛好 10 天班
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
            
            current_idx += random.randint(2, 4) # 強制隔開，避免相連變成 4 天以上
            
        if success and days.count("D") == 10:
            days_str = "".join(["1" if d == "D" else "0" for d in days])
            if "1111" not in days_str and "010" not in days_str and not days_str.startswith("10") and not days_str.endswith("01"):
                return days
                
    # 保底安全模組
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
        
        # 排序：正職 1-13 在前，半職 1 在最後一行
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

        st.success(f"✅ 成功辨識 {len(display_names)} 位有效人員（已成功過濾尾部假別統計行）。")

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
            
            # A. 編排半職人員（嚴格限制 2-3 天，共 10 天）
            for pt_name in part_time_names:
                res[pt_name] = schedule_part_time(num_days)

            # B. 正職人員排班邏輯
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                
                for pt_name in part_time_names:
                    if res[pt_name][d] == "D": 
                        target["D"] -= 1
                
                pool = full_time_names.copy()
                random.shuffle(pool)
                
                for n in full_time_names:
                    v = bg_vacation[n][d]
                    if v in ["D", "E", "N"]:
                        res[n][d] = v
                        target[v] -= 1
                        pool.remove(n)
                    elif v == "R":
                        res[n][d] = "off"
                        pool.remove(n)
                    else:
                        prev = res[n][d-1] if d > 0 else history_final[n]
                        if prev == "N":
                            res[n][d] = "v"
                            pool.remove(n)
                
                for shift in ["N", "E", "D"]:
                    qualified = [n for n in pool if shift in perm_final[n]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop()
                            res[chosen][d] = shift
                            pool.remove(chosen)
                
                for n in pool: 
                    res[n][d] = "off"

            st.success("🎉 自動排班計算完成！")
            final_df = pd.DataFrame(res).T
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_df.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Schedule_Final.xlsx")

    except Exception as e:
        st.error(f"系統執行失敗: {e}")
