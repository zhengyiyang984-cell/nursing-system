import datetime
import pandas as pd
import streamlit as st

from config import *
from loader import load_request_and_permissions
from utils import make_date_headers, default_manpower_by_dates
from optimizer import optimize_schedule
from schedule_statistics import build_schedule_dataframe, build_manpower_dataframe, build_person_statistics
from validator import validate_schedule, issues_to_dataframe
from exporter import export_workbook

# =====================================================
# 自動從上月 2F 班表擷取：權限、上月最後班、已連上天數
# =====================================================
SHIFT_FOR_HISTORY = ["D", "E", "N", "M", "R", "off", "OFF", "休", "公休"]
WORK_FOR_STREAK = ["D", "E", "N", "M"]
PERMISSION_OPTIONS = ["DEN", "DE", "DN", "EN", "D", "E", "N"]

NAME_ALIASES = {
    "林怡微": ["林怡微", "林怡薇"],
    "溫鈺羚": ["溫鈺羚", "温鈺羚"],
}


def _clean_cell(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = text.replace("Ｏ", "O").replace("ｏ", "o")
    if text.upper() == "OFF":
        return "off"
    if text in ["休", "公休"]:
        return "off"
    return text


def _match_nurse(row_values, nurse):
    aliases = NAME_ALIASES.get(nurse, [nurse])
    row_text = " ".join(row_values)
    return any(alias in row_text for alias in aliases)


def _normalize_shift(value):
    value = _clean_cell(value)
    if value.upper() == "OFF":
        return "off"
    if value in ["休", "公休"]:
        return "off"
    if value in ["D", "E", "N", "M", "R", "off"]:
        return value
    return ""


def load_history_and_permission(upload_file, nurse_names):
    """
    從上月 2F 班表自動擷取：
    1. 權限：依上月實際出現過的 D/E/N 推估
    2. 上月最後班：最後一個有效班別 D/E/N/M/R/off
    3. 已連上天數：從月底往前連續 D/E/N/M 的天數
    """
    history_shift = {n: SHIFT_OFF for n in nurse_names}
    history_streak = {n: 0 for n in nurse_names}
    permissions = {n: "DEN" for n in nurse_names}

    if upload_file is None:
        return history_shift, history_streak, permissions

    df = pd.read_excel(upload_file, header=None)

    for _, row in df.iterrows():
        row_values = [_clean_cell(x) for x in row.tolist()]

        target = None
        for nurse in nurse_names:
            if _match_nurse(row_values, nurse):
                target = nurse
                break

        if target is None:
            continue

        shifts = []
        for cell in row_values:
            shift = _normalize_shift(cell)
            if shift:
                shifts.append(shift)

        if not shifts:
            continue

        history_shift[target] = shifts[-1]

        streak = 0
        for shift in reversed(shifts):
            if shift in WORK_FOR_STREAK:
                streak += 1
            else:
                break
        history_streak[target] = min(streak, MAX_CONTINUOUS_WORK)

        # 權限優先抓表格中明確權限；若沒有，就由 D/E/N 出現紀錄推估
        explicit_perm = next((cell for cell in row_values if cell in PERMISSION_OPTIONS), "")
        if explicit_perm:
            permissions[target] = explicit_perm
        else:
            inferred = ""
            if "D" in shifts:
                inferred += "D"
            if "E" in shifts:
                inferred += "E"
            if "N" in shifts:
                inferred += "N"
            if inferred:
                permissions[target] = inferred

    return history_shift, history_streak, permissions


# =====================================================
# Streamlit 主程式
# =====================================================
st.set_page_config(page_title="2F護理排班系統", layout="wide")
st.title("🏥 2F護理排班系統")
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

    file_history = st.file_uploader("上傳【上月舊班表 / 2F班表】", type=["xlsx"])
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
    requests, request_permissions = load_request_and_permissions(file_request, CORE_STAFF, num_days)
    history_shift, history_streak, auto_permissions = load_history_and_permission(file_history, CORE_STAFF)
except Exception as exc:
    st.error(f"Excel 讀取失敗：{exc}")
    st.stop()

# 權限來源：優先使用上月2F班表推估，若沒抓到再用預排休表，最後預設 DEN
initial_permissions = {}
for nurse in CORE_STAFF:
    auto_perm = auto_permissions.get(nurse, "DEN")
    req_perm = request_permissions.get(nurse, "DEN")
    initial_permissions[nurse] = auto_perm if auto_perm != "DEN" else req_perm

st.subheader("👥 1. 人員權限與上月狀態")
st.caption("權限、上月最後班、已連上天數會自動從上月2F班表擷取；仍可在下方手動修正。")

config_rows = []
for nurse in CORE_STAFF:
    config_rows.append({
        "姓名": nurse,
        "權限": initial_permissions.get(nurse, "DEN"),
        "上月最後班": history_shift.get(nurse, SHIFT_OFF),
        "已連上天數": history_streak.get(nurse, 0),
    })

config_df = st.data_editor(
    pd.DataFrame(config_rows),
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "姓名": st.column_config.TextColumn("姓名", disabled=True),
        "權限": st.column_config.SelectboxColumn("權限", options=PERMISSION_OPTIONS, required=True),
        "上月最後班": st.column_config.SelectboxColumn("上月最後班", options=ALL_SHIFTS, required=True),
        "已連上天數": st.column_config.NumberColumn("已連上天數", min_value=0, max_value=5, step=1),
    },
)

st.subheader("📊 2. 每週人力上下限")

weeks_map = {}

weeks_setup_data = []

current_week_idx = 1

last_week_no = None

for i in range(num_days):

    curr = start_date + datetime.timedelta(days=i)

    year, week_no, weekday_no = curr.isocalendar()

    if last_week_no is not None and week_no != last_week_no:
        current_week_idx += 1

    last_week_no = week_no

    is_weekend = curr.weekday() in [5, 6]

    week_label = f"第 {current_week_idx} 週"

    day_type_label = (
        "假日(六日)"
        if is_weekend
        else "平日(一五)"
    )

    weeks_map[i] = {
        "week_label": week_label,
        "is_weekend": is_weekend
    }

    key = f"{week_label} - {day_type_label}"

    exist = [
        x["週別與平假日"]
        for x in weeks_setup_data
    ]

    if key not in exist:

        if is_weekend:

            weeks_setup_data.append({
                "週別與平假日": key,
                "week_id": week_label,
                "is_we": True,

                "D_min": 3,
                "D_max": 5,

                "E_min": 2,
                "E_max": 4,

                "N_min": 2,
                "N_max": 2
            })

        else:

            weeks_setup_data.append({
                "週別與平假日": key,
                "week_id": week_label,
                "is_we": False,

                "D_min": 4,
                "D_max": 6,

                "E_min": 3,
                "E_max": 4,

                "N_min": 2,
                "N_max": 2
            })

weekly_df = st.data_editor(
    pd.DataFrame(weeks_setup_data),
    use_container_width=True,
    num_rows="fixed",
    column_config={
        "週別與平假日":
        st.column_config.TextColumn(
            "週別與平假日",
            disabled=True
        )
    }
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

for d in range(num_days):

    info = weeks_map[d]

    selected = weekly_df[
        (weekly_df["week_id"] == info["week_label"])
        &
        (weekly_df["is_we"] == info["is_weekend"])
    ].iloc[0]

    manpower.append({

        "D_min": int(selected["D_min"]),
        "D_max": int(selected["D_max"]),

        "E_min": int(selected["E_min"]),
        "E_max": int(selected["E_max"]),

        "N_min": int(selected["N_min"]),
        "N_max": int(selected["N_max"])

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
            tabs = st.tabs([
                "📅 最終班表",
                "🔍 規則檢查"
            ])
        
            with tabs[0]:
        
                col1, col2 = st.columns([4, 1])
        
                with col1:
                    st.subheader("📅 最終班表")
                    st.dataframe(
                        schedule_df,
                        use_container_width=True,
                        height=520
                    )
        
                with col2:
                    st.subheader("🌴 休假統計")
                    st.dataframe(
                        person_df,
                        use_container_width=True,
                        height=520
                    )
        
                st.subheader("📊 每日人力統計")
                st.dataframe(
                    daily_df,
                    use_container_width=True
                )
        
            with tabs[1]:
        
                if issues_df.empty:
                    st.success("沒有發現違規或提醒。")
                else:
                    st.warning("仍有需要人工確認或調整的項目。")
                    st.dataframe(
                        issues_df,
                        use_container_width=True
                    )
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
