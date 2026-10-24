"""Generate differential-test vectors: random lots + the cyrb53 of the Python engine's canonical output.
The JS test (web/tests/parity.test.mjs) must reproduce every value exactly."""
import json, os, random, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from tests._util import bundle, sample, AS_OF  # noqa: E402
from tests.test_engine import Properties  # noqa: E402
from niryatsafe.engine import evaluate, canon, cyrb53  # noqa: E402

b = bundle()
rnd = random.Random(2026)
helper = Properties()
inputs = [sample(s["id"]) for s in b["samples"]]
inputs += [helper.rand_lot(rnd) for _ in range(400)]
import copy
def mutate(rnd):
    inp = copy.deepcopy(sample("clean"))
    for _ in range(rnd.randint(1, 3)):
        m = rnd.choice(["val", "unit", "form", "doc", "date", "spray", "acc", "loq", "drop", "pack", "origin"])
        if m == "val":
            inp["results"][rnd.randrange(len(inp["results"]))] = {"analyte": rnd.choice(["tricyclazole", "carbendazim", "cadmium", "arsenic_total", "aflatoxin_b1"]),
                "status": "value", "value": rnd.choice([0.0005, 0.0079, 0.0081, 0.0101, 0.2, 1.9, 2.1]), "unit": rnd.choice(["mg/kg", "ug/kg"]), "loq": None}
        elif m == "unit":
            inp["results"].append({"analyte": "aflatoxin_b1", "status": "value", "value": rnd.choice([1.0, 1.7, 2.0, 2.5]), "unit": rnd.choice(["ug/kg", "ppb", "ppm", "mg/kg"])})
        elif m == "form":
            inp["lot"]["form"] = rnd.choice(["raw_white", "sella", "brown"])
        elif m == "doc":
            inp["docs"][rnd.choice(list(inp["docs"]))] = rnd.choice([True, False, None])
        elif m == "date":
            inp["lab"]["report_date"] = rnd.choice(["2026-07-01", "2026-09-10", "2026-09-11", "2026-12-30", None])
        elif m == "spray":
            inp["sprays"].append(rnd.choice(["tricyclazole", "Diazinon", "Mystery 9", "tebuconazole"]))
        elif m == "acc":
            inp["lab"]["accredited"] = rnd.choice([False, None])
        elif m == "loq":
            inp["results"][0] = {"analyte": inp["results"][0]["analyte"], "status": "nd", "unit": "mg/kg", "loq": rnd.choice([None, 0.005, 0.02])}
        elif m == "drop":
            inp["results"] = inp["results"][:-rnd.randint(1, 5)]
            inp["lab"]["screen"] = rnd.choice([True, False])
        elif m == "pack":
            inp["lot"]["dest"] = rnd.choice(["DE", "NL", "US", "", "EU", "IN"])
        else:
            inp["lot"]["origin"] = "punjab"
    return inp
inputs += [mutate(rnd) for _ in range(150)]
vectors = []
for inp in inputs:
    r = evaluate(json.loads(json.dumps(inp)), b)
    vectors.append({"input": inp, "verdict": r["verdict"], "counts": r["counts"], "memo_id": r["memo_id"],
                    "digest": cyrb53(canon(r))})
os.makedirs(os.path.join(ROOT, "tests", "vectors"), exist_ok=True)
with open(os.path.join(ROOT, "tests", "vectors", "parity.json"), "w", encoding="utf-8") as fh:
    json.dump(vectors, fh, ensure_ascii=False)
from collections import Counter
print(len(vectors), "vectors;", dict(Counter(v["verdict"] for v in vectors)))
