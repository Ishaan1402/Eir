"""Data Maker input from the CDC NHAMCS 2022 ED public-use file (real, de-identified, public).

    python build_input.py   # -> nhamcs_ed_train.csv (70%, goes to Data Maker), nhamcs_ed_holdout.csv (30%, stays local)

One row per adult ED visit: who arrived, how, the vitals and pain at triage, the triage level the ED gave,
and what happened. No IDs, no free text, no dates. Blank = not recorded (never imputed). The holdout never
goes to Data Maker, so a model trained on the synthetic rows can be tested on real visits it has never seen.
"""
import random
from pathlib import Path

import pandas

HERE = Path(__file__).parent
SOURCE = HERE.parents[1] / "evals/local/benchmark_data/nhamcs/ed2022_sas.sas7bdat"
SEED = 20261029
HOLDOUT = 0.30
SEX = {1: "Female", 2: "Male"}
RACE = {1: "Non-Hispanic White", 2: "Non-Hispanic Black", 3: "Hispanic", 4: "Non-Hispanic Other"}
CRITICAL_ADMIT = {1, 3, 5}  # critical care unit, operating room, cardiac catheterization lab


def outcome(r):
    if r["DIEDED"] == 1 or r["HDSTAT"] == 2 or r["ADMIT"] in CRITICAL_ADMIT:
        return "ICU, death or surgery"
    if r["ADMITHOS"] == 1 or r["OBSHOS"] == 1:
        return "Ward admission"
    if any(r[k] == 1 for k in ("TRANNH", "TRANPSYC", "TRANOTH")):
        return "Transferred"
    return "Sent home"


def num(value, lo, hi):
    return int(value) if lo <= value <= hi else None


def main():
    frame = pandas.read_sas(SOURCE, encoding="latin-1")
    rows = []
    for r in frame.to_dict("records"):
        if r["AGE"] < 18 or r["DOA"] == 1:
            continue
        temp = r["TEMPF"] / 10 if r["TEMPF"] > 0 else None
        rows.append({
            "AGE": int(r["AGE"]),
            "SEX": SEX.get(int(r["SEX"])),
            "RACE_ETHNICITY": RACE.get(int(r["RACERETH"])),
            "ARRIVED_BY_AMBULANCE": "Yes" if r["ARREMS"] == 1 else "No" if r["ARREMS"] == 2 else None,
            "HEART_RATE": num(r["PULSE"], 1, 250),
            "RESP_RATE": num(r["RESPR"], 1, 80),
            "SYSTOLIC_BP": num(r["BPSYS"], 1, 300),
            "DIASTOLIC_BP": num(r["BPDIAS"], 1, 250),
            # An SpO2 equal to the pulse and under 85 is almost always the pulse typed twice: left blank.
            "SPO2": None if r["POPCT"] == r["PULSE"] and r["POPCT"] < 85 else num(r["POPCT"], 1, 100),
            "TEMP_F": round(temp, 1) if temp and 90 <= temp <= 110 else None,
            "PAIN_0_10": num(r["PAINSCALE"], 0, 10),
            "TRIAGE_LEVEL": int(r["IMMEDR"]) if r["IMMEDR"] in (1, 2, 3, 4, 5) else None,
            "OUTCOME": outcome(r),
        })
    data = pandas.DataFrame(rows)
    for c in ("AGE", "HEART_RATE", "RESP_RATE", "SYSTOLIC_BP", "DIASTOLIC_BP", "SPO2", "PAIN_0_10", "TRIAGE_LEVEL"):
        data[c] = data[c].astype("Int64")
    # Stratified 70/30 split by outcome, fixed seed.
    rng = random.Random(SEED)
    hold = []
    for _, group in data.groupby("OUTCOME"):
        idx = list(group.index)
        rng.shuffle(idx)
        hold += idx[: round(len(idx) * HOLDOUT)]
    holdout = data.loc[sorted(hold)]
    train = data.drop(index=hold)
    train.to_csv(HERE / "nhamcs_ed_train.csv", index=False)
    holdout.to_csv(HERE / "nhamcs_ed_holdout.csv", index=False)
    print(f"{len(data)} adult visits: {len(train)} train, {len(holdout)} holdout")
    print(train.isna().mean().round(3).to_string())
    print(train["OUTCOME"].value_counts().to_string())
    print(train["ARRIVED_BY_AMBULANCE"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
