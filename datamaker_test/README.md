# SAS Data Maker test dataset: fictitious EMS reports + clinician annotations

**File:** `ems_synthetic_annotations.csv`. It has 1,000 rows × 26 columns (~167 KB) and is a UTF-8 CSV with a header row.
**It contains no real data.** Every row comes from `generate.py` (seed 20261007, Python stdlib only), so there is no PHI or PII.
`python3 generate.py` reproduces the file exactly.

## What a row is

Each row is one EMS report radioed to the ED. It is flattened the same way as our annotation workbook
(Cases + Observations + Clinical review):

- what the crew reported now
- the earlier report, if this is an update
- the reviewer's labels: meaningful change, attention category and app handling.

Free-text transcripts are left out on purpose, because Data Maker generates tabular data. This file is the structured layer that
we would extract from transcripts.

**A blank cell means the value was not stated in the report.** Values are never imputed, which follows the workbook's "missing stays missing" rule.

## Columns

| Column | Type | Notes |
|---|---|---|
| case_id | ID | `SYN0001`…; unique key, exclude from modeling |
| report_time_utc | datetime | ISO UTC, 2025 |
| update_number | integer | 1 = first report, 2 = update with an earlier report (~38%) |
| elapsed_minutes | integer | minutes since the earlier report; 0 on first reports |
| eta_minutes | integer | ETA to the ED, 3–45 |
| age, sex | integer / categorical | ~10% not stated |
| chief_complaint | categorical | 11 levels |
| heart_rate, systolic_bp, diastolic_bp, resp_rate, spo2_pct | integer | current vitals; each sometimes not stated; ~6% "sparse" reports have no BP or SpO2 |
| mental_status | categorical | Alert / Confused / Responds to voice / Responds to pain / Unresponsive |
| glucose_mg_dl | integer | mostly stated for AMS, low blood sugar, stroke and seizure; hypoglycemia only occurs in those |
| temp_c | numeric | mostly stated for "Weakness with fever" |
| intervention | categorical | complaint-specific (e.g. Aspirin for chest discomfort, Epinephrine only for allergic reaction) |
| prior_heart_rate, prior_systolic_bp, prior_spo2_pct, prior_mental_status | mixed | earlier report; blank on first reports |
| meaningful_change | categorical | Yes / No / Uncertain / No prior information (workbook values) |
| attention_category | categorical | **label**: Prepare now / Preparation can wait / Routine awareness / Cannot assess (workbook values) |
| app_case_status | categorical | Needs Review when attention_category = Cannot assess, otherwise Queued |
| reviewer_id | categorical | REV01–REV04 |
| reviewed_at_utc | datetime | 3–40 days after the report |

## How labels are assigned (test-data rules, not an approved rubric)

- **Prepare now:** any of these red flags is stated: SBP < 90, SpO2 < 90, RR < 10 or > 28, HR > 130 or < 45, responds to pain or
  unresponsive, glucose < 60, stroke symptoms, or epinephrine given for a significant allergic reaction.
- **Cannot assess:** no red flag stated, and key vitals are missing (no BP and no SpO2, or no HR and no BP). App handling is then Needs Review.
  An Uncertain change **does not** by itself make a case Cannot assess.
- **Preparation can wait:** concerning but not red-flag findings, such as HR > 110, SpO2 < 94, RR > 22, confusion, fever ≥ 38.5,
  chest discomfort at age ≥ 40, or a meaningful change in a sicker patient.
- **Routine awareness:** none of the above.
- About 10% of "can wait" and "routine" labels are flipped between the two, to mimic reviewers disagreeing.
- **meaningful_change = Yes** when HR moves ≥ 15, SBP moves ≥ 20, SpO2 moves ≥ 3, or mental status changes between reports.
  It is **Uncertain** when too few vitals can be compared, or (~7%) for a questionable reading.

These thresholds are loosely based on common prehospital red flags. **They are a simplification for test data. They are not our rubric (still a
draft, not approved), not a clinical protocol, and not calibrated to any real registry.** The labels do not represent clinician judgment.

## What to check in the Data Maker output

- Do the synthetic rows keep the red-flag → Prepare now link? A synthetic row with SBP 70 and "Routine awareness" is a utility failure.
- Does Cannot assess still always go with Needs Review, and only appear when key vitals are blank?
- Do first reports keep blank prior_* columns and "No prior information"? This is structural missingness, and a common failure point for synthesizers.
- Are complaint-specific patterns kept: glucose with AMS and low blood sugar, temperature with fever, epinephrine only with allergic reaction?
- Is report_time_utc earlier than reviewed_at_utc?
