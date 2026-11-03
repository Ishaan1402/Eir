"""Check a SAS Data Maker output against the rules the source data was generated with (see README.md).

    python3 validate_output.py OUTPUT.csv [SOURCE.csv]

Hard rules hold for 100% of rows in the source, so any violation in the output is a utility failure of the
synthesizer. With SOURCE.csv it also compares label mix and missingness, and counts output rows that copy a
source row exactly (a synthesizer should not reproduce its training rows). Stdlib only, like generate.py.
"""
import csv
import sys
from collections import Counter
from datetime import datetime

MENTAL = {"Alert", "Confused", "Responds to voice", "Responds to pain", "Unresponsive"}
CHANGE = {"Yes", "No", "Uncertain", "No prior information"}
ATTENTION = {"Prepare now", "Preparation can wait", "Routine awareness", "Cannot assess"}
INTERVENTIONS = {  # allowed interventions per chief complaint (generate.py COMPLAINTS)
    "Shortness of breath": {"Oxygen", "Albuterol", "None"},
    "Chest discomfort": {"Aspirin", "Nitroglycerin", "None"},
    "Stroke symptoms": {"None"},
    "Altered mental status": {"None", "Glucose"},
    "Low blood sugar": {"Glucose"},
    "Fall": {"None", "Pain medication"},
    "Weakness with fever": {"IV fluids", "None"},
    "Abdominal pain": {"None", "IV fluids", "Pain medication"},
    "Seizure": {"None", "Midazolam"},
    "Allergic reaction": {"Epinephrine", "Diphenhydramine"},
    "Motor vehicle collision": {"None", "IV fluids"},
}
HYPO_COMPLAINTS = {"Low blood sugar", "Altered mental status", "Seizure"}
RANGES = {  # generator clamps; blank is always allowed (not stated)
    "age": (18, 99), "eta_minutes": (3, 45), "elapsed_minutes": (0, 15),
    "heart_rate": (40, 175), "systolic_bp": (60, 220), "diastolic_bp": (35, 125), "resp_rate": (8, 40),
    "spo2_pct": (75, 100), "glucose_mg_dl": (20, 450), "temp_c": (35.0, 41.0),
    "prior_heart_rate": (40, 175), "prior_systolic_bp": (60, 220), "prior_spo2_pct": (75, 100),
}
PRIOR = ["prior_heart_rate", "prior_systolic_bp", "prior_spo2_pct", "prior_mental_status"]
ID_COLUMNS = {"case_id", "reviewer_id"}  # may be dropped in Data Maker; ignored when comparing rows


def num(value):
    """Blank -> None. Accepts '72', '72.0', ' 72 '. Raises ValueError on anything else."""
    value = (value or "").strip()
    return None if value == "" else float(value)


def when(value):
    value = (value or "").strip()
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00").replace(" ", "T"))


def text(value):
    value = (value or "").strip()
    return value or None


def load(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def red_flag(r):
    """Observable red flags (README 'Prepare now'). Epinephrine is excluded: its rule also depends on hidden severity."""
    sbp, spo2, rr, hr, glucose = r["systolic_bp"], r["spo2_pct"], r["resp_rate"], r["heart_rate"], r["glucose_mg_dl"]
    return ((sbp is not None and sbp < 90) or (spo2 is not None and spo2 < 90)
            or (rr is not None and (rr < 10 or rr > 28)) or (hr is not None and (hr > 130 or hr < 45))
            or r["mental_status"] in ("Responds to pain", "Unresponsive")
            or (glucose is not None and glucose < 60) or r["chief_complaint"] == "Stroke symptoms")


def key_missing(r):
    return (r["systolic_bp"] is None and r["spo2_pct"] is None) or (r["heart_rate"] is None and r["systolic_bp"] is None)


def parse(raw):
    """Typed copy of a row, or the reason it can't be read."""
    r = {}
    for column in RANGES:
        if column in raw:
            r[column] = num(raw[column])
    for column in ("update_number",):
        r[column] = num(raw.get(column))
    for column in ("sex", "chief_complaint", "mental_status", "intervention", "prior_mental_status",
                   "meaningful_change", "attention_category", "app_case_status"):
        r[column] = text(raw.get(column))
    r["report_time_utc"] = when(raw.get("report_time_utc"))
    r["reviewed_at_utc"] = when(raw.get("reviewed_at_utc"))
    return r


RULES = [
    # (name, applies to row?, holds for row?)
    ("update_number is 1 or 2", lambda r: True, lambda r: r["update_number"] in (1, 2)),
    ("values inside generator ranges", lambda r: True, lambda r: all(
        r.get(c) is None or lo <= r[c] <= hi for c, (lo, hi) in RANGES.items())),
    ("systolic BP above diastolic", lambda r: r["systolic_bp"] is not None and r["diastolic_bp"] is not None,
     lambda r: r["systolic_bp"] > r["diastolic_bp"]),
    ("BP stated as a pair", lambda r: True, lambda r: (r["systolic_bp"] is None) == (r["diastolic_bp"] is None)),
    ("category values are known levels", lambda r: True, lambda r: (
        r["chief_complaint"] in INTERVENTIONS and r["mental_status"] in MENTAL
        and r["meaningful_change"] in CHANGE and r["attention_category"] in ATTENTION
        and r["app_case_status"] in ("Needs Review", "Queued") and r["sex"] in (None, "Female", "Male")
        and r["prior_mental_status"] in (None, *MENTAL))),
    ("first report: prior_* blank", lambda r: r["update_number"] == 1, lambda r: all(r[c] is None for c in PRIOR)),
    ("first report: elapsed 0", lambda r: r["update_number"] == 1, lambda r: r["elapsed_minutes"] == 0),
    ("first report: 'No prior information'", lambda r: r["update_number"] == 1,
     lambda r: r["meaningful_change"] == "No prior information"),
    ("update: prior HR and mental status stated", lambda r: r["update_number"] == 2,
     lambda r: r["prior_heart_rate"] is not None and r["prior_mental_status"] is not None),
    ("update: elapsed 3-15 min", lambda r: r["update_number"] == 2,
     lambda r: r["elapsed_minutes"] is not None and 3 <= r["elapsed_minutes"] <= 15),
    ("update: change is Yes/No/Uncertain", lambda r: r["update_number"] == 2,
     lambda r: r["meaningful_change"] in ("Yes", "No", "Uncertain")),
    ("red flag -> Prepare now", red_flag, lambda r: r["attention_category"] == "Prepare now"),
    ("no red flag + key vitals missing -> Cannot assess", lambda r: not red_flag(r) and key_missing(r),
     lambda r: r["attention_category"] == "Cannot assess"),
    ("Cannot assess only when key vitals missing", lambda r: r["attention_category"] == "Cannot assess",
     lambda r: key_missing(r) and not red_flag(r)),
    ("Cannot assess <-> Needs Review", lambda r: True,
     lambda r: (r["attention_category"] == "Cannot assess") == (r["app_case_status"] == "Needs Review")),
    ("intervention allowed for complaint", lambda r: r["chief_complaint"] in INTERVENTIONS,
     lambda r: r["intervention"] in INTERVENTIONS[r["chief_complaint"]]),
    ("Epinephrine only for allergic reaction", lambda r: r["intervention"] == "Epinephrine",
     lambda r: r["chief_complaint"] == "Allergic reaction"),
    ("glucose < 70 only for AMS / low sugar / seizure", lambda r: r["glucose_mg_dl"] is not None
     and r["glucose_mg_dl"] < 70, lambda r: r["chief_complaint"] in HYPO_COMPLAINTS),
    ("report time before review time", lambda r: r["report_time_utc"] and r["reviewed_at_utc"],
     lambda r: r["report_time_utc"] < r["reviewed_at_utc"]),
]


def check(rows):
    parsed, unreadable = [], []
    for index, raw in enumerate(rows, start=2):  # line 1 is the header
        try:
            parsed.append((index, parse(raw)))
        except (ValueError, TypeError) as error:
            unreadable.append((index, str(error)))
    print(f"rows: {len(rows)}   unreadable: {len(unreadable)}" + (f"   e.g. line {unreadable[0][0]}: {unreadable[0][1]}" if unreadable else ""))
    failures = 0
    for name, applies, holds in RULES:
        scope = [(i, r) for i, r in parsed if applies(r)]
        bad = [i for i, r in scope if not holds(r)]
        failures += bool(bad)
        share = f"{len(bad)}/{len(scope)}" if scope else "0/0"
        example = f"   e.g. lines {', '.join(map(str, bad[:5]))}" if bad else ""
        print(f"  {'FAIL' if bad else 'ok  '}  {name:<52} {share}{example}")
    return failures


def profile(rows):
    total = len(rows) or 1
    mix = Counter(r.get("attention_category", "").strip() for r in rows)
    blanks = {c: sum(1 for r in rows if not (r.get(c) or "").strip()) / total for c in rows[0]} if rows else {}
    updates = sum(1 for r in rows if (r.get("update_number") or "").strip() in ("2", "2.0")) / total
    return {k: v / total for k, v in mix.items()}, blanks, updates


def compare(output, source):
    out_mix, out_blank, out_upd = profile(output)
    src_mix, src_blank, src_upd = profile(source)
    print("\nlabel mix (output vs source):")
    for label in sorted(ATTENTION):
        print(f"  {label:<22} {out_mix.get(label, 0):6.1%}  vs {src_mix.get(label, 0):6.1%}")
    print(f"updates (update_number=2): {out_upd:.1%} vs {src_upd:.1%}")
    print("blank share by column, where output and source differ by more than 5 points:")
    shown = False
    for column, share in src_blank.items():
        if column in out_blank and abs(out_blank[column] - share) > 0.05:
            print(f"  {column:<22} {out_blank[column]:6.1%}  vs {share:6.1%}")
            shown = True
    if not shown:
        print("  none")
    missing = [c for c in source[0] if c not in output[0] and c not in ID_COLUMNS]
    if missing:
        print(f"columns in source but not in output: {', '.join(missing)}")
    shared = [c for c in source[0] if c in output[0] and c not in ID_COLUMNS]
    def key(row):
        return tuple((row.get(c) or "").strip() for c in shared)

    seen = {key(s) for s in source}
    print(f"output rows identical to a source row (ignoring IDs): {sum(1 for r in output if key(r) in seen)}")


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    output = load(argv[1])
    print(f"== {argv[1]}")
    failures = check(output)
    if len(argv) == 3:
        compare(output, load(argv[2]))
    print(f"\n{'PASS' if not failures else f'{failures} rule(s) failed'}: hard rules")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
