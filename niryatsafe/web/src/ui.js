import { useEffect, useState } from "react";
import { fill } from "./engine.js";

export const cx = (...a) => a.filter(Boolean).join(" ");

export const todayISO = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

export function load(key, fallback) {
  try {
    const v = window.localStorage.getItem(key);
    return v === null ? fallback : JSON.parse(v);
  } catch (e) {
    return fallback;
  }
}
export function save(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch (e) {
    /* storage can be empty, full or blocked: the app must still work */
  }
}

export function useOnline() {
  const [on, setOn] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const up = () => setOn(true), down = () => setOn(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => { window.removeEventListener("online", up); window.removeEventListener("offline", down); };
  }, []);
  return on;
}

export function makeT(bundle, lang) {
  const ui = bundle.i18n[lang].ui, en = bundle.i18n.en.ui;
  return (key, params) => {
    const s = ui[key] !== undefined ? ui[key] : en[key] !== undefined ? en[key] : key;
    return params ? fill(s, params) : s;
  };
}
