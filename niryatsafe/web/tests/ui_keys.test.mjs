// Every t("key") used in the app must exist in both languages, and every language must have the same keys.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const ui = JSON.parse(fs.readFileSync(path.join(root, "rules", "ui.json"), "utf8"));
const src = fs.readdirSync(path.join(root, "web", "src")).filter((f) => /\.(jsx|js)$/.test(f)).map((f) => fs.readFileSync(path.join(root, "web", "src", f), "utf8")).join("\n");
const used = new Set([...src.matchAll(/\bt\("([a-z_0-9]+)"/g)].map((m) => m[1]).filter((k) => !k.endsWith("_")));
for (const s of ["high", "med", "low"]) used.add("risk_" + s);
for (const s of ["busy", "ok", "diff", "off"]) used.add("verify_" + s);

test("all UI keys exist in English and Hindi", () => {
  for (const k of used) for (const l of ["en", "hi"]) assert.ok(ui[l][k] !== undefined, `missing ${l}.${k}`);
});
test("English and Hindi have the same keys and placeholders", () => {
  assert.deepEqual(Object.keys(ui.en).sort(), Object.keys(ui.hi).sort());
  const ph = (s) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort().join(",");
  for (const k of Object.keys(ui.en)) assert.equal(ph(ui.en[k]), ph(ui.hi[k]), k);
});
test("no UI key is unused (keeps the catalog honest)", () => {
  const unused = Object.keys(ui.en).filter((k) => !used.has(k) && !src.includes(`"${k}"`));
  assert.deepEqual(unused, []);
});
