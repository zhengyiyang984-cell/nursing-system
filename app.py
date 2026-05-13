import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-序號簡潔版", layout="wide")

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
        
        # A欄:權限, B欄:序號, C欄:姓名
        perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
        no = str(row.iloc[1]).strip() if pd.notna(row.iloc[1]) else ""
        name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ""
        
        # 如果序號跟姓名都空，就跳過
        if no == "nan" and name == "nan": continue
        if "星期" in no or "星期" in name: continue
            
        # 【修改重點】這裡只取序號作為顯示名稱
        display_label = no if no != "nan" else name
        
        # 抓取最後一天班別作為預設值
        last_day = "off"
        for cell in reversed(row.values[3:8]):
            c = str(cell).strip().upper()
            if c in ["D", "E", "N", "OFF", "V", "R"]:
                last_day = c if c in ["D", "E", "N", "R"] else c.lower()
                break
        if last_day not in ["D", "E", "N", "off", "v", "R"]: last_day = "off"

        configs[display_label] = {
            "pure_id": re.sub(r'[\s\u3000]', '', name), # 這是用來跟檔案 B 對齊人名用的
            "perm": perm if perm != "NAN" else "DEN",
            "last_day": last_day
        }
    return configs

st.title("🏥 2F 護理排班系統 (序號核對模式)")

with st.sidebar:
    st.header("📂 檔案上傳")
    num_days = st.slider("本月天數", 28, 31, 31)
    file_a = st.file_uploader("1. 上傳【班表】(檔案 A)", type=["xlsx"])
    file_b = st.file_uploader("2. 上傳【預班表】(檔案 B)", type=["xlsx"])

if file_a and file_b:
    try:
        # 背景作業：讀取人員配置
        staff_configs = get_staff_configs(file_a)
        display_names = list(staff_configs.keys())
        
        # 背景作業：讀取預班表 (檔案 B)
        df_b = pd.read_excel(file_b, header=None)
        bg_vacation = {n: [""] * num_days for n in display_names}
        for i in range(len(df_b)):
            b_name = re.sub(r'[\s\u3000]', '', str(df_b.iloc[i, 2]))
            # 透過後台儲存的 pure_id 進行人名比對
            for n in display_names:
                if staff_configs[n]["pure_id"] == b_name:
                    for d in range(num_days):
                        val = str(df_b.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b.columns) else ""
                        if val in ["R", "OFF", "V", "開會", "0", "●"]: bg_vacation[n][d] = "R"
                        elif val in ["D", "E", "N"]: bg_vacation[n][d] = val
                    break

        st.success(f"✅ 已辨識 {len(display_names)} 位人員，預班表資料已同步。")

        # --- 核對區：只顯示序號 ---
        st.subheader("⚙️ 核對權限與銜接狀態")
        history_final, perm_final, cont_days_final = {}, {}, {}
        cols = st.columns(4)
        
        for i, n in enumerate(display_names):
            with cols[i % 4]:
                with st.container(border=True):
                    st.markdown(f"{n}")
                    perm_final[n] = st.text_input(f"權限", value=staff_configs[n]["perm"], key=f"p_{n}")
                    history_final[n] = st.selectbox(f"上次班別", ["D", "E", "N", "off", "v", "R"], 
                                                   index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), 
                                                   key=f"h_{n}")
                    cont_days_final[n] = st.number_input(f"連續天數", 0, 6, 0, key=f"c_{n}")

        # --- 啟動排班 ---
        st.markdown("---")
        if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
            res = {n: [""] * num_days for n in display_names}
            for d in range(num_days):
                target = {"D": 4, "E": 3, "N": 2}
                pool = display_names.copy()
                random.shuffle(pool)
                
                # A. 套用背景預約假
                for n in display_names:
                    v = bg_vacation[n][d]
                    if v in ["D", "E", "N"]:
                        res[n][d] = v; target[v] -= 1; pool.remove(n)
                    elif v == "R":
                        res[n][d] = "off"; pool.remove(n)
                    else:
                        prev = res[n][d-1] if d > 0 else history_final[n]
                        if prev == "N":
                            res[n][d] = "v"; pool.remove(n)
                
                # B. 分配人力
                for shift in ["N", "E", "D"]:
                    qualified = [n for n in pool if shift in perm_final[n]]
                    for _ in range(max(0, target[shift])):
                        if qualified:
                            chosen = qualified.pop(); res[chosen][d] = shift; pool.remove(chosen)
                
                for n in pool: res[n][d] = "off"

            st.success("🎉 排班完成！")
            final_df = pd.DataFrame(res).T
            st.dataframe(final_df, use_container_width=True)
            
            out = BytesIO()
            with pd.ExcelWriter(out) as w: final_df.to_excel(w)
            st.download_button("📥 下載 Excel 結果", out.getvalue(), "Schedule_Final.xlsx")

    except Exception as e:
        st.error(f"解析失敗: {e}")
else:
    st.info("👋 請上傳檔案 A 與 檔案 B 開始排班。")
