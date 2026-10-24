// Build the PWA with esbuild:  node build.mjs            -> dist/   (app.js, app.css, sw.js, icons, manifest)
//                              node build.mjs --standalone -> dist/niryatsafe-standalone.html (one file, opens by double-click)
import { build } from "esbuild";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(root, "dist");
const common = { entryPoints: [path.join(root, "src/main.jsx")], bundle: true, minify: true, jsx: "automatic", target: ["es2020"],
  define: { "process.env.NODE_ENV": '"production"' }, legalComments: "none", logLevel: "warning" };

const walk = (d, base = d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? walk(path.join(d, e.name), base) : [path.relative(base, path.join(d, e.name)).split(path.sep).join("/")]);

if (process.argv.includes("--standalone")) {
  const out = await build({ ...common, outdir: path.join(root, ".tmp"), write: false, loader: { ".woff": "dataurl" } });
  const js = out.outputFiles.find((f) => f.path.endsWith(".js")).text.replace(/<\/script/gi, "<\\/script");
  const css = out.outputFiles.find((f) => f.path.endsWith(".css")).text;
  let html = fs.readFileSync(path.join(root, "public/index.html"), "utf8")
    .replace(/<link rel="manifest"[^>]*>\n?/, "").replace(/<link rel="apple-touch-icon"[^>]*>\n?/, "")
    .replace(/<link rel="icon"[^>]*>\n?/, "")
    .replace('<link rel="stylesheet" href="app.css">', () => `<style>${css}</style>`)
    .replace('<script src="app.js" defer></script>', () => `<script>${js}</script>`);
  fs.mkdirSync(dist, { recursive: true });
  fs.writeFileSync(path.join(dist, "niryatsafe-standalone.html"), html);
  console.log("standalone:", (html.length / 1024).toFixed(0), "KB");
} else {
  fs.rmSync(dist, { recursive: true, force: true });
  fs.mkdirSync(dist, { recursive: true });
  await build({ ...common, outfile: path.join(dist, "app.js"), loader: { ".woff": "file" }, assetNames: "fonts/[name]" });
  for (const f of ["index.html", "manifest.webmanifest"]) fs.copyFileSync(path.join(root, "public", f), path.join(dist, f));
  fs.cpSync(path.join(root, "public/icons"), path.join(dist, "icons"), { recursive: true });
  const files = walk(dist);
  const hash = crypto.createHash("sha256");
  for (const f of files.sort()) hash.update(f).update(fs.readFileSync(path.join(dist, f)));
  const version = hash.digest("hex").slice(0, 10);
  const assets = ["./", ...files];
  const sw = fs.readFileSync(path.join(root, "public/sw.template.js"), "utf8").replaceAll("__VERSION__", version).replaceAll("__ASSETS__", JSON.stringify(assets));
  fs.writeFileSync(path.join(dist, "sw.js"), sw);
  console.log("built dist:", assets.length, "files, cache", version);
}
