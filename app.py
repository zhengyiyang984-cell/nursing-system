import streamlit as st
import pandas as pd
from io import BytesIO

st.set_page_config(page_title="2F 護理排班審核系統", layout="wide")

# --- 1. 核心臨床驗證器 ---
def validate_clinical_rules(df, part_time_names):
    violations = []
    
    # 檢查 1: 每日 4/3/2 配置
    for col in df.columns:
        counts = df[col].value_counts()
        if counts.get('D', 0) != 4 or counts.get('E', 0) != 3 or counts.get('N', 0) != 2:
            violations.append(f"❌ {col} 人數未達 4/3/2 (D:{counts.get('D',0)} E:{counts.get('E',0)} N:{counts.get('N',0)})")

    # 檢查 2: 半職人員 (不超過 10 天)
    for name in part_time_names:
        if name in df.index:
            days_worked = df.loc[name].isin(['D', 'E', 'N']).sum()
            if days_worked > 10:
                violations.append(f"❌ {name} 半職工作天數超過 10 天 (共 {days_worked} 天)")

    # 檢查 3: 連續夜班 (N) 不超過 5 天
    for name in df.index:
        n_streak = 0
        for day in df.loc[name]:
            if day == 'N':
                n_streak += 1
                if n_streak > 5:
                    violations.append(f"❌ {name} 連續夜班已達 {n_streak} 天，請調整！")
                    break
            else:
                n_streak = 0
    return violations

# --- 2. 網頁操作介面 ---
st.title("🏥 2F 護理排班臨床審核系統")

uploaded_file = st.file_uploader("請上傳排班 Excel 檔", type=["xlsx"])

if uploaded_file:
    # 讀取並顯示表格
    df = pd.read_excel(uploaded_file, index_col=0)
    st.write("請在下方直接修改班表，確認無誤後點擊檢查：")
    edited_df = st.data_editor(df, use_container_width=True)
    
    if st.button("🚀 執行臨床規範總檢查"):
        # 設定半職人員清單
        part_time_staff = ["郭珍君"]
        
        errors = validate_clinical_rules(edited_df, part_time_staff)
        
        if not errors:
            st.success("🎉 全月排班完美通過所有臨床規範！")
            st.balloons()
        else:
            for err in errors:
                st.error(err)
        
        # 產出符合 Markdown 格式的檢查報告
        st.subheader("📋 班表檢查報告 (Markdown)")
        st.code(edited_df.to_markdown(), language="markdown")
