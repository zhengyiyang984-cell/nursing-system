import streamlit as st
import pandas as pd
import random

# 設定網頁佈局
st.set_page_config(page_title="2F 智慧排班系統", layout="wide")

# --- 1. 核心自動排班引擎 ---
def auto_fill_missing_shifts(df, staff_perm):
    # 定義目標人數
    TARGET = {'D': 4, 'E': 3, 'N': 2}
    
    # 針對每一天進行填補
    for day in df.columns:
        # 統計當天目前人數
        current_counts = df[day].value_counts()
        
        for shift in ['N', 'E', 'D']: # 先補夜班最難補的
            while current_counts.get(shift, 0) < TARGET.get(shift, 0):
                # 找出符合該班別權限，且當天還沒排班的人
                candidates = [
                    name for name in df.index 
                    if df.loc[name, day] not in ['D', 'E', 'N', 'R', 'V'] 
                    and shift in staff_perm.get(name, "DEN")
                ]
                
                if not candidates:
                    break # 真的補不到了
                
                # 權重補位：找目前總排班數最少的人優先
                best_candidate = min(candidates, key=lambda n: df.loc[n].isin(['D', 'E', 'N']).sum())
                df.loc[best_candidate, day] = shift
                current_counts = df[day].value_counts()
    return df

# --- 2. 界面邏輯 ---
st.title("🏥 2F 智慧排班管理系統")

# 設定人員權限 (可擴充為動態讀取)
if 'staff_perm' not in st.session_state:
    st.session_state.staff_perm = {name: "DEN" for name in ["郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", "汪家容", "林欣儀", "林怡薇"]}

with st.sidebar:
    st.subheader("⚙️ 人員權限與工時")
    st.session_state.staff_perm = st.data_editor(pd.DataFrame.from_dict(st.session_state.staff_perm, orient='index', columns=['權限']))

# 上傳預排表
uploaded_file = st.file_uploader("📂 上傳【預排休班表】", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, index_col=0)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("手動預排編輯")
        edited_df = st.data_editor(df, use_container_width=True)
    
    with col2:
        st.subheader("自動化補位")
        if st.button("🚀 執行智慧自動排班"):
            # 複製預排表進行自動化
            filled_df = auto_fill_missing_shifts(edited_df.copy(), st.session_state.staff_perm['權限'].to_dict())
            st.success("✅ 自動補位完成！")
            st.dataframe(filled_df, use_container_width=True)
            
            # 檢查規則
            violations = []
            if "郭珍君" in filled_df.index:
                pt_days = filled_df.loc["郭珍君"].isin(['D', 'E', 'N']).sum()
                if pt_days > 10: violations.append(f"❌ 郭珍君工時已達 {pt_days} 天，超過 10 天上限！")
            
            for v in violations: st.error(v)
            
            # 輸出檔案
            csv = filled_df.to_csv().encode('utf-8')
            st.download_button("📥 下載完成班表", csv, "Final_Schedule.csv")
