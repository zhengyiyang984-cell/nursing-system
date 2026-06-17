# app.py
import streamlit as st
import loader
import validator

st.title("🏥 2F 護理排班系統雛型")

# app.py (修改這一段)
uploaded_file = st.file_uploader("上傳你的排班表 (Excel)", type=["xlsx"])

if uploaded_file:
    # 這裡會自動處理 .xlsx 檔案
    df = loader.load_data(uploaded_file)
    # ... 後續程式碼不變
    st.write("### 目前排班表", df)
    
    st.write("### 兼職人員檢查 (上限 10 天)")
    staff_list = df['姓名/職級'].unique()
    for staff in staff_list:
        is_ok, count = validator.check_staff_limit(df, staff)
        if not is_ok:
            st.error(f"⚠️ {staff}: 已排 {count} 天 (超出限制)")
        else:
            st.success(f"✅ {staff}: 已排 {count} 天")
# app.py 片段範例
from validator import ScheduleValidator

# 假設 df 是你讀進來的班表
v = ScheduleValidator(df)
errors = v.validate_rules()

if errors:
    for err in errors:
        st.error(f"⚠️ 規則衝突: {err}")
else:
    st.success("✅ 排班表完全符合所有規定！")
