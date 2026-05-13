import streamlit as st
import pandas as pd
import random
from io import BytesIO
import re

st.set_page_config(page_title="2F 護理排班系統-雙匯入整合版", layout="wide")

# --- 輔助函式：清理 ID ---
def clean_id(val):
    if pd.isna(val): return ""
    s = re.sub(r'[\s\n\r\t\u200b-\u200d\ufeff]', '', str(val)).split('.')[0]
    return '半職1' if '半職' in s else s

# --- 輔助函式：偵測權限與銜接 ---
def get_staff_base_data(df):
    staff_data = {}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid and (sid.isdigit() or '半職' in sid):
            perm = str(row.iloc[0]).strip().upper() if pd.notna(row.iloc[0]) else "DEN"
            last_val = "off"
            for cell in reversed(row.values):
                c = str(cell).strip().upper()
                if c in ["D", "E", "N", "OFF", "V", "R"]:
                    last_val = c.lower() if c in ["OFF", "V"] else c
                    break
            staff_data[sid] = {"perm": perm, "last_day": last_val}
    return staff_data

# --- 輔助函式：偵測預約假與固定班 ---
def get_vacation_import(df, names, num_days):
    v_map = {n: [""] * num_days for n in names}
    for i, row in df.iterrows():
        sid = clean_id(row.iloc[1])
        if sid in names:
            for d in range(num_days):
                col_idx = d + 3 # 假設日期從第 4 欄開始
                if col_idx < len(row):
                    val = str(row.iloc[col_idx]).strip().upper()
                    if val in ["OFF", "V", "開會", "R"]:
                        v_map[sid][d] = "R"
                    elif val in ["D", "E", "N"]:
                        v_map[sid][d] = val
    return v_map

st.title("🏥 2F 護理排班系統 (雙匯入整合版)")

# --- 1. 側邊欄：雙匯入區塊 ---
with st.sidebar:
    st.header("⚙️ 設定與匯入")
    num_days = st.slider("本月排班天數", 28, 31, 31)
    
    st.divider()
    st.subheader("📥 檔案 A：偵測權限與銜接")
    base_file = st.file_uploader("上傳上月班表", type=["xlsx", "csv"], key="base")
    
    staff_configs = {}
    if base_file:
        try:
            df_base = pd.read_csv(base_file, header=None) if base_file.name.endswith('.csv') else pd.read_excel(base_file, header=None)
            staff_configs = get_staff_base_data(df_base)
            st.success(f"✅ 已載入 {len(staff_configs)} 人名單")
        except Exception as e:
            st.error(f"讀取失敗: {e}")

    st.divider()
    st.subheader("📥 檔案 B：自訂假與固定班")
    vac_file = st.file_uploader("上傳本月預約表 (選填)", type=["xlsx", "csv"], key="vac")
    
    imported_v_map = None
    if vac_file and staff_configs:
        try:
            df_vac = pd.read_csv(vac_file, header=None) if vac_file.name.endswith('.csv') else pd.read_excel(vac_file, header=None)
            imported_v_map = get_vacation_import(df_vac, list(staff_configs.keys()), num_days)
            st.success("✅ 已載入自訂休假與固定班")
        except Exception as e:
            st.warning(f"預約表讀取失敗: {e}")

if not staff_configs:
    st.info("💡 請先在左側上傳「檔案 A」以產生成員名單。")
    st.stop()

# --- 2. 銜接核對 ---
st.subheader("⚙️ 核對權限與銜接狀態")
names = list(staff_configs.keys())
history_final, perm_final, cont_days_final = {}, {}, {}
cols = st.columns(4)
for i, n in enumerate(names):
    with cols[i % 4]:
        perm_final[n] = st.text_input(f"{n} 權限", value=staff_configs[n]["perm"], key=f"p_{n}")
        history_final[n] = st.selectbox(f"{n} 上次", ["D", "E", "N", "off", "v", "R"], 
                                       index=["D", "E", "N", "off", "v", "R"].index(staff_configs[n]["last_day"]), key=f"h_{n}")
        cont_days_final[n] = st.number_input(f"{n} 連續天數", 0, 6, 0, key=f"c_{n}")

# --- 3. 預約假表格 ---
st.subheader("📅 自訂休假與固定班 (R 為休假)")
dates = [f"{i+1}日" for i in range(num_days)]

# 如果有匯入檔案 B，則初始化表格
if 'v_df' not in st.session_state or st.session_state.v_df.index.tolist() != names:
    if imported_v_map:
        st.session_state.v_df = pd.DataFrame(imported_v_map).T
        st.session_state.v_df.columns = dates
    else:
        st.session_state.v_df = pd.DataFrame("", index=names, columns=dates)

# 提供手動微調
edited_df = st.data_editor(st.session_state.v_df, use_container_width=True)

# --- 4. 核心邏輯 ---
def run_scheduling(days, hist, cont, v_table, perms):
    res = {n: [""] * days for n in names}
    
    # 半職1 邏輯 (10天, 2-3連班)
    if "半職1" in names:
        pt_row = v_table.loc["半職1"]
        pt_reserved = [d for d in range(days) if str(pt_row.iloc[d]).strip().upper() in ["R", "V", "OFF"]]
        for d in pt_reserved: res["半職1"][d] = "R"
        pt_work = []
        for _ in range(3000):
            tmp, last, ok = [], -2, True
            blocks = [3, 3, 2, 2]; random.shuffle(blocks)
            for b in blocks:
                starts = [s for s in range(days) if s > last+1 and s+b <= days and all(s+i not in pt_reserved for i in range(b))]
                if not starts: ok = False; break
                s = random.choice(starts); tmp.extend(range(s, s+b)); last = s+b-1
            if ok and len(tmp) == 10: pt_work = tmp; break
        if pt_work:
            for d in pt_work: res["半職1"][d] = "D"
        for d in range(days):
            if res["半職1"][d] == "": res["半職1"][d] = "off"

    # 全員 4D/3E/2N 補人
    others = [n for n in names if n != "半職1"]
    for d in range(days):
        target = {"D": 4, "E": 3, "N": 2}
        if "半職1" in res and res["半職1"][d] == "D": target["D"] -= 1
        
        pool = others.copy()
        random.shuffle(pool)
        
        for n in others:
            val = str(v_table.loc[n, f"{d+1}日"]).strip().upper()
            if val in ["D", "E", "N"]:
                res[n][d] = val; target[val] -= 1; pool.remove(n)
            elif val in ["R", "V", "OFF", "開會"]:
                res[n][d] = "R"; pool.remove(n)
            else:
                prev = res[n][d-1] if d > 0 else hist[n]
                if prev == "N": res[n][d] = "v"; pool.remove(n)
                # 連班天數保護 (第一天)
                elif d == 0 and cont[n] >= 5: res[n][d] = "off"; pool.remove(n)

        for shift in ["N", "E", "D"]:
            qualified = [n for n in pool if shift in perms[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop(); res[staff][d] = shift; pool.remove(staff)
        
        for n in pool: res[n][d] = "off"
            
    return pd.DataFrame(res).T, None

# --- 5. 啟動 ---
if st.button("🚀 啟動自動排班", type="primary", use_container_width=True):
    final_res, err = run_scheduling(num_days, history_final, cont_days_final, edited_df, perm_final)
    if err:
        st.error(err)
    else:
        st.success("✅ 排班成功！")
        def style_f(v):
            colors = {'D': '#FFF9C4', 'E': '#C8E6C9', 'N': '#BBDEFB', 'R': '#FFCDD2'}
            return f'background-color: {colors.get(v, "transparent")}; color: black; font-weight: bold'
        st.dataframe(final_res.style.map(style_f), use_container_width=True)
        out = BytesIO()
        with pd.ExcelWriter(out, engine='openpyxl') as writer:
            final_res.to_excel(writer, sheet_name='建議班表')
        st.download_button("📥 下載 Excel 結果", out.getvalue(), "2F_Schedule.xlsx")
# --- 以下是新增的自動同步與顯示區塊 ---
import re

if file_a and file_b:
    st.markdown("---")
    st.subheader("🔄 預約班表自動同步區")
    
    # 1. 讀取與解析資料
    try:
        # 讀取檔案 A 建立人員清單
        df_a_sync = pd.read_excel(file_a, header=None)
        # 讀取檔案 B 獲取預約假
        df_b_sync = pd.read_excel(file_b, header=None)
        
        # 建立比對 ID (移除空格的姓名)
        sids = []
        labels = []
        for i in range(2, len(df_a_sync)):
            name = str(df_a_sync.iloc[i, 2]).strip()
            no = str(df_a_sync.iloc[i, 1]).strip()
            if name and name != "nan" and "星期" not in name:
                pure_id = re.sub(r'[\s\u3000]', '', name)
                sids.append(pure_id)
                labels.append(f"{no} {name}")

        # 2. 初始化同步表格 (Session State)
        if 'sync_df' not in st.session_state or len(st.session_state.sync_df) != len(sids):
            st.session_state.sync_df = pd.DataFrame("", index=labels, columns=[f"{d+1}日" for d in range(num_days)])

        # 3. 按鈕啟動同步
        if st.button("點擊同步：將【預班表】填入下方表格", type="primary", use_container_width=True):
            new_df = st.session_state.sync_df.copy()
            for i in range(len(df_b_sync)):
                b_raw_name = str(df_b_sync.iloc[i, 2]).strip()
                b_id = re.sub(r'[\s\u3000]', '', b_raw_name)
                
                if b_id in sids:
                    row_name = labels[sids.index(b_id)]
                    for d in range(num_days):
                        val = str(df_b_sync.iloc[i, d+3]).strip().upper() if (d+3) < len(df_b_sync.columns) else ""
                        if val in ["R", "OFF", "V", "開會", "0"]:
                            new_df.loc[row_name, f"{d+1}日"] = "R"
                        elif val in ["D", "E", "N"]:
                            new_df.loc[row_name, f"{d+1}日"] = val
            st.session_state.sync_df = new_df
            st.toast("✅ 同步完成！")

        # 4. 顯示編輯器，讓你可以微調
        st.write("請確認或修改預約假：")
        final_edited_df = st.data_editor(st.session_state.sync_df, use_container_width=True)

        # 5. 下載同步後的預約表 (可選)
        out_sync = BytesIO()
        with pd.ExcelWriter(out_sync) as w: final_edited_df.to_excel(w)
        st.download_button("📥 下載這份預約資料", out_sync.getvalue(), "Synced_Vacation.xlsx")

    except Exception as e:
        st.error(f"同步過程發生錯誤: {e}")
