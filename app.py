import streamlit as st
import pandas as pd

st.set_page_config(page_title="2F 護理排班後台管理", layout="wide")

# --- 初始化儲存空間 ---
if 'config_df' not in st.session_state:
    st.session_state.config_df = pd.DataFrame({
        "權限班別": ["DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN", "DEN"],
        "上月最後班別": ["off"] * 13,
        "上月累計天數": [0] * 13
    }, index=["郭珍君", "李雅慧", "蔡靜如", "陳慧屏", "劉榆琳", "黃家靜", "許雅雯", "陳義樺", "林欣蓓", "陳萱芸", "汪家容", "林欣儀", "林怡薇"])

st.title("🏥 2F 護理排班後台管理")

# --- 1. 人員設定與狀態修改區 ---
with st.expander("⚙️ 人員權限與上月狀態設定"):
    st.write("在此處修改人員本月可上的班別（權限）、上月最後班別及天數")
    st.session_state.config_df = st.data_editor(st.session_state.config_df, use_container_width=True)

# --- 2. 上傳與顯示排班表 ---
st.subheader("📅 本月排班表編輯")
uploaded_file = st.file_uploader("上傳本月排班 Excel", type=["xlsx"])

if uploaded_file:
    df = pd.read_excel(uploaded_file, index_col=0)
    edited_df = st.data_editor(df, use_container_width=True)
    
    # --- 3. 整合驗證邏輯 ---
    if st.button("🚀 執行綜合檢查"):
        violations = []
        
        # 檢查權限是否吻合 (例如：只能上 D/E 的人卻被排了 N)
        for name in edited_df.index:
            allowed = st.session_state.config_df.loc[name, "權限班別"]
            for day_shift in edited_df.loc[name]:
                if day_shift not in ['D', 'E', 'N', 'off', 'R', 'V'] or (day_shift in ['D', 'E', 'N'] and day_shift not in allowed):
                    violations.append(f"❌ {name} 的排班 '{day_shift}' 超出其權限 '{allowed}'")
        
        # (在此處可加入您原本的 4/3/2 人數與半職天數檢查邏輯)
        
        if violations:
            for v in violations: st.error(v)
        else:
            st.success("✅ 所有班表均符合人員權限要求！")
            st.code(edited_df.to_markdown(), language="markdown")
