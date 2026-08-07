import datetime
import pandas as pd
import streamlit as st

from config import *
from loader import (
    detect_file_date_range,
    load_history_and_permission,
    load_request_and_permissions,
    merge_staff_records,
)
from utils import make_date_headers, default_manpower_by_dates
from optimizer import optimize_schedule
from schedule_statistics import build_schedule_dataframe, build_manpower_dataframe, build_person_statistics
from validator import validate_schedule, issues_to_dataframe
from exporter import export_workbook

# =====================================================
# Streamlit 主程式
# =====================================================
st.set_page_config(page_title="智慧護理排班系統", layout="wide")
st.title("🏥 智慧護理排班系統")
st.caption("支援 XLS／XLSX／CSV・自動辨識人員與跨月日期・AI 最佳化排班")

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

    file_history = st.file_uploader("上傳【上月班表】", type=["xls", "xlsx"])
    file_request = st.file_uploader("上傳【當月要班需求】", type=["csv", "xls", "xlsx"])

    auto_use_request_dates = st.checkbox(
        "自動使用要班需求檔日期",
        value=False,
        help="關閉時，以你上方手動選擇的開始／結束日期為準；開啟時，才會改用要班需求檔中的日期。"
    )

    st.divider()
    st.header("🧠 AI最佳化")
    attempts = st.slider("排班嘗試次數", 10, 500, 100, step=10)
    seed = st.number_input("隨機種子（可留 0）", min_value=0, value=0, step=1)

if end_date < start_date:
    st.error("結束日期不能早於開始日期。")
    st.stop()

# 要班需求檔日期僅作為提示；是否套用由使用者決定。
detected_start = None
detected_end = None

if file_request is not None:
    try:
        detected_start, detected_end = detect_file_date_range(file_request)

        if auto_use_request_dates:
            if (start_date, end_date) != (detected_start, detected_end):
                st.info(
                    f"已依要班需求檔自動套用排班期間："
                    f"{detected_start.strftime('%Y/%m/%d')} ～ "
                    f"{detected_end.strftime('%Y/%m/%d')}"
                )

            start_date, end_date = detected_start, detected_end

        elif (start_date, end_date) != (detected_start, detected_end):
            st.warning(
                "目前使用你手動選擇的排班期間："
                f"{start_date.strftime('%Y/%m/%d')} ～ "
                f"{end_date.strftime('%Y/%m/%d')}。"
                "要班需求檔內日期為："
                f"{detected_start.strftime('%Y/%m/%d')} ～ "
                f"{detected_end.strftime('%Y/%m/%d')}。"
                "若要自動跟隨檔案日期，請勾選左側「自動使用要班需求檔日期」。"
            )

    except Exception as exc:
        st.warning(f"無法辨識要班需求檔日期，將使用手動日期：{exc}")

num_days = (end_date - start_date).days + 1
expected_dates = [start_date + datetime.timedelta(days=i) for i in range(num_days)]
date_headers = make_date_headers(start_date, num_days)

if not file_request:
    st.info("請先上傳當月【要班需求】以啟動系統。")
    st.stop()

try:
    staff_records = merge_staff_records(file_history, file_request)
    if not staff_records:
        raise ValueError("檔案中找不到可排班人員。")
    staff_names = [record["name"] for record in staff_records]

    # 動態半職名單：由上月班表中的「半」班別自動辨識。
    detected_part_time = [record["name"] for record in staff_records if record.get("is_parttime")]
    PART_TIME[:] = detected_part_time

    requests, request_permissions = load_request_and_permissions(
        file_request, staff_records, expected_dates
    )
    history_shift, history_streak, auto_permissions = load_history_and_permission(
        file_history, staff_records
    )
except Exception as exc:
    st.error(f"班表讀取失敗：{exc}")
    st.stop()

st.success(
    f"已讀取 {len(staff_names)} 位人員；"
    f"排班期間 {start_date.strftime('%m/%d')}～{end_date.strftime('%m/%d')}；"
    f"半職 {len(PART_TIME)} 位。"
)

# 權限來源：優先使用上月班表，無法判斷時再用要班需求。
initial_permissions = {}
for nurse in staff_names:
    auto_perm = auto_permissions.get(nurse, "DEN")
    req_perm = request_permissions.get(nurse, "DEN")
    initial_permissions[nurse] = auto_perm if auto_perm != "DEN" else req_perm

st.subheader("👥 1. 人員權限與上月狀態")
st.caption("權限、上月最後班、已連上天數會自動從上月班表擷取；仍可在下方手動修正。")

config_rows = []
for nurse in staff_names:
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
        "已連上天數": st.column_config.NumberColumn("已連上天數", min_value=0, max_value=31, step=1),
    },
)

st.subheader("📊 2. 日期區間最低人力")
st.caption(
    f"目前排班期間：{start_date.strftime('%Y/%m/%d')} ～ "
    f"{end_date.strftime('%Y/%m/%d')}。"
    "下方日期區間會隨左側開始／結束日期自動重建；"
    "後面的設定列會覆蓋前面的重疊設定。"
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

manpower_editor_key = (
    f"manpower_range_editor_"
    f"{start_date.isoformat()}_"
    f"{end_date.isoformat()}"
)

rule_df = st.data_editor(
    st.session_state.manpower_rules_df,
    key=manpower_editor_key,
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
            "白班 D 最低人力", min_value=0, max_value=len(staff_names), step=1, required=True
        ),
        "E_min": st.column_config.NumberColumn(
            "小夜 E 最低人力", min_value=0, max_value=len(staff_names), step=1, required=True
        ),
        "N_min": st.column_config.NumberColumn(
            "大夜 N 最低人力", min_value=0, max_value=len(staff_names), step=1, required=True
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
        staff_names,
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
        staff_names,
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
        staff_names,
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
            1 for nurse in staff_names
            if schedule[nurse][idx] == SHIFT_D
        )
        e_count = sum(
            1 for nurse in staff_names
            if schedule[nurse][idx] == SHIFT_E
        )
        n_count = sum(
            1 for nurse in staff_names
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
        staff_names,
        manpower,
        date_headers
    )
    person_df = build_person_statistics(schedule, staff_names)

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
