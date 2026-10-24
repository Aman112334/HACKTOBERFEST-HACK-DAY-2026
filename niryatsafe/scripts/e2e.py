"""End-to-end check in headless Chromium: verdicts, Hindi, paste import, service worker + offline reload, console errors.
   python scripts/e2e.py [--shots DIR] [--video DIR]      (needs: pip install playwright && playwright install chromium)"""
import argparse, os, sys, threading, time
from http.server import ThreadingHTTPServer
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from niryatsafe.serve import make_handler  # noqa: E402
from niryatsafe.service import Service  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--shots", default=os.path.join(ROOT, "docs", "screens"))
ap.add_argument("--video", default=None)
a = ap.parse_args()
os.makedirs(a.shots, exist_ok=True)

srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Service()))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}/"
errors, checks = [], []


def check(name, ok, detail=""):
    checks.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (f"  [{detail}]" if detail and not ok else ""))


def stamp(page):
    return page.locator("svg.stamp").first.get_attribute("aria-label")


with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN", record_video_dir=a.video, record_video_size={"width": 1280, "height": 720}) if a.video \
        else br.new_context(viewport={"width": 1280, "height": 900}, locale="en-IN")
    page = ctx.new_page()
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(base)
    page.wait_for_selector("svg.stamp")
    check("Lot 402 loads as the default sample", "402" in page.locator(".lotline").inner_text())
    check("Lot 402 verdict is FIX FIRST", stamp(page) == "FIX FIRST", stamp(page))
    txt = page.locator(".headline").inner_text()
    check("headline says compliance cannot be shown", "Compliance cannot be shown" in txt, txt[:120])
    check("path to ship has the deck's re-test sentence", "detection limit of 0.01 mg/kg or lower, then attach the new certificate" in page.locator(".path").inner_text())
    page.screenshot(path=os.path.join(a.shots, "01-lot402-desktop.png"))

    page.get_by_role("button", name="Passes India, fails the EU").click()
    page.wait_for_timeout(500)
    check("hold sample gives HOLD", stamp(page) == "HOLD", stamp(page))
    check("India-pass / EU-fail bars are shown", page.locator(".bar.india").count() >= 1)
    page.screenshot(path=os.path.join(a.shots, "02-hold-desktop.png"))

    page.get_by_role("button", name="हिं").click()
    page.wait_for_timeout(400)
    check("Hindi stamp reads रोकें", stamp(page) == "रोकें", stamp(page))
    check("page language switches to hi", page.evaluate("document.documentElement.lang") == "hi")
    check("no raw i18n keys leak into the page", "kicker_in_rice" not in page.inner_text("body") and "{" not in page.inner_text(".verdict"))
    page.screenshot(path=os.path.join(a.shots, "03-hold-hindi.png"))
    page.get_by_role("button", name="EN").click()

    page.get_by_role("button", name="Start blank").click()
    page.get_by_role("button", name="Paste lab table").click()
    page.fill("textarea", "Parameter\tResult\tUnit\tLOQ\nTricyclazole\t0.04\tmg/kg\t0.01\nCarbendazim\tND\tmg/kg\t0.01\nDiazinon\tBQL\tmg/kg\t0.02")
    page.get_by_role("button", name="Read table").click()
    page.wait_for_timeout(300)
    check("paste import reads 3 rows", "Read 3 rows" in page.locator(".note-line").inner_text(), page.locator(".note-line").inner_text())
    check("pasted tricyclazole 0.04 blocks shipment", stamp(page) == "HOLD", stamp(page))

    page.get_by_role("button", name="Lot 402 · Punjab → Germany").click()
    page.wait_for_timeout(300)
    page.locator(".slip select").nth(1).select_option("OTHER")
    page.wait_for_timeout(300)
    check("an uncovered destination cannot ship or hold", stamp(page) == "FIX FIRST" and "not covered yet" in page.locator(".verdict").inner_text())
    page.get_by_role("button", name="Lot 402 · Punjab → Germany").click()
    page.screenshot(path=os.path.join(a.shots, "04-lot402-after.png"))

    # service worker + offline
    page.reload()
    page.wait_for_function("navigator.serviceWorker && navigator.serviceWorker.controller !== null || true")
    page.wait_for_selector(".pill", state="visible")
    for _ in range(40):
        if "works offline" in page.locator(".pill").inner_text().lower():
            break
        time.sleep(0.25)
    check("service worker is ready (works offline)", "works offline" in page.locator(".pill").inner_text().lower())
    page.reload()
    page.wait_for_load_state("networkidle")
    ctx.set_offline(True)
    page.reload()
    page.wait_for_selector("svg.stamp", timeout=8000)
    check("app reloads while offline", True)
    check("offline pill shows Offline", page.locator(".pill").inner_text().lower().startswith("offline"))
    page.get_by_role("button", name="Start blank").click()
    page.wait_for_timeout(300)
    check("verdict still computes offline", stamp(page) == "FIX FIRST", stamp(page))
    page.screenshot(path=os.path.join(a.shots, "05-offline.png"))
    ctx.set_offline(False)

    m = br.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, locale="hi-IN", is_mobile=True, has_touch=True)
    mp = m.new_page()
    mp.goto(base)
    mp.wait_for_selector("svg.stamp")
    check("mobile defaults to Hindi from the browser language", mp.evaluate("document.documentElement.lang") == "hi")
    check("no horizontal scroll on a 390px phone", mp.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1"),
          str(mp.evaluate("document.documentElement.scrollWidth")))
    mp.screenshot(path=os.path.join(a.shots, "06-mobile-hindi.png"))
    mp.locator(".verdict").scroll_into_view_if_needed()
    mp.screenshot(path=os.path.join(a.shots, "07-mobile-verdict.png"))
    sa = os.path.join(ROOT, "web", "dist", "niryatsafe-standalone.html")
    if os.path.exists(sa):
        sp = br.new_page(viewport={"width": 1100, "height": 800})
        sp.on("pageerror", lambda e: errors.append("standalone: " + str(e)))
        sp.goto("file://" + sa)
        sp.wait_for_selector("svg.stamp")
        check("standalone HTML opens from disk and gives the Lot 402 verdict", stamp(sp) == "FIX FIRST", stamp(sp))
    if a.video:
        page.close(); ctx.close()
    br.close()

check("no console errors", not errors, "; ".join(errors[:3]))
srv.shutdown()
bad = [n for n, ok in checks if not ok]
print(f"\n{len(checks) - len(bad)}/{len(checks)} checks passed")
sys.exit(1 if bad else 0)
