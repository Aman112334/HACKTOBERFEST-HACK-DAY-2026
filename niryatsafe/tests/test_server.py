import json, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from tests._util import bundle, sample, ROOT
from niryatsafe.service import Service
from niryatsafe.serve import make_handler


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os, tempfile
        cls.dist = tempfile.mkdtemp()
        open(os.path.join(cls.dist, "index.html"), "w").write("<!doctype html><title>x</title>")
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Service(), cls.dist))
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def call(self, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_health_and_rulebook(self):
        s, h = self.call("/api/health")
        self.assertEqual(s, 200)
        self.assertTrue(h["ok"])
        s, rb = self.call("/api/rulebook")
        self.assertEqual(rb["meta"]["hash"], bundle()["meta"]["hash"])

    def test_evaluate_matches_engine_and_renders_hindi(self):
        s, r = self.call("/api/evaluate?lang=hi", sample("hold"))
        self.assertEqual(s, 200)
        self.assertEqual(r["verdict"], "HOLD")
        self.assertEqual(r["verdict_label"], "रोकें")
        self.assertTrue(any("EU सीमा" in f["text"] for f in r["findings"]))

    def test_evaluate_defaults_as_of_to_server_date(self):
        inp = sample("clean"); inp.pop("as_of")
        s, r = self.call("/api/evaluate", inp)
        self.assertEqual(s, 200)
        self.assertRegex(r["as_of"], r"^\d{4}-\d{2}-\d{2}$")

    def test_parse_endpoint_and_bad_input(self):
        s, r = self.call("/api/parse-lab-table", {"text": "Tricyclazole\t<0.01\tmg/kg\t0.01"})
        self.assertEqual(r["rows"][0]["analyte"], "tricyclazole")
        s, _ = self.call("/nope")
        self.assertEqual(s, 404)

    def test_static_index_and_path_traversal(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/") as r:
            self.assertIn(b"<title>x</title>", r.read())
        s, _ = self.call("/../../etc/passwd")
        self.assertEqual(s, 404)


if __name__ == "__main__":
    unittest.main()
