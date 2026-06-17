# app.py
import streamlit as st
import loader
import validator

st.title("🏥 2F 護理排班系統雛型")

uploaded_file = st.file_uploader("上傳你的排班表 (CSV)", type="csv")

if uploaded_file:
    df = loader.load_data(uploaded_file)
    st.write("### 目前排班表", df)
    
    st.write("### 兼職人員檢查 (上限 10 天)")
    staff_list = df['姓名/職級'].unique()
    for staff in staff_list:
        is_ok, count = validator.check_staff_limit(df, staff)
        if not is_ok:
            st.error(f"⚠️ {staff}: 已排 {count} 天 (超出限制)")
        else:
            st.success(f"✅ {staff}: 已排 {count} 天")
