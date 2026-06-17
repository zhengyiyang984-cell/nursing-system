import pandas as pd

SHIFT_LIST = ["D", "E", "N", "M", "R", "off"]


def clean(v):
    if pd.isna(v):
        return ""
    return str(v).strip()


def load_history_only(upload_file, nurse_names):
    """
    讀取上月班表
    回傳：
        history_shift
        history_streak
    """

    history_shift = {n: "off" for n in nurse_names}
    history_streak = {n: 0 for n in nurse_names}

    if upload_file is None:
        return history_shift, history_streak

    df = pd.read_excel(upload_file, header=None)

    for _, row in df.iterrows():

        row = [clean(x) for x in row]

        text = " ".join(row)

        target = None

        for nurse in nurse_names:
            if nurse in text:
                target = nurse
                break

        if target is None:
            continue

        shifts = []

        for item in row:

            if item in SHIFT_LIST:
                shifts.append(item)

        if len(shifts) == 0:
            continue

        history_shift[target] = shifts[-1]

        streak = 0

        for s in reversed(shifts):

            if s in ["D", "E", "N", "M"]:
                streak += 1
            else:
                break

        history_streak[target] = streak

    return history_shift, history_streak


def load_request(upload_file, nurse_names, num_days):
    """
    讀預排休
    """

    requests = {
        n: [""] * num_days
        for n in nurse_names
    }

    permissions = {
        n: "DEN"
        for n in nurse_names
    }

    if upload_file is None:
        return requests, permissions

    df = pd.read_excel(upload_file, header=None)

    for _, row in df.iterrows():

        row = [clean(x) for x in row]

        target = None

        for nurse in nurse_names:
            if nurse in row:
                target = nurse
                break

        if target is None:
            continue

        # 找權限
        for item in row:

            if item in [
                "DEN",
                "DE",
                "DN",
                "EN",
                "D",
                "E",
                "N"
            ]:

                permissions[target] = item

        shifts = []

        for item in row:

            if item in [
                "D",
                "E",
                "N",
                "M",
                "R"
            ]:

                shifts.append(item)

            else:

                shifts.append("")

        requests[target] = shifts[:num_days]

    return requests, permissions
