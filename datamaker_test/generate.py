"""Generate a fictitious table of EMS prehospital reports + clinician annotations for testing SAS Data Maker.

Each row is one incoming EMS report to the ED, flattened the way the annotation workbook
(Cases + Observations + Clinical review) would be: what the report stated, the prior report if any,
and the clinician-style labels. No real patients, no PHI. Deterministic (seeded). Stdlib only.

Blank cell = not stated in the report (never imputed), matching the workbook's "missing stays missing" rule.
"""
import csv
import random
from datetime import datetime, timedelta

SEED = 20261007
N_ROWS = 1000
OUT = "ems_synthetic_annotations.csv"
REVIEWERS = ["REV01", "REV02", "REV03", "REV04"]
MENTAL = ["Alert", "Confused", "Responds to voice", "Responds to pain", "Unresponsive"]

rng = random.Random(SEED)

# complaint: weight, age mean/sd, hr/sbp/spo2 shift, chance of altered mental status, glucose stated, temp stated, interventions
COMPLAINTS = {
    "Shortness of breath":   (16, 66, 15, 14,   5, -4, 0.10, 0.10, 0.15, ["Oxygen", "Albuterol", "None"]),
    "Chest discomfort":      (16, 62, 13,  8,  10, -1, 0.03, 0.15, 0.02, ["Aspirin", "Aspirin", "Nitroglycerin", "None"]),
    "Stroke symptoms":       ( 9, 71, 12,  2,  30,  0, 0.30, 0.85, 0.05, ["None"]),
    "Altered mental status": ( 9, 64, 18,  6,  -5, -1, 0.85, 0.90, 0.30, ["None", "Glucose"]),
    "Low blood sugar":       ( 6, 58, 18,  6,   0,  0, 0.80, 1.00, 0.05, ["Glucose"]),
    "Fall":                  (13, 76, 12,  2,   0,  0, 0.10, 0.25, 0.05, ["None", "Pain medication"]),
    "Weakness with fever":   ( 9, 72, 14, 18, -15, -2, 0.35, 0.40, 0.90, ["IV fluids", "None"]),
    "Abdominal pain":        ( 9, 50, 18, 10,  -3,  0, 0.05, 0.20, 0.20, ["None", "IV fluids", "Pain medication"]),
    "Seizure":               ( 6, 40, 18, 14,   5, -2, 0.70, 0.80, 0.15, ["None", "Midazolam"]),
    "Allergic reaction":     ( 5, 35, 15, 18, -12, -2, 0.05, 0.10, 0.02, ["Epinephrine", "Epinephrine", "Diphenhydramine"]),
    "Motor vehicle collision": (6, 38, 15, 12,  -3,  0, 0.15, 0.05, 0.02, ["None", "IV fluids"]),
}


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def maybe(p, value):
    """Return value if stated in the report (probability p), else None."""
    return value if rng.random() < p else None


def vitals(name, sev, age, z):
    """z: per-patient standard-normal noise, shared by prior and current report so they stay correlated."""
    _, _, _, hr_s, sbp_s, spo2_s, ams_p, *_ = COMPLAINTS[name]
    shock = name in ("Allergic reaction", "Weakness with fever", "Motor vehicle collision", "Abdominal pain")
    hr = int(clamp(80 + hr_s * (0.5 + sev) + 40 * sev ** 2 + 10 * z[0] + rng.gauss(0, 3), 40, 175))
    sbp = int(clamp(130 + sbp_s + 0.3 * (age - 50) - (70 * sev ** 2 if shock else 0) + 15 * z[1] + rng.gauss(0, 4), 60, 220))
    dbp = int(clamp(sbp * rng.uniform(0.55, 0.68), 35, 125))
    rr = int(clamp(16 + 14 * sev ** 2 + (5 if name == "Shortness of breath" else 0) + 2.5 * z[2] + rng.gauss(0, 1), 8, 40))
    spo2 = int(clamp(97.5 + spo2_s * (0.4 + sev) - 10 * sev ** 2 + 1.3 * z[3] + rng.gauss(0, 0.5), 75, 100))
    if z[4] < ams_p * (0.4 + sev):
        ms = MENTAL[int(clamp(1 + sev * 4 + 0.7 * z[5], 1, 4))]
    else:
        ms = "Alert"
    return hr, sbp, dbp, rr, spo2, ms


def gen_row(i):
    name = rng.choices(list(COMPLAINTS), weights=[c[0] for c in COMPLAINTS.values()])[0]
    _, age_mu, age_sd, *_, glu_p, temp_p, interventions = COMPLAINTS[name]

    age = maybe(0.9, int(clamp(rng.gauss(age_mu, age_sd), 18, 99)))
    sex = maybe(0.9, rng.choice(["Female", "Male"]))
    sev = clamp(rng.betavariate(1.4, 5.0) + max(0, (age or 60) - 65) / 300 + (0.35 if rng.random() < 0.07 else 0), 0, 1)
    z = [rng.gauss(0, 1) for _ in range(4)] + [rng.random(), rng.gauss(0, 1)]

    # ~35% of reports are an update with an earlier report from the same crew
    is_update = rng.random() < 0.35
    elapsed = rng.randint(3, 15) if is_update else 0
    eta = int(clamp(rng.lognormvariate(2.6, 0.45), 3, 45))
    report_time = datetime(2025, 1, 1) + timedelta(minutes=rng.randint(0, 364 * 24 * 60))

    prior = None
    if is_update:
        drift = rng.choices([-0.3, 0.0, 0.35], weights=[30, 45, 25])[0]  # improved / stable / worsened
        prior = vitals(name, clamp(sev - drift, 0, 1), age or 60, z)
    hr, sbp, dbp, rr, spo2, ms = vitals(name, sev, age or 60, z)

    glucose = None
    if rng.random() < glu_p:
        hypo = name == "Low blood sugar" or (name in ("Altered mental status", "Seizure") and rng.random() < 0.2)
        if hypo and is_update and rng.random() < 0.6:  # treated before this update
            glucose, ms = int(clamp(rng.gauss(105, 20), 70, 180)), rng.choice(["Alert", "Alert", "Confused"])
        elif hypo:
            glucose = int(clamp(rng.gauss(45, 10), 20, 69))
        else:
            glucose = int(clamp(rng.lognormvariate(4.8, 0.25), 75, 450))
    temp = round(clamp(rng.gauss(38.9 if name == "Weakness with fever" else 37.0, 0.5), 35.0, 41.0), 1) if rng.random() < temp_p else None
    intervention = rng.choice(interventions)
    if name == "Low blood sugar" and is_update and glucose and glucose >= 70:
        intervention = "Glucose"

    # reports don't always state everything; blank = not stated
    hr = maybe(0.95, hr)
    if rng.random() < 0.06:  # sparse report: complaint and little else
        sbp = dbp = spo2 = None
    if rng.random() < 0.07:
        sbp = dbp = None
    rr = maybe(0.85, rr)
    spo2 = maybe(0.93, spo2)

    # meaningful change vs prior report (Yes / No / Uncertain / No prior information)
    p_hr = p_sbp = p_spo2 = p_ms = None
    if prior:
        p_hr, p_sbp, _, _, p_spo2, p_ms = prior
        p_sbp = maybe(0.9, p_sbp)
        p_spo2 = maybe(0.9, p_spo2)
        diffs = [
            hr is not None and abs(hr - p_hr) >= 15,
            sbp is not None and p_sbp is not None and abs(sbp - p_sbp) >= 20,
            spo2 is not None and p_spo2 is not None and abs(spo2 - p_spo2) >= 3,
            ms != p_ms,
        ]
        comparable = sum(x is not None for x in (hr, sbp, spo2)) >= 2
        if rng.random() < 0.07:  # e.g. conflicting or questionable reading in the report
            change = "Uncertain"
        elif any(diffs):
            change = "Yes"
        elif comparable:
            change = "No"
        else:
            change = "Uncertain"
    else:
        change = "No prior information"

    # attention category: red flags present in the report -> Prepare now; missing key info with no red flag -> Cannot assess.
    # Change being Uncertain never by itself makes a case Cannot assess.
    red = ((sbp is not None and sbp < 90) or (spo2 is not None and spo2 < 90) or (rr is not None and (rr < 10 or rr > 28))
           or (hr is not None and (hr > 130 or hr < 45)) or ms in ("Responds to pain", "Unresponsive")
           or (glucose is not None and glucose < 60) or name == "Stroke symptoms"
           or (name == "Allergic reaction" and intervention == "Epinephrine" and sev > 0.3))
    concern = ((hr is not None and hr > 110) or (spo2 is not None and spo2 < 94) or (rr is not None and rr > 22)
               or ms in ("Confused", "Responds to voice") or (temp is not None and temp >= 38.5)
               or (name == "Chest discomfort" and (age or 60) >= 40) or change == "Yes" and sev > 0.35)
    key_missing = (sbp is None and spo2 is None) or (hr is None and sbp is None)
    if red:
        attention = "Prepare now"
    elif key_missing:
        attention = "Cannot assess"
    elif concern:
        attention = "Preparation can wait"
    else:
        attention = "Routine awareness"
    if attention in ("Preparation can wait", "Routine awareness") and rng.random() < 0.10:
        attention = "Routine awareness" if attention == "Preparation can wait" else "Preparation can wait"  # reviewer disagreement

    reviewed = report_time + timedelta(days=rng.randint(3, 40), minutes=rng.randint(0, 600))

    return {
        "case_id": f"SYN{i:04d}",
        "report_time_utc": report_time.strftime("%Y-%m-%dT%H:%M:00Z"),
        "update_number": 2 if is_update else 1,
        "elapsed_minutes": elapsed,
        "eta_minutes": eta,
        "age": age,
        "sex": sex,
        "chief_complaint": name,
        "heart_rate": hr,
        "systolic_bp": sbp,
        "diastolic_bp": dbp,
        "resp_rate": rr,
        "spo2_pct": spo2,
        "mental_status": ms,
        "glucose_mg_dl": glucose,
        "temp_c": temp,
        "intervention": intervention,
        "prior_heart_rate": p_hr,
        "prior_systolic_bp": p_sbp,
        "prior_spo2_pct": p_spo2,
        "prior_mental_status": p_ms,
        "meaningful_change": change,
        "attention_category": attention,
        "app_case_status": "Needs Review" if attention == "Cannot assess" else "Queued",
        "reviewer_id": rng.choice(REVIEWERS),
        "reviewed_at_utc": reviewed.strftime("%Y-%m-%dT%H:%M:00Z"),
    }


rows = [gen_row(i) for i in range(1, N_ROWS + 1)]
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]))
    w.writeheader()
    for r in rows:
        w.writerow({k: ("" if v is None else v) for k, v in r.items()})
print(f"wrote {OUT}: {len(rows)} rows x {len(rows[0])} cols")
