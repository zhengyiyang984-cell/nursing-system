import datetime
import pandas as pd
import streamlit as st

from config import *
from loader import load_request_and_permissions, load_history_only
from utils import make_date_headers, default_manpower_by_dates
from optimizer import optimize_schedule
from schedule_statistics import build_schedule_dataframe, build_manpower_dataframe, build_person_statistics
from validator import validate_schedule, issues_to_dataframe
from exporter import export_workbook

st.set_page_config(page_title="2F護理排班系統 V3.0", layout="wide")
st.title("🏥 2F護理排班系統 V3.0")
st.caption("AI最佳化・N→N→off→off・最多連上5天・全職休假保底・郭珍君10天D班")

if "best_result" not in st.session_state:
    st.session_state.best_result = None
if "top_results" not in st.session_state:
    st.session_state.top_results = []

with st.sidebar:
    st.header("📅 日期與檔案")
    today = datetime.date.today()
    default_start = today.replace(day=1)
    start_date = st.date_input("開始日期", default_start)
    end_date = st.date_input("結束日期", today)

    file_history = st.file_uploader("上傳【上月舊班表】", type=["xlsx"])
    file_request = st.file_uploader("上傳【當月預排休表】", type=["xlsx"])

    st.divider()
    st.header("🧠 AI最佳化")
    attempts = st.slider("排班嘗試次數", 10, 500, 100, step=10)
    seed = st.number_input("隨機種子（可留 0）", min_value=0, value=0, step=1)

if end_date < start_date:
    st.error("結束日期不能早於開始日期。")
    st.stop()

num_days = (end_date - start_date).days + 1
date_headers = make_date_headers(start_date, num_days)

if not file_request:
    st.info("請先上傳當月【預排休表】以啟動系統。")
    st.stop()

try:
    requests, extracted_permissions = load_request_and_permissions(file_request, CORE_STAFF, num_days)
    history_shift, history_streak = load_history_only(file_history, CORE_STAFF)
except Exception as exc:
    st.error(f"Excel 讀取失敗：{exc}")
    st.stop()

st.subheader("👥 1. 人員權限與上月狀態")
config_rows = []
for nurse in CORE_STAFF:
    config_rows.append({
        "姓名": nurse,
        "權限": extracted_permissions.get(nurse, "DEN"),
        "上月最後班": history_shift.get(nurse, SHIFT_OFF),
        "已連上天數": history_streak.get(nurse, 0),
    })

config_df = st.data_editor(
    pd.DataFrame(config_rows),
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "姓名": st.column_config.TextColumn("姓名", disabled=True),
        "權限": st.column_config.SelectboxColumn("權限", options=["DEN", "DE", "DN", "EN", "D", "E", "N"], required=True),
        "上月最後班": st.column_config.SelectboxColumn("上月最後班", options=ALL_SHIFTS, required=True),
        "已連上天數": st.column_config.NumberColumn("已連上天數", min_value=0, max_value=5, step=1),
    },
)

st.subheader("📊 2. 每日人力上下限")
default_manpower = default_manpower_by_dates(start_date, num_days)
manpower_editor = []
for d in range(num_days):
    row = {"日期": date_headers[d]}
    row.update(default_manpower[d])
    manpower_editor.append(row)

manpower_df = st.data_editor(
    pd.DataFrame(manpower_editor),
    use_container_width=True,
    num_rows="fixed",
    column_config={"日期": st.column_config.TextColumn("日期", disabled=True)},
)

permissions = {}
history_shift_final = {}
history_streak_final = {}
for _, row in config_df.iterrows():
    name = str(row["姓名"]).strip()
    permissions[name] = str(row["權限"]).upper().strip()
    history_shift_final[name] = str(row["上月最後班"]).strip()
    history_streak_final[name] = int(row["已連上天數"])

manpower = []
for _, row in manpower_df.iterrows():
    manpower.append({
        "D_min": int(row["D_min"]), "D_max": int(row["D_max"]),
        "E_min": int(row["E_min"]), "E_max": int(row["E_max"]),
        "N_min": int(row["N_min"]), "N_max": int(row["N_max"]),
    })

st.divider()
run = st.button("🚀 啟動 AI 最佳化排班", type="primary", use_container_width=True)

if run:
    progress = st.progress(0)
    status = st.empty()

    def update_progress(done, total, best_score):
        progress.progress(done / total)
        status.write(f"已完成 {done}/{total} 次，目前最佳分數：{best_score}")

    best, top = optimize_schedule(
        CORE_STAFF,
        permissions,
        requests,
        manpower,
        history_shift_final,
        history_streak_final,
        attempts=attempts,
        base_seed=None if seed == 0 else int(seed),
        progress_callback=update_progress,
    )
    st.session_state.best_result = best
    st.session_state.top_results = top
    st.success(f"排班完成，最佳分數：{best['score']}")

if st.session_state.best_result:
    best = st.session_state.best_result
    schedule = best["schedule"]
    issues = validate_schedule(schedule, CORE_STAFF, manpower, history_shift_final, requests)
    issues_df = issues_to_dataframe(issues, date_headers)
    if issues_df.empty:
        issues_df = pd.DataFrame(columns=["對象/類別", "日期", "班別", "提醒"])

    schedule_df = build_schedule_dataframe(schedule, CORE_STAFF, date_headers, permissions)
    daily_df = build_manpower_dataframe(schedule, CORE_STAFF, manpower, date_headers)
    person_df = build_person_statistics(schedule, CORE_STAFF)

    st.subheader("🏆 排班結果")
    c1, c2, c3 = st.columns(3)
    c1.metric("最佳分數", best["score"])
    c2.metric("違規/提醒數", len(issues))
    c3.metric("嘗試次數", attempts)

    if st.session_state.top_results:
        ranking_df = pd.DataFrame([
            {"排名": x["rank"], "分數": x["score"], "提醒數": len(x["issues"]), "seed": x["seed"]}
            for x in st.session_state.top_results
        ])
        with st.expander("查看前10名排班品質排行榜"):
            st.dataframe(ranking_df, use_container_width=True)

    tabs = st.tabs(["📅 最終班表", "📊 每日人力", "👤 個人統計", "🔍 規則檢查"])
    with tabs[0]:
        st.dataframe(schedule_df, use_container_width=True, height=520)
    with tabs[1]:
        st.dataframe(daily_df, use_container_width=True)
    with tabs[2]:
        st.dataframe(person_df, use_container_width=True)
    with tabs[3]:
        if issues_df.empty:
            st.success("沒有發現違規或提醒。")
        else:
            st.warning("仍有需要人工確認或調整的項目。")
            st.dataframe(issues_df, use_container_width=True)

    excel_bytes = export_workbook(schedule_df, daily_df, person_df, issues_df)
    st.download_button(
        "📥 下載彩色 Excel 班表",
        data=excel_bytes,
        file_name=f"2F護理排班_V3_{start_date.strftime('%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
