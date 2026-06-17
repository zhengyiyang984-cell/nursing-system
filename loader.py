import pandas as pd
from config import ALL_SHIFTS, CLINICAL_SHIFTS, SHIFT_M, SHIFT_R, SHIFT_OFF

PERMISSION_VALUES = {"DEN", "DE", "DN", "EN", "D", "E", "N"}
REQUEST_VALUES = set(ALL_SHIFTS) - {SHIFT_OFF}


def clean_cell(value):
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def normalize_shift(value):
    text = clean_cell(value)
    aliases = {
        "休": SHIFT_R,
        "預休": SHIFT_R,
        "排休": SHIFT_R,
        "OFF": SHIFT_OFF,
        "Off": SHIFT_OFF,
        "off": SHIFT_OFF,
        "會": SHIFT_M,
        "會議": SHIFT_M,
        "白": "D",
        "小": "E",
        "大": "N",
    }
    return aliases.get(text, text)


def read_excel_any(upload_file):
    return pd.read_excel(upload_file, header=None, dtype=object)


def find_nurse_in_row(row_values, nurse_names):
    row_text = " ".join(clean_cell(v) for v in row_values)
    for nurse in nurse_names:
        if nurse in row_text:
            return nurse
    return None


def extract_shifts_after_name(row_values, nurse, num_days):
    values = [normalize_shift(v) for v in row_values]
    name_indexes = [i for i, v in enumerate(values) if nurse in v]
    start = (name_indexes[0] + 1) if name_indexes else 0

    extracted = []
    for v in values[start:]:
        if v in REQUEST_VALUES or v == SHIFT_OFF:
            extracted.append(v)
        elif v == "":
            extracted.append("")
        if len(extracted) >= num_days:
            break

    while len(extracted) < num_days:
        extracted.append("")
    return extracted[:num_days]


def load_request_and_permissions(upload_file, nurse_names, num_days):
    requests = {n: [""] * num_days for n in nurse_names}
    permissions = {n: "DEN" for n in nurse_names}

    if upload_file is None:
        return requests, permissions

    df = read_excel_any(upload_file)
    for _, row in df.iterrows():
        raw_values = list(row.values)
        nurse = find_nurse_in_row(raw_values, nurse_names)
        if not nurse:
            continue

        values = [clean_cell(v).upper() for v in raw_values]
        for v in values:
            if v in PERMISSION_VALUES:
                permissions[nurse] = v
                break

        requests[nurse] = extract_shifts_after_name(raw_values, nurse, num_days)

    return requests, permissions


def load_history_only(upload_file, nurse_names):
    history_shift = {n: SHIFT_OFF for n in nurse_names}
    history_streak = {n: 0 for n in nurse_names}

    if upload_file is None:
        return history_shift, history_streak

    df = read_excel_any(upload_file)
    for _, row in df.iterrows():
        raw_values = list(row.values)
        nurse = find_nurse_in_row(raw_values, nurse_names)
        if not nurse:
            continue

        shifts = []
        for v in raw_values:
            s = normalize_shift(v)
            if s in ALL_SHIFTS:
                shifts.append(s)

        if not shifts:
            continue

        history_shift[nurse] = shifts[-1]
        streak = 0
        for s in reversed(shifts):
            if s in CLINICAL_SHIFTS or s == SHIFT_M:
                streak += 1
            else:
                break
        history_streak[nurse] = streak

    return history_shift, history_streak
