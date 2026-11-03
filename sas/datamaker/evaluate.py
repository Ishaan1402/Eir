"""Is Data Maker's synthetic copy of the NHAMCS visits faithful, private and useful? Checked against real visits.

    python evaluate.py ~/Downloads/<data maker output>.csv     # -> results/ (json + csv tables for CAS/VA)

- Fidelity: each column's distribution (1 - total variation distance; numbers in clinical bins), and links
  that matter clinically: outcome by low blood pressure, low SpO2 and triage level.
- Privacy: synthetic rows that exactly copy a training row, and each synthetic row's distance to its closest
  training row next to the same distance for real holdout visits (a synthetic set much closer than real
  unseen visits would suggest memorised rows).
- Usefulness ("train on synthetic, test on real"): the same gradient boosting model trained once on the
  real training rows and once on the synthetic rows, both scored on the real 30% holdout Data Maker never saw.
"""
import json
import sys
from pathlib import Path

import numpy
import pandas
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import roc_auc_score

HERE = Path(__file__).parent
OUT = HERE / "results"
NUMERIC = ["AGE", "HEART_RATE", "RESP_RATE", "SYSTOLIC_BP", "DIASTOLIC_BP", "SPO2", "TEMP_F", "PAIN_0_10"]
CATEGORICAL = ["SEX", "RACE_ETHNICITY", "ARRIVED_BY_AMBULANCE", "TRIAGE_LEVEL", "OUTCOME"]
BINS = {
    "AGE": [18, 30, 45, 65, 80, 200], "HEART_RATE": [0, 50, 60, 100, 120, 140, 400],
    "RESP_RATE": [0, 10, 12, 20, 24, 30, 200], "SYSTOLIC_BP": [0, 90, 100, 140, 180, 400],
    "DIASTOLIC_BP": [0, 60, 90, 110, 300], "SPO2": [0, 88, 92, 95, 101], "TEMP_F": [0, 96.8, 100.4, 102.2, 200],
    "PAIN_0_10": [-1, 0, 3, 6, 8, 11],
}
TARGETS = {"Admitted, ICU, death or surgery": ["Ward admission", "ICU, death or surgery"],
           "ICU, death or surgery": ["ICU, death or surgery"]}
SEED = 20261029


def load(path):
    frame = pandas.read_csv(path)
    frame.columns = [c.strip().upper() for c in frame.columns]
    missing = [c for c in NUMERIC + CATEGORICAL if c not in frame.columns]
    if missing:
        raise SystemExit(f"{path}: missing columns {missing}")
    for c in NUMERIC:
        frame[c] = pandas.to_numeric(frame[c], errors="coerce")
    frame["TRIAGE_LEVEL"] = pandas.to_numeric(frame["TRIAGE_LEVEL"], errors="coerce").round().astype("Int64").astype(str).replace("<NA>", numpy.nan)
    for c in CATEGORICAL:
        frame[c] = frame[c].astype("string").str.strip().replace({"": pandas.NA})
    return frame[NUMERIC + CATEGORICAL]


def binned(series, column):
    if column in BINS:
        return pandas.cut(series, BINS[column], right=False).astype(str).where(series.notna(), "(blank)")
    return series.fillna("(blank)").astype(str)


def similarity(real, synth, column):
    a = binned(real[column], column).value_counts(normalize=True)
    b = binned(synth[column], column).value_counts(normalize=True)
    keys = a.index.union(b.index)
    return 1 - 0.5 * sum(abs(a.get(k, 0) - b.get(k, 0)) for k in keys)


def share(frame, mask_col, condition, outcome_values):
    rows = frame[condition(frame[mask_col])]
    return (rows["OUTCOME"].isin(outcome_values).mean(), len(rows)) if len(rows) else (float("nan"), 0)


def matrix(frame, columns_from=None):
    x = frame[NUMERIC].copy()
    for c in ["SEX", "RACE_ETHNICITY", "ARRIVED_BY_AMBULANCE", "TRIAGE_LEVEL"]:
        x = x.join(pandas.get_dummies(frame[c], prefix=c, dummy_na=True).astype(float))
    if columns_from is not None:
        x = x.reindex(columns=columns_from, fill_value=0.0)
    return x


def closest(a, b, scale):
    """For each row of a, the distance to its closest row of b (numbers scaled by their spread, blanks as -1)."""
    aa = (a.fillna(-1) / scale).to_numpy(float)
    bb = (b.fillna(-1) / scale).to_numpy(float)
    best = numpy.empty(len(aa))
    for start in range(0, len(aa), 500):
        chunk = aa[start:start + 500]
        d = numpy.sqrt(((chunk[:, None, :] - bb[None, :, :]) ** 2).sum(axis=2))
        best[start:start + 500] = d.min(axis=1)
    return best


def main(path):
    train, holdout, synth = load(HERE / "nhamcs_ed_train.csv"), load(HERE / "nhamcs_ed_holdout.csv"), load(path)
    OUT.mkdir(exist_ok=True)
    rows = []

    # Fidelity
    for c in NUMERIC + CATEGORICAL:
        rows.append({"CHECK": "Fidelity", "MEASURE": f"{c} distribution similarity", "REAL": 1.0,
                     "SYNTHETIC": round(similarity(train, synth, c), 3), "NOTE": "1 - total variation distance vs the real training rows"})
    links = [
        ("Sent to ICU, died or had surgery when systolic BP < 90", "SYSTOLIC_BP", lambda s: s < 90, ["ICU, death or surgery"]),
        ("Admitted (ward, ICU, death or surgery) when SpO2 < 92", "SPO2", lambda s: s < 92, TARGETS["Admitted, ICU, death or surgery"]),
        ("Admitted (ward, ICU, death or surgery) when triage level is 1 or 2", "TRIAGE_LEVEL", lambda s: s.isin(["1", "2"]), TARGETS["Admitted, ICU, death or surgery"]),
        ("Admitted (ward, ICU, death or surgery) when triage level is 4 or 5", "TRIAGE_LEVEL", lambda s: s.isin(["4", "5"]), TARGETS["Admitted, ICU, death or surgery"]),
        ("Admitted (ward, ICU, death or surgery) after an ambulance arrival", "ARRIVED_BY_AMBULANCE", lambda s: s == "Yes", TARGETS["Admitted, ICU, death or surgery"]),
    ]
    for name, col, cond, outs in links:
        r, rn = share(train, col, cond, outs)
        s, sn = share(synth, col, cond, outs)
        rows.append({"CHECK": "Clinical link", "MEASURE": name, "REAL": round(r, 3), "SYNTHETIC": round(s, 3),
                     "NOTE": f"share of rows; real n={rn}, synthetic n={sn}"})

    # Privacy
    key = NUMERIC + CATEGORICAL
    train_keys = set(map(tuple, train[key].astype(str).to_numpy()))
    copies = sum(tuple(r) in train_keys for r in synth[key].astype(str).to_numpy())
    holdout_copies = sum(tuple(r) in train_keys for r in holdout[key].astype(str).to_numpy())
    rows.append({"CHECK": "Privacy", "MEASURE": "Rows identical to a real training row", "REAL": holdout_copies,
                 "SYNTHETIC": copies, "NOTE": f"real column = unseen real holdout visits ({len(holdout)}) for comparison; synthetic n={len(synth)}"})
    xt, xs, xh = matrix(train), None, None
    xs, xh = matrix(synth, xt.columns), matrix(holdout, xt.columns)
    scale = xt.std().replace(0, 1).fillna(1)
    rng = numpy.random.default_rng(SEED)
    sample = lambda x: x.iloc[rng.choice(len(x), size=min(2000, len(x)), replace=False)]
    dcr_s, dcr_h = closest(sample(xs), xt, scale), closest(sample(xh), xt, scale)
    rows.append({"CHECK": "Privacy", "MEASURE": "Median distance to the closest real training row", "REAL": round(float(numpy.median(dcr_h)), 3),
                 "SYNTHETIC": round(float(numpy.median(dcr_s)), 3), "NOTE": "real column = unseen holdout visits; synthetic should not be much closer"})
    rows.append({"CHECK": "Privacy", "MEASURE": "Share closer to a training row than the closest 5% of real unseen visits",
                 "REAL": 0.05, "SYNTHETIC": round(float((dcr_s < numpy.quantile(dcr_h, 0.05)).mean()), 3),
                 "NOTE": "about 0.05 means no sign of memorised rows"})

    # Usefulness: train on synthetic, test on real
    xh_full = matrix(holdout, xt.columns)
    for target, values in TARGETS.items():
        y_h = holdout["OUTCOME"].isin(values).astype(int)
        scores = {}
        for name, frame in (("Trained on real rows", train), ("Trained on synthetic rows", synth)):
            model = HistGradientBoostingClassifier(random_state=SEED, max_iter=300, learning_rate=0.05)
            model.fit(matrix(frame, xt.columns), frame["OUTCOME"].isin(values).astype(int))
            scores[name] = roc_auc_score(y_h, model.predict_proba(xh_full)[:, 1])
        rows.append({"CHECK": "Train on synthetic, test on real", "MEASURE": f"Predicting {target}: AUROC on {len(holdout)} real unseen visits",
                     "REAL": round(scores["Trained on real rows"], 3), "SYNTHETIC": round(scores["Trained on synthetic rows"], 3),
                     "NOTE": "same gradient boosting model; real column trained on real rows"})
        tri = holdout["TRIAGE_LEVEL"].astype(float)
        known = tri.notna()
        rows.append({"CHECK": "Train on synthetic, test on real", "MEASURE": f"Reference: ED triage level alone, predicting {target}",
                     "REAL": round(roc_auc_score(y_h[known], -tri[known]), 3), "SYNTHETIC": None,
                     "NOTE": f"on the {int(known.sum())} holdout visits with a triage level"})

    table = pandas.DataFrame(rows)
    table.to_csv(OUT / "EIR_SYNTH_CHECKS.csv", index=False)
    summary = {"synthetic_file": str(path), "synthetic_rows": len(synth), "train_rows": len(train), "holdout_rows": len(holdout)}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=1))
    # Side-by-side distributions for a VA chart.
    dist = []
    for c in NUMERIC + CATEGORICAL:
        for label, frame in (("Real", train), ("Synthetic", synth)):
            for value, p in binned(frame[c], c).value_counts(normalize=True).items():
                dist.append({"COLUMN": c, "VALUE": value, "SOURCE": label, "SHARE": round(p, 4)})
    pandas.DataFrame(dist).to_csv(OUT / "EIR_SYNTH_DISTRIBUTIONS.csv", index=False)
    pandas.set_option("display.width", 220, "display.max_colwidth", 80)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
