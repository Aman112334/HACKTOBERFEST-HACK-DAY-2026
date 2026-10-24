import { createRoot } from "react-dom/client";
import builtin from "../../rules/compiled/bundle.json";
import App from "./App.jsx";
import { load, save } from "./ui.js";
import "./styles.css";

const ver = (v) => String(v).split(".").map((n) => parseInt(n, 10) || 0);
const newer = (a, b) => { const x = ver(a), y = ver(b); for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0); return false; };

// The rules pack: use a newer one that was cached from the server earlier, otherwise the one built into the app.
function pick() {
  const cached = load("ns.pack", null);
  return cached && cached.meta && cached.i18n && newer(cached.meta.version, builtin.meta.version) ? cached : builtin;
}
// Called when the server offers a different pack: accept it only if it is newer, and keep it for offline use.
function onPack(candidate, current) {
  if (!newer(candidate.meta.version, current.meta.version)) return false;
  save("ns.pack", candidate);
  return true;
}

createRoot(document.getElementById("root")).render(<App initialBundle={pick()} onPack={onPack} />);

if ("serviceWorker" in navigator && /^https?:/.test(location.protocol)) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
