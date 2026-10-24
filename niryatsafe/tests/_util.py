import os, sys, copy
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from niryatsafe.engine import load_bundle, evaluate  # noqa: E402
from niryatsafe.rulebook import resolve_sample, write_bundle  # noqa: E402

AS_OF = "2026-10-21"
BUNDLE_PATH = os.path.join(ROOT, "rules", "compiled", "bundle.json")


def bundle():
    if not os.path.exists(BUNDLE_PATH):
        write_bundle()
    return load_bundle(BUNDLE_PATH)


def sample(sid, **over):
    b = bundle()
    s = [x for x in b["samples"] if x["id"] == sid][0]
    inp = resolve_sample(s, AS_OF)
    for k, v in over.items():
        inp[k] = v
    return inp


def run(inp):
    return evaluate(copy.deepcopy(inp), bundle())


def keys(res, sev=None):
    return [f["key"] for f in res["findings"] if sev is None or f["severity"] == sev]


def ids(res, sev=None):
    return [f["id"] for f in res["findings"] if sev is None or f["severity"] == sev]
