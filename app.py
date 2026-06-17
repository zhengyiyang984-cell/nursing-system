# app.py
import streamlit as st
import loader
import scheduler
import validator

st.title("2F 護理站自動排班系統")

uploaded_file = st.file_uploader("上傳排班需求 Excel", type="xlsx")

if uploaded_file:
    data = loader.load_excel(uploaded_file)
    
    if st.button("開始排班"):
        # 1. 執行核心演算法
        raw_schedule = scheduler.generate(data)
        
        # 2. 驗證合法性
        v = validator.ScheduleValidator(raw_schedule)
        is_valid, msg = v.validate_all()
        
        if is_valid:
            st.success("排班完成！")
            st.dataframe(raw_schedule)
        else:
            st.error(f"排班失敗: {msg}")
