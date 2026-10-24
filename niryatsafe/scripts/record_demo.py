"""Record the fallback demo video (deck slide 9: "demo script + fallback recording"): Lot 402 -> fix -> SHIP -> Hindi -> HOLD -> offline.
   python scripts/record_demo.py        ->  docs/demo/fallback-demo.webm"""
import os, shutil, sys, threading, time
from http.server import ThreadingHTTPServer
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from niryatsafe.serve import make_handler  # noqa: E402
from niryatsafe.service import Service  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

out_dir = os.path.join(ROOT, "docs", "demo")
os.makedirs(out_dir, exist_ok=True)
tmp = os.path.join(out_dir, "_tmp")
shutil.rmtree(tmp, ignore_errors=True)
srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Service()))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"
W = lambda pg, ms: pg.wait_for_timeout(ms)

with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=tmp, record_video_size={"width": 1280, "height": 720}, locale="en-IN")
    pg = ctx.new_page()
    pg.goto(base)
    pg.wait_for_selector("svg.stamp")
    for _ in range(40):                      # let the service worker cache the app, so the offline scene works
        if "works offline" in pg.locator(".pill").inner_text().lower():
            break
        time.sleep(0.25)
    W(pg, 3500)                              # Lot 402: FIX FIRST, the two bars, "Compliance cannot be shown."
    row = pg.locator(".lrow", has_text="Tricyclazole").first
    row.scroll_into_view_if_needed()
    W(pg, 1500)
    loq = row.locator("input[aria-label='LOQ']")
    loq.click(); loq.fill("")
    loq.type("0.01", delay=220)             # the re-test result: detection limit 0.01
    W(pg, 3500)                              # SHIP
    pg.evaluate("window.scrollTo(0, 0)")
    pg.get_by_role("button", name="हिं").click(); W(pg, 3000)
    pg.get_by_role("button", name="EN").click(); W(pg, 800)
    pg.get_by_role("button", name="Passes India, fails the EU").click(); W(pg, 3500)   # HOLD with India / EU / lab bars
    pg.locator(".gapchart").scroll_into_view_if_needed(); W(pg, 3500)
    ctx.set_offline(True)
    pg.reload(); pg.wait_for_selector("svg.stamp", timeout=8000); W(pg, 1500)
    pg.get_by_role("button", name="Lot 402 · Punjab → Germany").click(); W(pg, 3500)    # offline: still computes
    pg.close(); ctx.close(); br.close()

vids = [f for f in os.listdir(tmp) if f.endswith(".webm")]
shutil.move(os.path.join(tmp, vids[0]), os.path.join(out_dir, "fallback-demo.webm"))
shutil.rmtree(tmp, ignore_errors=True)
srv.shutdown()
print("wrote docs/demo/fallback-demo.webm", os.path.getsize(os.path.join(out_dir, "fallback-demo.webm")) // 1024, "KB")
