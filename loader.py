"""Excel 匯入工具。

V24 重點：不再以「姓名後第一個 D/E/N」當作第一天，避免把權限欄誤讀成班別。
會先偵測日期標題列與連續日期欄，再依日期欄精準擷取班別。
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from config import ALL_SHIFTS, SHIFT_D, SHIFT_E, SHIFT_M, SHIFT_N, SHIFT_OFF, SHIFT_R

PERMISSION_VALUES = {"DEN", "DE", "DN", "EN", "D", "E", "N"}
REQUEST_VALUES = {SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R}

NAME_ALIASES = {
    "林怡微": ["林怡微", "林怡薇"],
    "溫鈺羚": ["溫鈺羚", "温鈺羚"],
}


def clean_cell(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().replace("Ｏ", "O").replace("ｏ", "o")
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def normalize_shift(value, *, request_mode: bool = False) -> str:
    text = clean_cell(value)
    upper = text.upper()
    aliases = {
        "休": SHIFT_R if request_mode else SHIFT_OFF,
        "預休": SHIFT_R,
        "排休": SHIFT_R,
        "公休": SHIFT_OFF,
        "OFF": SHIFT_OFF,
        "會": SHIFT_M,
        "會議": SHIFT_M,
        "開會": SHIFT_M,
        "白": SHIFT_D,
        "小": SHIFT_E,
        "大": SHIFT_N,
        # 原始預班表以 V 表示休假；系統內統一為固定預排休 R。
        "V": SHIFT_R,
    }
    if upper in aliases:
        return aliases[upper]
    if text in aliases:
        return aliases[text]
    if upper in {SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R}:
        return upper
    if upper == "OFF":
        return SHIFT_OFF
    return ""


def read_excel_any(upload_file):
    return pd.read_excel(upload_file, header=None, dtype=object)


def _aliases(nurse: str) -> Sequence[str]:
    return NAME_ALIASES.get(nurse, [nurse])


def _match_nurse(row_values: Sequence[object], nurse_names: Iterable[str]) -> Optional[str]:
    row_text = " ".join(clean_cell(v) for v in row_values)
    for nurse in nurse_names:
        if any(alias in row_text for alias in _aliases(nurse)):
            return nurse
    return None


def _day_number(value) -> Optional[int]:
    text = clean_cell(value)
    if not text:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if 1 <= number <= 31 else None


def detect_date_columns(df: pd.DataFrame, num_days: int) -> Tuple[int, List[int]]:
    """找出日期標題列與連續日期欄。

    允許跨月（例如 29,30,1,2...），因此只要求欄位連續且值介於 1~31。
    """
    best: Optional[Tuple[int, int, List[int]]] = None
    scan_rows = min(len(df), 12)

    for row_idx in range(scan_rows):
        values = list(df.iloc[row_idx].values)
        run: List[int] = []
        runs: List[List[int]] = []
        for col_idx, value in enumerate(values):
            if _day_number(value) is not None:
                run.append(col_idx)
            else:
                if run:
                    runs.append(run)
                run = []
        if run:
            runs.append(run)

        for cols in runs:
            if len(cols) < num_days:
                continue
            candidate = cols[:num_days]
            # 日期列下方通常是星期列，給予加分。
            weekday_score = 0
            if row_idx + 1 < len(df):
                weekday_score = sum(
                    1 for c in candidate
                    if "星期" in clean_cell(df.iat[row_idx + 1, c])
                )
            score = len(candidate) * 10 + weekday_score
            if best is None or score > best[0]:
                best = (score, row_idx, candidate)

    if best is None:
        raise ValueError(f"找不到連續 {num_days} 天的日期欄。請確認第一列附近有日期數字。")
    return best[1], best[2]


def _explicit_permission(row_values: Sequence[object], date_cols: Sequence[int]) -> str:
    date_start = min(date_cols) if date_cols else len(row_values)
    # 權限通常位於日期區之前；避免把日期內容中的 D/E/N 誤認成權限。
    for value in row_values[:date_start]:
        text = clean_cell(value).upper().replace(" ", "")
        if text in PERMISSION_VALUES:
            return text
    return ""


def load_request_and_permissions(upload_file, nurse_names, num_days):
    requests = {n: [""] * num_days for n in nurse_names}
    permissions = {n: "DEN" for n in nurse_names}

    if upload_file is None:
        return requests, permissions

    df = read_excel_any(upload_file)
    header_row, date_cols = detect_date_columns(df, num_days)

    for row_idx in range(header_row + 1, len(df)):
        row_values = list(df.iloc[row_idx].values)
        nurse = _match_nurse(row_values, nurse_names)
        if not nurse:
            continue

        explicit = _explicit_permission(row_values, date_cols)
        if explicit:
            permissions[nurse] = explicit

        extracted = []
        for col in date_cols:
            shift = normalize_shift(row_values[col], request_mode=True)
            # 預班表的空白代表交由系統安排；off 也視為固定休假 R。
            if shift == SHIFT_OFF:
                shift = SHIFT_R
            extracted.append(shift if shift in REQUEST_VALUES else "")
        requests[nurse] = extracted

    return requests, permissions


def load_history_and_permission(upload_file, nurse_names, num_history_days: Optional[int] = None):
    history_shift = {n: SHIFT_OFF for n in nurse_names}
    history_streak = {n: 0 for n in nurse_names}
    permissions = {n: "DEN" for n in nurse_names}

    if upload_file is None:
        return history_shift, history_streak, permissions

    df = read_excel_any(upload_file)

    # 上月班表常為 28~31 天；未指定時選最長日期區段。
    if num_history_days is None:
        detected = None
        for days in (31, 30, 29, 28, 27, 26):
            try:
                detected = detect_date_columns(df, days)
                num_history_days = days
                break
            except ValueError:
                continue
        if detected is None:
            raise ValueError("上月班表找不到日期欄。")
        header_row, date_cols = detected
    else:
        header_row, date_cols = detect_date_columns(df, num_history_days)

    for row_idx in range(header_row + 1, len(df)):
        row_values = list(df.iloc[row_idx].values)
        nurse = _match_nurse(row_values, nurse_names)
        if not nurse:
            continue

        explicit = _explicit_permission(row_values, date_cols)
        shifts = [normalize_shift(row_values[c], request_mode=False) for c in date_cols]

        valid = [s for s in shifts if s in ALL_SHIFTS]
        if valid:
            history_shift[nurse] = valid[-1]

        streak = 0
        for shift in reversed(shifts):
            if shift in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M]:
                streak += 1
            else:
                break
        history_streak[nurse] = streak

        if explicit:
            permissions[nurse] = explicit
        else:
            inferred = "".join(s for s in [SHIFT_D, SHIFT_E, SHIFT_N] if s in shifts)
            if inferred:
                permissions[nurse] = inferred

    return history_shift, history_streak, permissions
