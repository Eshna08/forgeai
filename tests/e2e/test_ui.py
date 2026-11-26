"""Playwright smoke tests for the web UI. They start the real server with LLM_PROVIDER=mock and drive Chromium.

Screenshots of the key screens are written to docs/screenshots/.
Run alone:  python -m pytest tests/e2e -q
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]
SHOTS = ROOT / "docs" / "screenshots"
HR_BRIEF = (ROOT / "demos" / "hr" / "brief.txt").read_text(encoding="utf-8").strip()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    runs = Path(tempfile.mkdtemp(prefix="forgeai_e2e_runs_"))
    for d in ("hr_demo", "spares_demo", "admissions_demo"):  # committed demo runs give the UI real data to show
        if (ROOT / "runs" / d).is_dir():
            shutil.copytree(ROOT / "runs" / d, runs / d)
    port = _free_port()
    env = {**os.environ, "LLM_PROVIDER": "mock", "EMBEDDING_BACKEND": "hash", "RUNS_DIR": str(runs), "TARGET_SCORE": "90"}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.app:app", "--port", str(port)], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/stats", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    else:
        proc.kill()
        pytest.fail("server did not start")
    yield base
    proc.kill()
    shutil.rmtree(runs, ignore_errors=True)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture()
def page(browser, server, request):
    ctx = browser.new_context(viewport={"width": 1366, "height": 900}, color_scheme="light", base_url=server)
    ctx.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())  # offline-safe, deterministic timing
    if request.node.name != "test_landing_loader_demo_cards_and_live_stats":  # only that test sees a first visit
        ctx.add_init_script("try { localStorage.setItem('forge-seen', '1') } catch (e) {}")
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    yield pg
    ctx.close()
    assert not errors, f"JavaScript errors: {errors}"


def shot(page, name, full=True):
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=full)


def api(server, path, data=None):
    req = urllib.request.Request(server + path, data=data, method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
    return json.loads(urllib.request.urlopen(req, timeout=30).read())


def wait_done(server, run_id, timeout=90):
    t0 = time.time()
    while time.time() - t0 < timeout:
        if api(server, f"/api/runs/{run_id}")["done"]:
            return
        time.sleep(0.3)
    raise AssertionError("run did not finish")


# ---------------------------------------------------------------------------------------------------------------
def test_landing_loader_demo_cards_and_live_stats(page):
    page.goto("/", wait_until="domcontentloaded")
    t0 = time.time()
    page.wait_for_selector("#loader", state="detached", timeout=2000)
    assert time.time() - t0 < 1.3  # loader: 700ms count-up + 300ms fade
    cards = page.locator("[data-demo]")
    cards.first.wait_for()
    assert cards.count() == 3
    page.wait_for_function("() => [...document.querySelectorAll('#stats .value')].every(v => v.textContent !== '…')")
    values = page.locator("#stats .value").all_inner_texts()
    assert values[0] == "3" and values[1] == "90"  # live: three committed demo runs, 30 cases each
    shot(page, "01-home-light")
    page.reload()  # repeat visit: no loader
    assert page.locator("#loader").count() == 0


def test_demo_card_prefills_brief(page):
    page.goto("/")
    page.locator("[data-demo='hr']").click()
    page.wait_for_url("**/#/build?demo=hr")
    page.wait_for_function("() => document.querySelector('#brief') && document.querySelector('#brief').value.length > 20")
    assert page.input_value("#brief") == HR_BRIEF
    assert page.locator("#demo-chip").get_by_text("leave_policy.pdf").is_visible()
    shot(page, "02-build-form")


def test_mock_build_stepper_intake_and_results(page):
    page.goto("/#/build?demo=hr")
    page.wait_for_function("() => document.querySelector('#brief').value.length > 20")
    assert page.is_checked("#opt-ask")
    page.click("#build-btn")
    page.wait_for_url("**/#/run/*")
    # intake: chat-style card, never more than 5 questions
    progress = page.locator("#q-progress")
    progress.wait_for(timeout=20000)
    total = int(progress.inner_text().split(" of ")[1])
    assert 1 <= total <= 5
    page.fill("#q-answer", "Shore-based office staff")
    page.click("[data-form] button[type=submit]")
    assert "Question 2 of" in progress.inner_text()
    assert page.locator("[data-step='1']").get_attribute("data-status") == "waiting-user"
    shot(page, "03-intake-chat", full=False)
    page.get_by_role("button", name="Let ForgeAI answer for me").click()
    # stepper moves through every stage and ends with a score + failure panel
    page.get_by_role("heading", name="What still fails and why").wait_for(timeout=60000)
    statuses = [page.locator(f"[data-step='{i}']").get_attribute("data-status") for i in range(1, 8)]
    assert all(s in ("done", "warning") for s in statuses), statuses
    assert page.locator(".score-ring strong").inner_text().endswith("%")
    assert page.locator(".gcard.unsupported").count() >= 1  # pension plan is not in the documents
    assert page.locator("#feed li").count() > 10
    page.locator("#stepper").scroll_into_view_if_needed()
    shot(page, "04-run-stepper-and-guard", full=False)
    shot(page, "05-results-dashboard")


def test_approval_blocks_generation_until_approved(page, server):
    page.goto("/#/build?demo=hr")
    page.wait_for_function("() => document.querySelector('#brief').value.length > 20")
    page.uncheck("#opt-ask")
    page.check("#opt-approve")
    page.click("#build-btn")
    page.get_by_role("heading", name="Review the requirements").wait_for(timeout=30000)
    run_id = page.url.rsplit("/", 1)[1]
    time.sleep(1.5)  # still paused: generation has not started
    assert page.locator("[data-step='3']").get_attribute("data-status") == "waiting"
    assert page.locator("[data-step='2']").get_attribute("data-status") == "waiting-user"
    assert not api(server, f"/api/runs/{run_id}")["done"]
    events = page.locator("#feed").inner_text()
    assert "Started: Generate agent" not in events
    shot(page, "06-approval", full=False)
    page.get_by_role("button", name="Approve and build").click()
    page.get_by_role("heading", name="What still fails and why").wait_for(timeout=60000)
    assert page.locator("[data-step='3']").get_attribute("data-status") in ("done", "warning")


def test_chat_returns_answer_with_sources(page):
    page.goto("/#/chat/spares_demo")
    page.wait_for_selector("#chat-input")
    page.fill("#chat-input", "What would 4 units of SP-0003 cost in total?")
    page.click("#composer button[type=submit]")
    reply = page.locator(".bubble.bot").last
    reply.get_by_text("How I answered").wait_for(timeout=30000)
    reply.get_by_text("How I answered").click()
    assert "spares_catalogue.csv" in reply.inner_text()
    assert "calculator" in reply.inner_text()
    page.fill("#chat-input", "Who painted the Sistine Chapel ceiling?")
    page.click("#composer button[type=submit]")
    page.locator(".bubble.soft-refusal").wait_for(timeout=30000)
    shot(page, "07-chat", full=False)


def test_requirements_page_lists_all_nine(page):
    page.goto("/#/requirements")
    page.locator("[data-req='R9']").wait_for(timeout=20000)
    for i in range(1, 10):
        assert page.locator(f"[data-req='R{i}']").count() == 1
    assert page.locator("[data-req^='S']").count() >= 5
    assert page.locator("[data-req='R9'] .st.pass").count() == 1
    shot(page, "08-requirements")


def test_runs_page_and_how_it_works_modal(page):
    page.goto("/#/runs")
    page.locator(".run-card").first.wait_for()
    assert page.locator(".run-card").count() >= 3
    shot(page, "09-runs")
    page.click("#how-btn")
    page.get_by_role("dialog").wait_for()
    shot(page, "10-how-it-works", full=False)
    page.keyboard.press("Escape")
    assert page.get_by_role("dialog").count() == 0


def test_results_of_committed_demo_and_dark_mode(page):
    page.goto("/#/run/spares_demo")
    page.get_by_role("heading", name="Optimizer changelog").wait_for(timeout=20000)
    shot(page, "11-results-spares")
    bg_light = page.evaluate("getComputedStyle(document.body).backgroundColor")
    page.click("#theme-btn")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    bg_dark = page.evaluate("getComputedStyle(document.body).backgroundColor")
    assert bg_light != bg_dark
    shot(page, "12-results-dark")
    page.goto("/")
    page.locator("[data-demo]").first.wait_for()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"  # choice persists
    shot(page, "13-home-dark", full=False)


@pytest.mark.parametrize("route", ["/", "/#/build", "/#/run/spares_demo", "/#/chat/spares_demo", "/#/runs", "/#/requirements"])
def test_no_horizontal_overflow_at_360px(browser, server, route):
    ctx = browser.new_context(viewport={"width": 360, "height": 740}, base_url=server, color_scheme="light")
    ctx.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())
    ctx.add_init_script("try { localStorage.setItem('forge-seen', '1') } catch (e) {}")
    page = ctx.new_page()
    page.goto(route)
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(400)
    sw = page.evaluate("document.documentElement.scrollWidth")
    assert sw <= 360, f"{route} overflows: scrollWidth={sw}"
    if route == "/":
        shot(page, "14-mobile-home")
    if route == "/#/run/spares_demo":
        shot(page, "15-mobile-results", full=False)
    ctx.close()


def test_accessibility_basics(page):
    """Labels, names, focus order: every form control and button must have an accessible name."""
    for route in ["/", "/#/build", "/#/chat/spares_demo", "/#/runs", "/#/requirements", "/#/run/spares_demo"]:
        page.goto(route)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)
        unnamed = page.evaluate("""() => [...document.querySelectorAll('button, a[href], input, select, textarea')]
            .filter(el => el.offsetParent !== null || el.type === 'file')
            .filter(el => {
              const name = (el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.title || el.innerText || el.value || '').trim();
              const labelled = el.id && document.querySelector(`label[for="${el.id}"]`);
              return !name && !labelled && !el.closest('label');
            }).map(el => el.outerHTML.slice(0, 80))""")
        assert not unnamed, f"{route}: controls without accessible names: {unnamed}"
        assert page.locator("h1").count() >= 1, f"{route} has no h1"
    # keyboard: first Tab lands on the skip link, Enter moves focus to main
    page.goto("/")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.className") == "skip"


def test_axe_wcag_aa_no_violations(browser, server):
    """Lighthouse-style accessibility audit: axe-core WCAG 2 A/AA rules on every view, light and dark."""
    axe_mod = pytest.importorskip("axe_playwright_python.sync_playwright")
    axe = axe_mod.Axe()
    problems = {}
    for scheme in ("light", "dark"):
        ctx = browser.new_context(viewport={"width": 1280, "height": 900}, base_url=server, color_scheme=scheme)
        ctx.route("**/fonts.{googleapis,gstatic}.com/**", lambda r: r.abort())
        ctx.add_init_script("try { localStorage.setItem('forge-seen', '1') } catch (e) {}")
        pg = ctx.new_page()
        for route in ["/", "/#/build?demo=hr", "/#/run/spares_demo", "/#/chat/spares_demo", "/#/runs", "/#/requirements"]:
            pg.goto(route)
            pg.wait_for_load_state("networkidle")
            pg.wait_for_timeout(500)
            v = axe.run(pg, options={"runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa"]}}).response["violations"]
            if v:
                problems[f"{scheme} {route}"] = [(x["id"], [n["target"] for n in x["nodes"][:3]]) for x in v]
        ctx.close()
    assert not problems, problems
