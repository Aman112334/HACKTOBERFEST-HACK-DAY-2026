"""Generate SYNTHETIC RASFF-style and FDA-style exports for tests and demos of the ingestion code.
Nothing here is real. Every id starts with SYN- and every file name contains SYNTHETIC."""
import csv, os, random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = os.path.join(ROOT, "data", "fixtures")
os.makedirs(FX, exist_ok=True)
rnd = random.Random(7)

subjects = (
    [("Tricyclazole in basmati rice from India", "pesticide residues")] * 14
    + [("Thiamethoxam in basmati rice from India", "pesticide residues")] * 10
    + [("Carbendazim in rice from India", "pesticide residues")] * 4
    + [("Chlorpyrifos in basmati rice from India", "pesticide residues")] * 4
    + [("Aflatoxins in rice from India", "mycotoxins")] * 2
    + [("Live insects in basmati rice from India", "pest infestation")] * 3
    + [("Tricyclazole in rice from Pakistan", "pesticide residues")] * 3
    + [("Salmonella in sesame seeds from India", "pathogenic micro-organisms")] * 3
    + [("Aflatoxins in groundnuts from India", "mycotoxins")] * 2
)
rows = []
for i, (subj, hz) in enumerate(subjects, 1):
    origin = "Pakistan" if "Pakistan" in subj else "India"
    y = rnd.choice([2023, 2024, 2025, 2026]); m = rnd.randint(1, 12 if y < 2026 else 8); d = rnd.randint(1, 28)
    sub0 = subj.split(" in ")[0]
    val = {"Tricyclazole": rnd.choice([0.03, 0.12, 0.19, 0.4]), "Thiamethoxam": rnd.choice([0.02, 0.05, 0.11]),
           "Carbendazim": rnd.choice([0.05, 0.3]), "Chlorpyrifos": rnd.choice([0.02, 0.08]),
           "Aflatoxins": rnd.choice([3.5, 6.0])}.get(sub0)
    res_txt = "" if val is None else (f"{val} ug/kg" if sub0 == "Aflatoxins" else f"{val} mg/kg")
    rows.append({"Reference": f"SYN-RASFF-{i:04d}", "Analytical result": res_txt, "Date of case": f"{y}-{m:02d}-{d:02d}",
                 "Notification type": "border rejection", "Subject": subj,
                 "Product category": "cereals and bakery products" if "rice" in subj else "nuts, nut products and seeds",
                 "Country of origin": origin, "Hazards": subj.split(" in ")[0], "Hazard category": hz,
                 "Action taken": "re-dispatch"})
rnd.shuffle(rows)
with open(os.path.join(FX, "rasff_export_SYNTHETIC.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

fda = []
spec = ([("RICE,BASMATI,MILLED", "PESTICIDE", "India")] * 5 + [("RICE,PARBOILED", "FILTHY", "India")] * 3
        + [("SPICE,TURMERIC", "SALMONELLA", "India")] * 6 + [("RICE,BASMATI,MILLED", "NO ENGLISH", "India")] * 2
        + [("RICE,JASMINE", "PESTICIDE", "Thailand")] * 2)
for i, (desc, ch, ctry) in enumerate(spec, 1):
    y = rnd.choice([2023, 2024, 2025]); m = rnd.randint(1, 12); d = rnd.randint(1, 28)
    fda.append({"FEI Number": f"SYN{i:07d}", "Firm Name": f"SYNTHETIC FIRM {i}", "Country Name": ctry,
                "Product Code": "02ABC99", "Product Code Description": desc,
                "Refusal Date": f"{m:02d}/{d:02d}/{y}", "Refusal Charges": ch})
with open(os.path.join(FX, "fda_refusals_SYNTHETIC.csv"), "w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(fda[0])); w.writeheader(); w.writerows(fda)
print("fixtures:", len(rows), "rasff rows,", len(fda), "fda rows")
