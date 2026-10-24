// Differential test: the JS engine must reproduce the Python engine bit-for-bit on every vector.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { evaluate, canon, cyrb53, resolveSample, renderFinding } from "../src/engine.js";
import { parseLine, parseTable } from "../src/labparse.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const read = (...p) => JSON.parse(fs.readFileSync(path.join(root, ...p), "utf8"));
const bundle = read("rules", "compiled", "bundle.json");
const vectors = read("tests", "vectors", "parity.json");

test("engine parity with Python on all vectors", () => {
  let bad = 0;
  vectors.forEach((v, i) => {
    const r = evaluate(JSON.parse(JSON.stringify(v.input)), bundle);
    const ok = cyrb53(canon(r)) === v.digest && r.verdict === v.verdict && r.memo_id === v.memo_id;
    if (!ok) { bad++; if (bad <= 3) console.error("MISMATCH vector", i, "py:", v.verdict, v.counts, "js:", r.verdict, r.counts); }
  });
  assert.equal(bad, 0, `${bad} of ${vectors.length} vectors differ`);
});

test("samples resolve and give their expected verdicts", () => {
  for (const s of bundle.samples) {
    const r = evaluate(resolveSample(s, "2026-10-21"), bundle);
    assert.equal(r.verdict, s.expect, s.id);
  }
});

test("lab table parser matches shared cases", () => {
  for (const c of read("tests", "labparse_cases.json")) {
    const r = parseLine(c.line, bundle);
    if (c.expect === null) { assert.equal(r, null, c.line); continue; }
    assert.ok(r, c.line);
    for (const [k, v] of Object.entries(c.expect)) assert.equal(r[k], v, `${c.line} -> ${k}`);
  }
  const t = parseTable("Parameter\tResult\tUnit\tLOQ\nTricyclazole\t0.04\tmg/kg\t0.01\nCarbendazim\tND\tmg/kg\t0.01\nnoise", bundle);
  assert.equal(t.rows.length, 2);
  assert.equal(t.skipped.length, 2);
});

test("every finding renders in both languages without leftover placeholders", () => {
  for (const s of bundle.samples) {
    const r = evaluate(resolveSample(s, "2026-10-21"), bundle);
    for (const lang of ["en", "hi"]) for (const f of r.findings) {
      const x = renderFinding(f, bundle, lang);
      assert.ok(!/\{\w+\}/.test(x.text), `${f.id} ${lang}: ${x.text}`);
      if (x.actionText !== null) assert.ok(!/\{\w+\}/.test(x.actionText), `${f.id} ${lang} action`);
    }
  }
});
