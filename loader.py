"""通用班表匯入工具（V27.3）。

目標：同時支援使用者目前提供的兩大類格式：
1. 舊版 2F 班表 / 預班表：日期列只有 1~31、29/30/1...，姓名欄位置不固定。
2. 新版 4W 班表 / 要班需求：XLS/XLSX/CSV、員工代碼、MM/DD 日期。

支援：
- 上月班表：.xlsx / .xls
- 當月預班 / 要班需求：.xlsx / .xls / .csv
- CSV：UTF-8 / Big5-HKSCS / CP950 / Big5
- 跨月份日期
- 依員工代碼或姓名合併
- 舊版裸日數日期欄（例如 29, 30, 1, 2 ...）
"""
from __future__ import annotations

import datetime as dt
import io
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from config import ALL_SHIFTS, SHIFT_D, SHIFT_E, SHIFT_M, SHIFT_N, SHIFT_OFF, SHIFT_R

PERMISSION_VALUES = {"DEN", "DE", "DN", "EN", "D", "E", "N"}
REQUEST_VALUES = {SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M, SHIFT_R}

# 舊檔曾出現過的姓名字形差異，可在這裡持續擴充。
NAME_ALIASES = {
    "林怡薇": "林怡微",
    "温鈺羚": "溫鈺羚",
}


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
    """讀取 xlsx、xls 或 csv，統一回傳 header=None DataFrame。"""
    name = _file_name(upload_file)
    ext = Path(name).suffix.lower()

    if ext == ".csv":
        raw = _read_bytes(upload_file)
        # 這批 4W 要班需求實際使用 Big5-HKSCS；順序很重要。
        for encoding in ("utf-8-sig", "utf-8", "big5hkscs", "cp950", "big5"):
            try:
                text = raw.decode(encoding)
                return pd.read_csv(io.StringIO(text), header=None, dtype=object)
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue

        text = raw.decode("big5hkscs", errors="replace")
        return pd.read_csv(io.StringIO(text), header=None, dtype=object)

    try:
        if hasattr(upload_file, "seek"):
            upload_file.seek(0)
        # .xls 會由 xlrd 處理；requirements.txt 已包含 xlrd>=2.0.1
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

    text = text.replace("＃", "#").rstrip("#").strip()
    upper = text.upper()

    if upper in {"D", "E", "N", "M", "R"}:
        return upper
    if upper in {"OFF", "O", "BK"}:
        return SHIFT_R if request_mode else SHIFT_OFF

    if text in {"白", "半"}:
        return SHIFT_D
    if text == "小":
        return SHIFT_E
    if text == "大":
        return SHIFT_N
    if text in {"會", "會議", "開會", "上課", "公假", "教育"}:
        return SHIFT_M

    rest_words = {
        "休", "預休", "排休", "公休", "V", "R", "旅遊", "颱補", "颱補4",
        "安胎", "產檢", "婚假", "喪假", "病假", "事假", "特休", "例休",
        "家庭照顧假", "生理假", "育嬰假", "無薪假", "陪產假", "產假",
    }
    if text in rest_words or upper in rest_words:
        return SHIFT_R if request_mode else SHIFT_OFF

    if any(word in text for word in ["颱補", "安胎", "產檢", "旅遊", "假"]):
        return SHIFT_R if request_mode else SHIFT_OFF

    return ""


def _canonical_name(value) -> str:
    text = clean_cell(value)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"PN\d+$", "", text, flags=re.IGNORECASE)
    text = NAME_ALIASES.get(text, text)
    return text.strip()


def _parse_header_date(value, year_hint: int = 2026) -> Optional[dt.date]:
    if pd.isna(value):
        return None
    if isinstance(value, (pd.Timestamp, dt.datetime, dt.date)):
        return pd.Timestamp(value).date()

    text = clean_cell(value)
    # MM/DD、YYYY/MM/DD、08/24(一) 都可辨識。
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


def _parse_filename_date_range(name: str, year_hint: int = 2026) -> Optional[Tuple[dt.date, dt.date]]:
    stem = Path(name).stem

    # ROC：115.07.27~08.23 / 115.07.27-08.23
    m = re.search(r"(?<!\d)(\d{3})[._-](\d{1,2})[._-](\d{1,2})\s*[~～\-]\s*(\d{1,2})[._-](\d{1,2})", stem)
    if m:
        year = int(m.group(1)) + 1911
        sm, sd, em, ed = map(int, m.groups()[1:])
        try:
            start = dt.date(year, sm, sd)
            end_year = year + (1 if em < sm else 0)
            end = dt.date(end_year, em, ed)
            return start, end
        except ValueError:
            pass

    # 20260824-0920
    m = re.search(r"(?<!\d)(\d{4})(\d{2})(\d{2})\s*[~～\-]\s*(\d{2})(\d{2})(?!\d)", stem)
    if m:
        y, sm, sd, em, ed = map(int, m.groups())
        try:
            start = dt.date(y, sm, sd)
            end = dt.date(y + (1 if em < sm else 0), em, ed)
            return start, end
        except ValueError:
            pass

    # 0629-0726 / 0601-0628
    m = re.search(r"(?<!\d)(\d{2})(\d{2})\s*[~～\-]\s*(\d{2})(\d{2})(?!\d)", stem)
    if m:
        sm, sd, em, ed = map(int, m.groups())
        try:
            start = dt.date(year_hint, sm, sd)
            end = dt.date(year_hint + (1 if em < sm else 0), em, ed)
            return start, end
        except ValueError:
            pass

    return None


def _int_day(value) -> Optional[int]:
    if isinstance(value, bool) or pd.isna(value):
        return None
    if isinstance(value, (int, float)) and float(value).is_integer():
        iv = int(value)
        return iv if 1 <= iv <= 31 else None
    text = clean_cell(value)
    if re.fullmatch(r"\d{1,2}", text):
        iv = int(text)
        return iv if 1 <= iv <= 31 else None
    return None


def _longest_bare_day_run(df: pd.DataFrame) -> Optional[Tuple[int, List[int], List[int]]]:
    """抓舊版表頭像 29,30,1,2... 或 1,2,3... 的最長連續日期欄。"""
    best = None
    for row_idx in range(min(len(df), 12)):
        row = df.iloc[row_idx].tolist()
        cur_cols: List[int] = []
        cur_days: List[int] = []

        def consider():
            nonlocal best, cur_cols, cur_days
            if len(cur_cols) >= 5:
                score = len(cur_cols)
                if best is None or score > best[0]:
                    best = (score, row_idx, list(cur_cols), list(cur_days))
            cur_cols, cur_days = [], []

        prev = None
        for col_idx, value in enumerate(row):
            day = _int_day(value)
            if day is None:
                consider()
                prev = None
                continue

            if not cur_days:
                cur_cols = [col_idx]
                cur_days = [day]
            else:
                expected_values = {prev + 1}
                if prev in {28, 29, 30, 31}:
                    expected_values.add(1)
                if day in expected_values:
                    cur_cols.append(col_idx)
                    cur_days.append(day)
                else:
                    consider()
                    cur_cols = [col_idx]
                    cur_days = [day]
            prev = day
        consider()

    if best is None:
        return None
    _, row_idx, cols, days = best
    return row_idx, cols, days


def detect_date_columns(
    df: pd.DataFrame,
    num_days: Optional[int] = None,
    year_hint: int = 2026,
    expected_dates: Optional[Sequence[dt.date]] = None,
    file_name: str = "",
) -> Tuple[int, List[int], List[dt.date]]:
    """同時支援完整 MM/DD 日期與舊版 1~31 裸日數。"""

    # A. 新版：完整 MM/DD / Excel date
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
        score = len(cols) + (100 if num_days and len(cols) >= num_days else 0)
        if best is None or score > best[0]:
            best = (score, row_idx, cols, dates)

    if best is not None:
        _, row_idx, cols, dates = best
        if num_days:
            if len(cols) < num_days:
                raise ValueError(f"檔案只有 {len(cols)} 個日期欄，但排班期間需要 {num_days} 天。")
            cols = cols[:num_days]
            dates = dates[:num_days]
        return row_idx, cols, dates

    # B. 舊版：29,30,1,2... / 1,2,3...
    bare = _longest_bare_day_run(df)
    if bare is None:
        raise ValueError("找不到日期欄。支援 MM/DD、Excel 日期或舊版 1~31 日期列。")

    row_idx, cols, days = bare

    if num_days and len(cols) < num_days:
        raise ValueError(f"檔案只有 {len(cols)} 個日期欄，但排班期間需要 {num_days} 天。")

    if expected_dates:
        expected_dates = list(expected_dates)
        if len(cols) < len(expected_dates):
            raise ValueError(f"檔案只有 {len(cols)} 個日期欄，但本次需要 {len(expected_dates)} 天。")
        cols = cols[:len(expected_dates)]
        days = days[:len(expected_dates)]
        mismatch = [
            (i, d, expected_dates[i].day)
            for i, d in enumerate(days)
            if d != expected_dates[i].day
        ]
        if mismatch:
            raise ValueError(
                "舊版日期列與目前選擇的排班期間不一致；"
                f"檔案開頭是 {days[:5]}，目前期間開頭是 {[x.day for x in expected_dates[:5]]}。"
            )
        return row_idx, cols, expected_dates

    filename_range = _parse_filename_date_range(file_name, year_hint=year_hint) if file_name else None
    if filename_range:
        start, end = filename_range
        dates = []
        cur = start
        while cur <= end and len(dates) < len(cols):
            dates.append(cur)
            cur += dt.timedelta(days=1)
        if len(dates) == len(cols) and all(a.day == b for a, b in zip(dates, days)):
            return row_idx, cols, dates

    # 歷史班表只需要日期欄順序，不需精確年月；建立安全的虛擬連續日期。
    base = dt.date(year_hint, 1, 1)
    dates = [base + dt.timedelta(days=i) for i in range(len(cols))]
    return row_idx, cols, dates


def detect_file_date_range(upload_file) -> Tuple[dt.date, dt.date]:
    name = _file_name(upload_file)
    df = read_table_any(upload_file)

    # 有完整 MM/DD 時，以表頭為準。
    try:
        _, _, dates = detect_date_columns(df, file_name=name)
        # 裸日數但 filename 有期間時 detect_date_columns 也會回傳正確日期。
        filename_range = _parse_filename_date_range(name)
        if filename_range and dates and dates[0].year == 2026 and dates[0].month == 1 and dates[0].day == 1:
            return filename_range
        if dates:
            # 若是虛擬日期則優先 filename。
            if filename_range:
                return filename_range
            return dates[0], dates[-1]
    except Exception:
        pass

    filename_range = _parse_filename_date_range(name)
    if filename_range:
        return filename_range
    raise ValueError("無法從檔案表頭或檔名辨識排班日期。")


def _find_header_column(df: pd.DataFrame, header_row: int, keywords: Sequence[str]) -> Optional[int]:
    for row_idx in range(max(0, header_row - 2), min(len(df), header_row + 2)):
        for col_idx, value in enumerate(df.iloc[row_idx].tolist()):
            text = clean_cell(value).replace(" ", "")
            if any(keyword.replace(" ", "") in text for keyword in keywords):
                return col_idx
    return None


def _looks_like_name(value) -> bool:
    text = _canonical_name(value)
    if not text or text in {"姓名", "姓名/職級", "公告訊息", "白班", "小夜", "大夜", "D人力", "E人力", "N人力"}:
        return False
    if text.upper() in PERMISSION_VALUES:
        return False
    # 主要支援 2~5 個中文字姓名；也允許少量英文字母。
    return bool(re.fullmatch(r"[\u4e00-\u9fff]{2,5}", text))


def _infer_name_col(df: pd.DataFrame, header_row: int, date_cols: Sequence[int]) -> Optional[int]:
    first_date = min(date_cols)
    candidates = range(0, first_date)
    best = None
    start = header_row + 1
    end = min(len(df), start + 60)
    for col in candidates:
        score = 0
        for r in range(start, end):
            if _looks_like_name(df.iat[r, col]):
                score += 1
        if best is None or score > best[0]:
            best = (score, col)
    return best[1] if best and best[0] >= 2 else None


def _infer_permission_col(df: pd.DataFrame, header_row: int, date_cols: Sequence[int]) -> Optional[int]:
    first_date = min(date_cols)
    best = None
    start = header_row + 1
    end = min(len(df), start + 60)
    for col in range(0, first_date):
        score = 0
        for r in range(start, end):
            value = clean_cell(df.iat[r, col]).upper()
            if value in PERMISSION_VALUES:
                score += 1
        if best is None or score > best[0]:
            best = (score, col)
    return best[1] if best and best[0] >= 2 else None


def _infer_code_col(df: pd.DataFrame, header_row: int) -> Optional[int]:
    return _find_header_column(df, header_row, ["員工代碼", "員工代號", "員工 代號"])


def _infer_fixed_col(df: pd.DataFrame, header_row: int) -> Optional[int]:
    return _find_header_column(df, header_row, ["固定班", "預設班別"])


def _resolve_columns(df: pd.DataFrame, header_row: int, date_cols: Sequence[int]):
    # 姓名/職級有些舊表只是標題放在日期前一欄，真正姓名卻在另一欄；因此先推估資料欄。
    inferred_name = _infer_name_col(df, header_row, date_cols)
    header_name = _find_header_column(df, header_row, ["姓名", "姓 名"])
    name_col = inferred_name if inferred_name is not None else header_name

    code_col = _infer_code_col(df, header_row)
    fixed_col = _infer_fixed_col(df, header_row)
    permission_col = _infer_permission_col(df, header_row, date_cols)
    return name_col, code_col, fixed_col, permission_col


def extract_staff_records(upload_file, expected_dates: Optional[Sequence[dt.date]] = None) -> List[dict]:
    if upload_file is None:
        return []

    df = read_table_any(upload_file)
    header_row, date_cols, _ = detect_date_columns(
        df,
        num_days=len(expected_dates) if expected_dates else None,
        expected_dates=expected_dates,
        file_name=_file_name(upload_file),
    )
    name_col, code_col, fixed_col, permission_col = _resolve_columns(df, header_row, date_cols)

    if name_col is None:
        raise ValueError(f"{Path(_file_name(upload_file)).name}：找不到姓名欄。")

    records = []
    for row_idx in range(header_row + 1, len(df)):
        name = _canonical_name(df.iat[row_idx, name_col])
        if not _looks_like_name(name):
            continue

        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        fixed = clean_cell(df.iat[row_idx, fixed_col]).upper() if fixed_col is not None else ""
        explicit_permission = clean_cell(df.iat[row_idx, permission_col]).upper() if permission_col is not None else ""
        if explicit_permission not in PERMISSION_VALUES:
            explicit_permission = ""

        row_raw = [clean_cell(df.iat[row_idx, c]) for c in date_cols]
        normalized_history = [normalize_shift(v, request_mode=False) for v in row_raw]
        is_parttime = sum(1 for value in row_raw if clean_cell(value) == "半") >= 4

        records.append({
            "code": code,
            "name": name,
            "fixed": fixed,
            "permission": explicit_permission,
            "is_parttime": is_parttime,
            "observed": normalized_history,
        })
    return records


def merge_staff_records(history_file, request_file, expected_dates: Optional[Sequence[dt.date]] = None) -> List[dict]:
    """依員工代碼優先、姓名其次合併；當月需求檔決定本次人員範圍。"""
    history = extract_staff_records(history_file) if history_file is not None else []
    request = extract_staff_records(request_file, expected_dates=expected_dates) if request_file is not None else []

    by_code: Dict[str, dict] = {}
    by_name: Dict[str, dict] = {}

    # 先 request 再 history，後續只補缺欄；姓名以 request 為主，history 補半職/權限資訊。
    for record in request + history:
        code = record.get("code", "")
        name = record.get("name", "")
        existing = by_code.get(code) if code else by_name.get(name)
        if existing is None:
            existing = dict(record)
            if code:
                by_code[code] = existing
            by_name[name] = existing
        else:
            if record.get("is_parttime"):
                existing["is_parttime"] = True
            if not existing.get("fixed") and record.get("fixed"):
                existing["fixed"] = record["fixed"]
            if not existing.get("permission") and record.get("permission"):
                existing["permission"] = record["permission"]
            if not existing.get("code") and code:
                existing["code"] = code
                by_code[code] = existing

    source = request if request else history
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


def _permission_from_record(record: dict, observed_shifts: Sequence[str]) -> str:
    explicit = clean_cell(record.get("permission", "")).upper()
    if explicit in PERMISSION_VALUES:
        return explicit

    fixed = clean_cell(record.get("fixed", "")).upper()
    if fixed in PERMISSION_VALUES:
        return fixed

    inferred = "".join(s for s in [SHIFT_D, SHIFT_E, SHIFT_N] if s in observed_shifts)
    return inferred or "DEN"


def _record_lookup(records: Sequence[dict]) -> Tuple[Dict[str, str], Dict[str, str]]:
    code_to_name = {clean_cell(r.get("code", "")): r["name"] for r in records if clean_cell(r.get("code", ""))}
    name_to_name = {_canonical_name(r["name"]): r["name"] for r in records}
    return code_to_name, name_to_name


def load_request_and_permissions(upload_file, staff_records, expected_dates: Sequence[dt.date]):
    names = [r["name"] for r in staff_records]
    requests = {n: [""] * len(expected_dates) for n in names}
    permissions = {n: "DEN" for n in names}
    if upload_file is None:
        return requests, permissions

    df = read_table_any(upload_file)
    header_row, date_cols, file_dates = detect_date_columns(
        df,
        num_days=len(expected_dates),
        expected_dates=expected_dates,
        file_name=_file_name(upload_file),
    )
    date_to_col = {date: col for date, col in zip(file_dates, date_cols)}
    name_col, code_col, fixed_col, permission_col = _resolve_columns(df, header_row, date_cols)
    code_to_name, name_to_name = _record_lookup(staff_records)
    records_by_name = {r["name"]: r for r in staff_records}

    for row_idx in range(header_row + 1, len(df)):
        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        raw_name = _canonical_name(df.iat[row_idx, name_col]) if name_col is not None else ""
        name = code_to_name.get(code) or name_to_name.get(raw_name)
        if not name:
            continue

        extracted = []
        observed = []
        for date in expected_dates:
            col = date_to_col.get(date)
            shift = normalize_shift(df.iat[row_idx, col], request_mode=True) if col is not None else ""
            extracted.append(shift if shift in REQUEST_VALUES else "")
            if shift in [SHIFT_D, SHIFT_E, SHIFT_N]:
                observed.append(shift)
        requests[name] = extracted

        explicit = clean_cell(df.iat[row_idx, permission_col]).upper() if permission_col is not None else ""
        record = dict(records_by_name.get(name, {}))
        if explicit in PERMISSION_VALUES:
            record["permission"] = explicit
        if fixed_col is not None:
            fixed = clean_cell(df.iat[row_idx, fixed_col])
            if fixed:
                record["fixed"] = fixed
        permissions[name] = _permission_from_record(record, observed)

    return requests, permissions


def load_history_and_permission(upload_file, staff_records):
    names = [r["name"] for r in staff_records]
    history_shift = {n: SHIFT_OFF for n in names}
    history_streak = {n: 0 for n in names}
    permissions = {n: "DEN" for n in names}
    if upload_file is None:
        return history_shift, history_streak, permissions

    df = read_table_any(upload_file)
    header_row, date_cols, _ = detect_date_columns(df, file_name=_file_name(upload_file))
    name_col, code_col, fixed_col, permission_col = _resolve_columns(df, header_row, date_cols)
    code_to_name, name_to_name = _record_lookup(staff_records)
    records_by_name = {r["name"]: r for r in staff_records}

    for row_idx in range(header_row + 1, len(df)):
        code = clean_cell(df.iat[row_idx, code_col]) if code_col is not None else ""
        raw_name = _canonical_name(df.iat[row_idx, name_col]) if name_col is not None else ""
        name = code_to_name.get(code) or name_to_name.get(raw_name)
        if not name:
            continue

        raw_values = [clean_cell(df.iat[row_idx, col]) for col in date_cols]
        shifts = [normalize_shift(value, request_mode=False) for value in raw_values]

        # 上月最後一天若空白，視為 off；不能用「最後一個非空班」代替。
        last = shifts[-1] if shifts else ""
        history_shift[name] = last if last in ALL_SHIFTS else SHIFT_OFF

        streak = 0
        for shift in reversed(shifts):
            if shift in [SHIFT_D, SHIFT_E, SHIFT_N, SHIFT_M]:
                streak += 1
            else:
                break
        history_streak[name] = streak

        record = dict(records_by_name.get(name, {}))
        explicit = clean_cell(df.iat[row_idx, permission_col]).upper() if permission_col is not None else ""
        if explicit in PERMISSION_VALUES:
            record["permission"] = explicit
        if fixed_col is not None:
            fixed = clean_cell(df.iat[row_idx, fixed_col])
            if fixed:
                record["fixed"] = fixed
        permissions[name] = _permission_from_record(record, shifts)

    return history_shift, history_streak, permissions
