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

st.subheader("📊 2. 日期區間最低人力")
st.caption(
    "可直接設定『幾號到幾號』需要多少 D／E／N 人力；後面的設定列會覆蓋前面的重疊設定。"
)

# 預設：整個排班區間分成平日與假日兩筆規則
# 使用實際日期而不是單純 1～31，跨月份時也能正確運作。
default_manpower_rules = pd.DataFrame([
    {
        "開始日期": start_date,
        "結束日期": end_date,
        "適用日": "平日",
        "D_min": 4,
        "E_min": 3,
        "N_min": 2,
    },
    {
        "開始日期": start_date,
        "結束日期": end_date,
        "適用日": "假日",
        "D_min": 3,
        "E_min": 2,
        "N_min": 2,
    },
])

# 日期範圍改變時，重建預設設定；同一日期範圍內 rerun 則保留使用者編輯值。
range_key = f"{start_date.isoformat()}_{end_date.isoformat()}"
if st.session_state.get("manpower_range_key") != range_key:
    st.session_state.manpower_range_key = range_key
    st.session_state.manpower_rules_df = default_manpower_rules

rule_df = st.data_editor(
    st.session_state.manpower_rules_df,
    key="manpower_range_editor",
    num_rows="dynamic",
    use_container_width=True,
    hide_index=True,
    column_config={
        "開始日期": st.column_config.DateColumn(
            "開始日期",
            min_value=start_date,
            max_value=end_date,
            required=True,
            format="MM/DD",
        ),
        "結束日期": st.column_config.DateColumn(
            "結束日期",
            min_value=start_date,
            max_value=end_date,
            required=True,
            format="MM/DD",
        ),
        "適用日": st.column_config.SelectboxColumn(
            "適用日",
            options=["全部", "平日", "假日"],
            required=True,
            help="全部：包含平日與六日；平日：週一至週五；假日：週六、週日。",
        ),
        "D_min": st.column_config.NumberColumn(
            "白班 D 最低人力", min_value=0, max_value=len(CORE_STAFF), step=1, required=True
        ),
        "E_min": st.column_config.NumberColumn(
            "小夜 E 最低人力", min_value=0, max_value=len(CORE_STAFF), step=1, required=True
        ),
        "N_min": st.column_config.NumberColumn(
            "大夜 N 最低人力", min_value=0, max_value=len(CORE_STAFF), step=1, required=True
        ),
    },
)

# 保存目前編輯值，避免按其他元件造成 rerun 後消失。
st.session_state.manpower_rules_df = rule_df.copy()

# 先檢查區間設定是否合法。
rule_errors = []
clean_rules = []
for row_no, (_, row) in enumerate(rule_df.iterrows(), start=1):
    try:
        rule_start = pd.to_datetime(row["開始日期"]).date()
        rule_end = pd.to_datetime(row["結束日期"]).date()
        day_type = str(row["適用日"]).strip()
        d_min = int(row["D_min"])
        e_min = int(row["E_min"])
        n_min = int(row["N_min"])
    except Exception:
        rule_errors.append(f"第 {row_no} 列資料不完整或格式不正確。")
        continue

    if rule_start > rule_end:
        rule_errors.append(f"第 {row_no} 列：開始日期不能晚於結束日期。")
        continue
    if rule_start < start_date or rule_end > end_date:
        rule_errors.append(f"第 {row_no} 列：日期必須落在本次排班期間內。")
        continue
    if day_type not in ["全部", "平日", "假日"]:
        rule_errors.append(f"第 {row_no} 列：適用日設定不正確。")
        continue

    clean_rules.append({
        "開始日期": rule_start,
        "結束日期": rule_end,
        "適用日": day_type,
        "D_min": d_min,
        "E_min": e_min,
        "N_min": n_min,
        "列號": row_no,
    })

if rule_errors:
    for message in rule_errors:
        st.error(message)
    st.stop()

# 依每天日期套用規則。若多筆重疊，較後面的列優先，方便建立特殊日期覆蓋規則。
manpower = []
uncovered_dates = []
preview_rows = []

for day_index in range(num_days):
    current_date = start_date + datetime.timedelta(days=day_index)
    is_weekend = current_date.weekday() >= 5
    current_type = "假日" if is_weekend else "平日"

    matched_rule = None
    for rule in clean_rules:
        in_range = rule["開始日期"] <= current_date <= rule["結束日期"]
        type_match = rule["適用日"] in ["全部", current_type]
        if in_range and type_match:
            # 不 break：讓後面的設定覆蓋前面的設定。
            matched_rule = rule

    if matched_rule is None:
        uncovered_dates.append(current_date)
        # 暫時填 0，下面會阻止啟動排班，避免默默使用錯誤預設值。
        today_req = {"D_min": 0, "E_min": 0, "N_min": 0}
        source_label = "未設定"
    else:
        today_req = {
            "D_min": int(matched_rule["D_min"]),
            "E_min": int(matched_rule["E_min"]),
            "N_min": int(matched_rule["N_min"]),
        }
        source_label = f"第 {matched_rule['列號']} 列"

    manpower.append(today_req)
    preview_rows.append({
        "日期": current_date,
        "星期": ["一", "二", "三", "四", "五", "六", "日"][current_date.weekday()],
        "類型": current_type,
        "D_min": today_req["D_min"],
        "E_min": today_req["E_min"],
        "N_min": today_req["N_min"],
        "套用來源": source_label,
    })

if uncovered_dates:
    missing_text = "、".join(d.strftime("%m/%d") for d in uncovered_dates[:12])
    if len(uncovered_dates) > 12:
        missing_text += f" 等共 {len(uncovered_dates)} 天"
    st.error(f"以下日期尚未設定最低人力：{missing_text}")
    st.info("請新增一筆涵蓋這些日期的規則，或建立整段日期的『全部／平日／假日』基本規則。")
    st.stop()

with st.expander("🔎 預覽每天實際套用的人力需求", expanded=False):
    st.dataframe(
        pd.DataFrame(preview_rows),
        use_container_width=True,
        hide_index=True,
        column_config={
            "日期": st.column_config.DateColumn("日期", format="MM/DD"),
        },
    )

permissions = {}
history_shift_final = {}
history_streak_final = {}
for _, row in config_df.iterrows():
    name = str(row["姓名"]).strip()
    permissions[name] = str(row["權限"]).upper().strip()
    history_shift_final[name] = str(row["上月最後班"]).strip()
    history_streak_final[name] = int(row["已連上天數"])

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

    issues = validate_schedule(
        schedule,
        CORE_STAFF,
        manpower,
        history_shift_final,
        requests
    )
    issues_df = issues_to_dataframe(issues, date_headers)

    if issues_df.empty:
        issues_df = pd.DataFrame(
            columns=["對象/類別", "日期", "班別", "提醒"]
        )

    schedule_df = build_schedule_dataframe(
        schedule,
        CORE_STAFF,
        date_headers,
        permissions
    )

    # ===== 人力統計直接加到班表底部 =====
    d_row = {col: "" for col in schedule_df.columns}
    e_row = {col: "" for col in schedule_df.columns}
    n_row = {col: "" for col in schedule_df.columns}

    d_row["姓名"] = "D人力"
    e_row["姓名"] = "E人力"
    n_row["姓名"] = "N人力"

    for idx, day in enumerate(date_headers):
        d_count = sum(
            1 for nurse in CORE_STAFF
            if schedule[nurse][idx] == SHIFT_D
        )
        e_count = sum(
            1 for nurse in CORE_STAFF
            if schedule[nurse][idx] == SHIFT_E
        )
        n_count = sum(
            1 for nurse in CORE_STAFF
            if schedule[nurse][idx] == SHIFT_N
        )

        d_row[day] = f"{d_count}/{manpower[idx]['D_min']}"
        e_row[day] = f"{e_count}/{manpower[idx]['E_min']}"
        n_row[day] = f"{n_count}/{manpower[idx]['N_min']}"

    schedule_df = pd.concat(
        [
            schedule_df,
            pd.DataFrame([d_row, e_row, n_row])
        ],
        ignore_index=True
    )

    daily_df = build_manpower_dataframe(
        schedule,
        CORE_STAFF,
        manpower,
        date_headers
    )
    person_df = build_person_statistics(schedule, CORE_STAFF)

    st.subheader("🏆 排班結果")

    c1, c2, c3 = st.columns(3)
    c1.metric("最佳分數", best["score"])
    c2.metric("違規/提醒數", len(issues))
    c3.metric("嘗試次數", attempts)

    if st.session_state.top_results:
        ranking_df = pd.DataFrame([
            {
                "排名": x["rank"],
                "分數": x["score"],
                "提醒數": len(x["issues"]),
                "seed": x["seed"]
            }
            for x in st.session_state.top_results
        ])

        with st.expander("查看前10名排班品質排行榜"):
            st.dataframe(ranking_df, use_container_width=True)

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
                height=620
            )

        with col2:
            st.subheader("🌴 休假統計")
            st.dataframe(
                person_df,
                use_container_width=True,
                height=620
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

    excel_bytes = export_workbook(
        schedule_df,
        daily_df,
        person_df,
        issues_df
    )

    st.download_button(
        "📥 下載彩色 Excel 班表",
        data=excel_bytes,
        file_name=f"2F護理排班_V3_{start_date.strftime('%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
