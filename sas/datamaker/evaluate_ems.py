"""Did Data Maker keep the rules of our fictitious EMS table? Checks its output against the input it learned from.

    python evaluate_ems.py ~/Downloads/<data maker output>.csv   # -> results/EIR_SYNTH_EMS_CHECKS.csv

The input (datamaker_test/ems_test_annotations.csv) is made by rules, so each rule is a test: a synthetic row
that breaks one (say SBP 70 labelled "Routine awareness") is a utility failure. The real column is the
input itself, so each rule shows how often it holds there (100% by construction, apart from the deliberate
10% label flips between the two lowest categories) next to how often it holds in the synthetic rows.
"""
import sys
from pathlib import Path

import pandas

HERE = Path(__file__).parent
REAL = HERE.parents[1] / "datamaker_test/ems_test_annotations.csv"
OUT = HERE / "results"
NUM = ["update_number", "elapsed_minutes", "eta_minutes", "age", "heart_rate", "systolic_bp", "diastolic_bp", "resp_rate",
       "spo2_pct", "glucose_mg_dl", "temp_c", "prior_heart_rate", "prior_systolic_bp", "prior_spo2_pct"]


def load(path):
    f = pandas.read_csv(path)
    f.columns = [c.strip().lower() for c in f.columns]
    for c in NUM:
        if c in f:
            f[c] = pandas.to_numeric(f[c], errors="coerce")
    return f


def red_flag(f):
    return ((f.systolic_bp < 90) | (f.spo2_pct < 90) | (f.resp_rate < 10) | (f.resp_rate > 28) | (f.heart_rate > 130)
            | (f.heart_rate < 45) | f.mental_status.isin(["Responds to pain", "Unresponsive"]) | (f.glucose_mg_dl < 60)
            | (f.chief_complaint == "Stroke symptoms") | ((f.intervention == "Epinephrine") & (f.chief_complaint == "Allergic reaction")))


def rate(mask, of):
    of = of.fillna(False)
    return round(float(mask[of].fillna(False).mean()), 3) if of.sum() else None, int(of.sum())


RULES = [
    ("A stated red flag is labelled Prepare now", lambda f: (f.attention_category == "Prepare now", red_flag(f))),
    ("Cannot assess always goes with Needs Review", lambda f: (f.app_case_status == "Needs Review", f.attention_category == "Cannot assess")),
    ("Cannot assess only when key vitals are missing",
     lambda f: ((f.systolic_bp.isna() & f.spo2_pct.isna()) | (f.heart_rate.isna() & f.systolic_bp.isna()), f.attention_category == "Cannot assess")),
    ("First reports have no prior heart rate", lambda f: (f.prior_heart_rate.isna(), f.update_number == 1)),
    ("First reports say No prior information", lambda f: (f.meaningful_change == "No prior information", f.update_number == 1)),
    ("Epinephrine only for allergic reactions", lambda f: (f.chief_complaint == "Allergic reaction", f.intervention == "Epinephrine")),
    ("Low blood sugar (< 60) only with AMS, low sugar, stroke or seizure",
     lambda f: (f.chief_complaint.isin(["Altered mental status", "Low blood sugar", "Stroke symptoms", "Seizure"]), f.glucose_mg_dl < 60)),
    ("Review happens after the report",
     lambda f: (pandas.to_datetime(f.reviewed_at_utc, errors="coerce", utc=True) > pandas.to_datetime(f.report_time_utc, errors="coerce", utc=True),
                f.reviewed_at_utc.notna() & f.report_time_utc.notna())),
]


def main(path):
    real, synth = load(REAL), load(path)
    rows = []
    for name, rule in RULES:
        r, rn = rate(*rule(real))
        try:
            s, sn = rate(*rule(synth))
        except Exception as e:  # a column Data Maker dropped or renamed
            s, sn = None, 0
            name += f" (not checkable: {e})"
        rows.append({"CHECK": "Rule kept", "MEASURE": name, "REAL": r, "SYNTHETIC": s,
                     "NOTE": f"share of rows the rule applies to that keep it; real n={rn}, synthetic n={sn}"})
    for c in ["attention_category", "chief_complaint", "mental_status", "sex", "meaningful_change"]:
        a, b = real[c].fillna("(blank)").value_counts(normalize=True), synth[c].fillna("(blank)").value_counts(normalize=True)
        sim = 1 - 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in a.index.union(b.index))
        rows.append({"CHECK": "Fidelity", "MEASURE": f"{c} distribution similarity", "REAL": 1.0, "SYNTHETIC": round(sim, 3),
                     "NOTE": "1 - total variation distance"})
    key = [c for c in real.columns if c in synth.columns and c not in ("case_id", "reviewer_id")]
    copies = len(set(map(tuple, synth[key].astype(str).to_numpy())) & set(map(tuple, real[key].astype(str).to_numpy())))
    rows.append({"CHECK": "Privacy", "MEASURE": "Synthetic rows identical to an input row", "REAL": None, "SYNTHETIC": copies,
                 "NOTE": f"of {len(synth)} synthetic rows"})
    OUT.mkdir(exist_ok=True)
    table = pandas.DataFrame(rows)
    table.to_csv(OUT / "EIR_SYNTH_EMS_CHECKS.csv", index=False)
    pandas.set_option("display.width", 220, "display.max_colwidth", 90)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
