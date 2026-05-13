import pandas as pd
import random
from typing import Dict, List, Tuple, Optional

def run_scheduling(
    names: List[str],
    days: int,
    hist: Dict[str, str],
    cont: Dict[str, int],
    v_table: pd.DataFrame,
    perms: Dict[str, str]
) -> Tuple[pd.DataFrame, Optional[str]]:
    """執行狀態化核心排班演算法。"""
    res = {n: [""] * days for n in names}
    
    # 初始化大夜班狀態追蹤
    n_state = {}
    for n in names:
        if hist.get(n) == "N":
            n_state[n] = cont.get(n, 1)
        else:
            n_state[n] = 0

    # --- 1. 半職1 邏輯 (預先排定) ---
    if "半職1" in names:
        pt_row = v_table.loc["半職1"]
        pt_reserved = [d for d in range(days) if str(pt_row.iloc[d]).strip().upper() in ["R", "V", "OFF"]]
        for d in pt_reserved: res["半職1"][d] = "R"
        pt_work = []
        for _ in range(3000):
            tmp, last, ok = [], -2, True
            blocks = [3, 3, 2, 2]
            random.shuffle(blocks)
            for b in blocks:
                # 確保不與預約衝突且間隔至少一天
                starts = [s for s in range(days) if s > last+1 and s+b <= days and all(s+i not in pt_reserved for i in range(b))]
                if not starts:
                    ok = False
                    break
                s = random.choice(starts)
                tmp.extend(range(s, s+b))
                last = s+b-1
            if ok and len(tmp) == 10:
                pt_work = tmp
                break
        if pt_work:
            for d in pt_work: res["半職1"][d] = "D"
        for d in range(days):
            if res["半職1"][d] == "": res["半職1"][d] = "off"

    # --- 2. 每日循環 (FT 補人) ---
    others = [n for n in names if n != "半職1"]
    
    for d in range(days):
        target = {"D": 4, "E": 3, "N": 2}
        if "半職1" in res and res["半職1"][d] == "D":
            target["D"] -= 1
        
        pool = others.copy()
        random.shuffle(pool)
        
        # Step A: 預約與固定班處理
        col_name = f"{d+1}日"
        if col_name not in v_table.columns and (d+1) in v_table.columns:
            col_name = d+1
            
        for n in others:
            val = str(v_table.loc[n, col_name]).strip().upper() if col_name in v_table.columns else ""
            if val in ["D", "E", "N"]:
                res[n][d] = val
                target[val] -= 1
                pool.remove(n)
                n_state[n] = n_state[n] + 1 if val == "N" else 0
            elif val in ["R", "V", "OFF", "開會"]:
                res[n][d] = "R"
                pool.remove(n)
                n_state[n] = 0

        # Step B: 強制大夜連續性 (4-5天)
        for n in pool[:]:
            if 0 < n_state[n] < 4:
                # 必須繼續大夜
                if "N" in perms[n].upper():
                    res[n][d] = "N"
                    target["N"] -= 1
                    n_state[n] += 1
                    pool.remove(n)
            elif n_state[n] == 4:
                # 已經 4 天，視人力需求決定是否第 5 天
                if target["N"] > 0 and random.random() > 0.5:
                    res[n][d] = "N"
                    target["N"] -= 1
                    n_state[n] += 1
                    pool.remove(n)
                else:
                    res[n][d] = "v" # 強制休息
                    n_state[n] = 0
                    pool.remove(n)

        # Step C: 強制休息 (大夜結束後第一天)
        for n in pool[:]:
            prev = res[n][d-1] if d > 0 else hist.get(n, "off")
            if prev == "N" and n_state[n] == 0:
                res[n][d] = "v"
                pool.remove(n)

        # Step D: 分配新大夜班 (確保足夠人力)
        if target["N"] > 0:
            qualified_n = [n for n in pool if "N" in perms[n].upper()]
            random.shuffle(qualified_n)
            for _ in range(target["N"]):
                if qualified_n:
                    staff = qualified_n.pop()
                    res[staff][d] = "N"
                    n_state[staff] = 1
                    target["N"] -= 1
                    pool.remove(staff)

        # Step E: 分配 E 與 D 班
        for shift in ["E", "D"]:
            qualified = [n for n in pool if shift in perms[n].upper()]
            random.shuffle(qualified)
            for _ in range(max(0, target[shift])):
                if qualified:
                    staff = qualified.pop()
                    res[staff][d] = shift
                    target[shift] -= 1
                    pool.remove(staff)

        # Step F: 剩餘人員排休
        for n in pool:
            res[n][d] = "off"
            
    return pd.DataFrame(res).T, None

