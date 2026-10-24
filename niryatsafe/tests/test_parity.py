"""Runs the JS side of the differential test (needs Node 18+). Skipped if node is not installed."""
import os, shutil, subprocess, unittest
from tests._util import ROOT


@unittest.skipUnless(shutil.which("node"), "node not installed")
class Parity(unittest.TestCase):
    def test_js_engine_matches_python(self):
        subprocess.run(["python3", os.path.join(ROOT, "scripts", "gen_vectors.py")], check=True, cwd=ROOT, capture_output=True)
        p = subprocess.run(["node", "--test", os.path.join(ROOT, "web", "tests", "parity.test.mjs")], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stdout[-2500:] + p.stderr[-1500:])


if __name__ == "__main__":
    unittest.main()
