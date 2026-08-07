"""通用班表匯入工具（V26）。

支援：
- .xlsx / .xls 上月班表
- .xlsx / .xls / .csv 當月要班需求
- 跨月份日期欄，例如 08/24 ~ 09/20
- 依員工代碼合併不同檔案中的姓名
- CSV Big5 / CP950 / UTF-8 編碼
"""
from __future__ import annotations

import datetime as dt
import io
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from config import ALL_SHIFTS, SHIFT_D, SHIFT_E, SHIFT_M, SHIFT_N, SHIFT_OFF, SHIFT_R

PERMISSION_VALUES = {"DEN", "DE", "DN", "EN", "D", "E", "N"}
REQUEST_VALUES = {SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R}


def clean_cell(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip().replace("Ｏ", "O").replace("ｏ", "o")
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _file_name(upload_file) -> str:
    return str(getattr(upload_file, "name", upload_file))


def _read_bytes(upload_file) -> bytes:
    if hasattr(upload_file, "getvalue"):
        return upload_file.getvalue()
    if hasattr(upload_file, "read"):
        try:
            upload_file.seek(0)
        except Exception:
            pass
        data = upload_file.read()
        try:
            upload_file.seek(0)
        except Exception:
            pass
        return data
    return Path(upload_file).read_bytes()


def read_table_any(upload_file) -> pd.DataFrame:
    """讀取 xlsx、xls 或 csv，統一回傳 header=None 的 DataFrame。"""
    name = _file_name(upload_file)
    ext = Path(name).suffix.lower()

    if ext == ".csv":
        raw = _read_bytes(upload_file)
        for encoding in ("utf-8-sig", "utf-8", "big5hkscs", "cp950", "big5"):
            try:
                text = raw.decode(encoding)
                return pd.read_csv(io.StringIO(text), header=None, dtype=object)
            except UnicodeDecodeError:
                continue
        # 最後保底：Big5 系列，無法辨識的單字以替代符號保留位置。
        text = raw.decode("big5hkscs", errors="replace")
        return pd.read_csv(io.StringIO(text), header=None, dtype=object)

    # pandas 讀 .xls 需要 xlrd；requirements.txt 已加入。
    try:
        if hasattr(upload_file, "seek"):
            upload_file.seek(0)
        return pd.read_excel(upload_file, header=None, dtype=object)
    finally:
        try:
            upload_file.seek(0)
        except Exception:
            pass


def normalize_shift(value, *, request_mode: bool = False) -> str:
    text = clean_cell(value)
    if not text:
        return ""

    # 要班 CSV 常帶 #，例如 R#、V#、E#、開會#。
    text = text.replace("＃", "#").rstrip("#").strip()
    upper = text.upper()

    if upper in {"D", "E", "N", "M", "R"}:
        return upper
    if upper in {"OFF", "O", "BK"}:
        return SHIFT_R if request_mode else SHIFT_OFF

    # 半職工作日視為白班；上課、開會不計臨床人力。
    if text in {"白", "半"}:
        return SHIFT_D
    if text in {"小"}:
        return SHIFT_E
    if text in {"大"}:
        return SHIFT_N
    if text in {"會", "會議", "開會", "上課", "公假", "教育"}:
        return SHIFT_M

    # 假別均視為休假。要班檔中固定成 R；歷史檔中視為 off。
    rest_words = {
        "休", "預休", "排休", "公休", "V", "R", "旅遊", "颱補", "颱補4",
        "安胎", "產檢", "婚假", "喪假", "病假", "事假", "特休", "例休",
    }
    if text in rest_words or upper in rest_words:
        return SHIFT_R if request_mode else SHIFT_OFF

    # 部分儲存格帶時數，如 颱補2.5、颱補6.5。
    if any(word in text for word in ["颱補", "安胎", "產檢", "旅遊", "假"]):
        return SHIFT_R if request_mode else SHIFT_OFF

    return ""


def _parse_header_date(value, year_hint: int = 2026) -> Optional[dt.date]:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return pd.Timestamp(value).date()

    text = clean_cell(value)
    match = re.search(r"(?:(\d{4})[./-])?(\d{1,2})[./-](\d{1,2})", text)
    if not match:
        return None
    year = int(match.group(1) or year_hint)
    month = int(match.group(2))
    day = int(match.group(3))
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def detect_date_columns(
    df: pd.DataFrame,
    num_days: Optional[int] = None,
    year_hint: int = 2026,
) -> Tuple[int, List[int], List[dt.date]]:
    """偵測含完整日期或 MM/DD 的標題列。"""
    best = None
    for row_idx in range(min(len(df), 15)):
        cols: List[int] = []
        dates: List[dt.date] = []
        for col_idx, value in enumerate(df.iloc[row_idx].tolist()):
            parsed = _parse_header_date(value, year_hint=year_hint)
            if parsed is not None:
                cols.append(col_idx)
                dates.append(parsed)

        if len(cols) < 2:
            continue
        score = len(cols)
        if num_days and len(cols) >= num_days:
            score += 100
        if best is None or score > best[0]:
            best = (score, row_idx, cols, dates)

    if best is None:
        raise ValueError("找不到日期欄，請確認檔案上方有 08/24、09/01 或 Excel 日期格式。")

    _, row_idx, cols, dates = best
    if num_days:
        if len(cols) < num_days:
            raise ValueError(f"檔案只有 {len(cols)} 個日期欄，但排班期間需要 {num_days} 天。")
        cols = cols[:num_days]
        dates = dates[:num_days]
    return row_idx, cols, dates


def detect_file_date_range(upload_file) -> Tuple[dt.date, dt.date]:
    df = read_table_any(upload_file)
    _, _, dates = detect_date_columns(df)
    return dates[0], dates[-1]


def _find_header_column(df: pd.DataFrame, header_row: int, keywords: Sequence[str]) -> Optional[int]:
    for col_idx, value in enumerate(df.iloc[header_row].tolist()):
        text = clean_cell(value).replace(" ", "")
        if any(keyword.replace(" ", "") in text for keyword in keywords):
            return col_idx
    return None


def _clean_name(value) -> str:
    text = clean_cell(value)
    # 歷史班表姓名可能為「彭淑琴PN3」。
    text = re.sub(r"PN\d+$", "", text, flags=re.IGNORECASE)
    return text.strip()


def extract_staff_records(upload_file) -> List[dict]:
    """擷取員工代碼、姓名、固定班與是否半職。"""
    if upload_file is None:
        return []
    df = read_table_any(upload_file)
    header_row, date_cols, _ = detect_date_columns(df)

    name_col = _find_header_column(df, header_row, ["姓名", "姓 名"])
    code_col = _find_header_column(df, header_row, ["員工代碼", "員工代號", "員工 代號"])
    fixed_col = _find_header_column(df, header_row, ["固定班", "預設班別"])

    if name_col is None:
        raise ValueError("找不到姓名欄。")

    records = []
    for row_idx in range(header_row + 1, len(df)):
        name = _clean_name(df.iat[row_idx, name_col])
        if not name or name in {"公告訊息", "姓名"}:
            continue
        # 過濾人力統計列與說明列。
        if name in {"D人力", "E人力", "N人力", "白班", "小夜", "大夜"}:
            continue

        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        fixed = clean_cell(df.iat[row_idx, fixed_col]).upper() if fixed_col is not None else ""
        row_shifts = [clean_cell(df.iat[row_idx, c]) for c in date_cols]
        is_parttime = sum(1 for value in row_shifts if value == "半") >= 4

        records.append({
            "code": code,
            "name": name,
            "fixed": fixed,
            "is_parttime": is_parttime,
        })
    return records


def merge_staff_records(history_file, request_file) -> List[dict]:
    """依員工代碼合併，優先採用上月班表中的完整姓名。"""
    history = extract_staff_records(history_file) if history_file is not None else []
    request = extract_staff_records(request_file) if request_file is not None else []

    by_code: Dict[str, dict] = {}
    by_name: Dict[str, dict] = {}

    for record in history + request:
        code = record.get("code", "")
        name = record.get("name", "")
        key_record = by_code.get(code) if code else by_name.get(name)
        if key_record is None:
            key_record = dict(record)
            if code:
                by_code[code] = key_record
            by_name[name] = key_record
        else:
            # 上月班表常有較完整姓名與半職資訊。
            if record.get("is_parttime"):
                key_record["is_parttime"] = True
            if not key_record.get("fixed") and record.get("fixed"):
                key_record["fixed"] = record["fixed"]

    # 只排當月需求檔中出現的人；若沒有需求檔才使用歷史名單。
    request_codes = {r.get("code") for r in request if r.get("code")}
    request_names = {r.get("name") for r in request}
    source = []
    for record in (history + request):
        if request:
            if record.get("code") and record.get("code") not in request_codes:
                continue
            if not record.get("code") and record.get("name") not in request_names:
                continue
        source.append(record)

    result = []
    seen = set()
    for record in source:
        merged = by_code.get(record.get("code")) if record.get("code") else by_name.get(record.get("name"))
        if not merged:
            continue
        identity = merged.get("code") or merged.get("name")
        if identity in seen:
            continue
        seen.add(identity)
        result.append(merged)
    return result


def _permission_from_fixed(fixed: str, shifts: Sequence[str]) -> str:
    fixed = clean_cell(fixed).upper()
    if fixed in PERMISSION_VALUES:
        return fixed
    # P、HN、ICT 等特殊類別先依歷史實際班別推估；無資料則 DEN。
    inferred = "".join(s for s in [SHIFT_D, SHIFT_E, SHIFT_N] if s in shifts)
    return inferred or "DEN"


def _record_lookup(records: Sequence[dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    code_to_name = {r.get("code", ""): r["name"] for r in records if r.get("code")}
    name_to_name = {r["name"]: r["name"] for r in records}
    return code_to_name, name_to_name


def load_request_and_permissions(upload_file, staff_records, expected_dates: Sequence[dt.date]):
    names = [r["name"] for r in staff_records]
    requests = {n: [""] * len(expected_dates) for n in names}
    permissions = {n: "DEN" for n in names}
    if upload_file is None:
        return requests, permissions

    df = read_table_any(upload_file)
    header_row, date_cols, file_dates = detect_date_columns(df)
    date_to_col = {date: col for date, col in zip(file_dates, date_cols)}

    name_col = _find_header_column(df, header_row, ["姓名", "姓 名"])
    code_col = _find_header_column(df, header_row, ["員工代碼", "員工代號", "員工 代號"])
    fixed_col = _find_header_column(df, header_row, ["固定班", "預設班別"])
    code_to_name, name_to_name = _record_lookup(staff_records)

    for row_idx in range(header_row + 1, len(df)):
        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        raw_name = _clean_name(df.iat[row_idx, name_col]) if name_col is not None else ""
        name = code_to_name.get(code) or name_to_name.get(raw_name)
        if not name:
            continue

        fixed = clean_cell(df.iat[row_idx, fixed_col]) if fixed_col is not None else ""
        extracted = []
        observed = []
        for date in expected_dates:
            col = date_to_col.get(date)
            shift = normalize_shift(df.iat[row_idx, col], request_mode=True) if col is not None else ""
            extracted.append(shift if shift in REQUEST_VALUES else "")
            if shift in [SHIFT_D, SHIFT_E, SHIFT_N]:
                observed.append(shift)
        requests[name] = extracted
        permissions[name] = _permission_from_fixed(fixed, observed)

    return requests, permissions


def load_history_and_permission(upload_file, staff_records):
    names = [r["name"] for r in staff_records]
    history_shift = {n: SHIFT_OFF for n in names}
    history_streak = {n: 0 for n in names}
    permissions = {n: "DEN" for n in names}
    if upload_file is None:
        return history_shift, history_streak, permissions

    df = read_table_any(upload_file)
    header_row, date_cols, _ = detect_date_columns(df)
    name_col = _find_header_column(df, header_row, ["姓名", "姓 名"])
    code_col = _find_header_column(df, header_row, ["員工代碼", "員工代號", "員工 代號"])
    fixed_col = _find_header_column(df, header_row, ["固定班", "預設班別"])
    code_to_name, name_to_name = _record_lookup(staff_records)

    for row_idx in range(header_row + 1, len(df)):
        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        raw_name = _clean_name(df.iat[row_idx, name_col]) if name_col is not None else ""
        name = code_to_name.get(code) or name_to_name.get(raw_name)
        if not name:
            continue

        raw_values = [clean_cell(df.iat[row_idx, col]) for col in date_cols]
        shifts = [normalize_shift(value, request_mode=False) for value in raw_values]
        valid = [shift for shift in shifts if shift in ALL_SHIFTS]
        if valid:
            history_shift[name] = valid[-1]

        streak = 0
        for shift in reversed(shifts):
            if shift in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M]:
                streak += 1
            else:
                break
        history_streak[name] = streak

        fixed = clean_cell(df.iat[row_idx, fixed_col]) if fixed_col is not None else ""
        permissions[name] = _permission_from_fixed(fixed, shifts)

    return history_shift, history_streak, permissions
