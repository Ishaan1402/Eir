"""Push the Data Maker check results to CAS (Public) for a Visual Analytics page.

    python push.py <data maker output>.csv   # run from the repo root with the PR #83 code on PYTHONPATH

Tables: EIR_SYNTH_CHECKS (one row per check), EIR_SYNTH_DISTRIBUTIONS (real vs synthetic shares per column)
and EIR_SYNTH_ROWS (the synthetic visits themselves, labelled synthetic).
"""
import asyncio
import csv
import dataclasses
import sys
from pathlib import Path

from backend import sas_sync

HERE = Path(__file__).parent
PREFIX = "EIR_SYNTH_"
COLUMNS = {
    "CHECKS": [("CHECK", "char", "Check"), ("MEASURE", "char", "Measure"), ("REAL", "num", "Real data"),
               ("SYNTHETIC", "num", "Synthetic data"), ("NOTE", "char", "How to read it")],
    "DISTRIBUTIONS": [("COLUMN", "char", "Column"), ("VALUE", "char", "Value or range"), ("SOURCE", "char", "Real or synthetic"),
                      ("SHARE", "num", "Share of rows")],
    "ROWS": [(c, "num" if c in ("AGE", "HEART_RATE", "RESP_RATE", "SYSTOLIC_BP", "DIASTOLIC_BP", "SPO2", "TEMP_F", "PAIN_0_10") else "char", c)
             for c in ("AGE", "SEX", "RACE_ETHNICITY", "ARRIVED_BY_AMBULANCE", "HEART_RATE", "RESP_RATE", "SYSTOLIC_BP",
                       "DIASTOLIC_BP", "SPO2", "TEMP_F", "PAIN_0_10", "TRIAGE_LEVEL", "OUTCOME")]
              + [("DATA_SOURCE", "char", "Where the row comes from")],
}


def read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{k.strip().upper(): (v if v != "" else None) for k, v in row.items()} for row in csv.DictReader(f)]


def main(synthetic):
    rows = read(synthetic)
    for r in rows:
        r["DATA_SOURCE"] = "Synthetic (SAS Data Maker, trained on CDC NHAMCS 2022)"
    tables = {"CHECKS": read(HERE / "results/EIR_SYNTH_CHECKS.csv"),
              "DISTRIBUTIONS": read(HERE / "results/EIR_SYNTH_DISTRIBUTIONS.csv"), "ROWS": rows}
    settings = dataclasses.replace(sas_sync.Settings.from_env(), prefix=PREFIX)

    async def run():
        client = sas_sync.CasClient(settings)
        try:
            await client.replace_tables({n: sas_sync.to_csv(n, d, COLUMNS) for n, d in tables.items()}, COLUMNS)
        finally:
            await client.close()
    asyncio.run(run())
    for n, d in tables.items():
        print(f"{settings.caslib}.{PREFIX}{n}: {len(d)} rows")


if __name__ == "__main__":
    main(Path(sys.argv[1]).expanduser())
