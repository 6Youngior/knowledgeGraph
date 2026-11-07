"""Exercise the classroom research journey against the real running service.

Uses an isolated browser, explicitly resets local demo state before/after, and
saves actual UI crops for the Beamer source. No model or market data is mocked.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import httpx
from playwright.sync_api import sync_playwright, expect

from graph_store import write_json

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "presentation" / "generated"
REVIEW = ROOT / "docs" / "results" / "ui_review"
BASE = "http://127.0.0.1:8000"


def check():
    OUT.mkdir(exist_ok=True, parents=True)
    REVIEW.mkdir(exist_ok=True, parents=True)
    checks, errors = [], []
    def record(name, detail=None):
        checks.append({"name": name, "passed": True, "detail": detail})
        print("PASS", name, flush=True)

    with httpx.Client(base_url=BASE, timeout=20) as client, sync_playwright() as p:
        client.post("/api/reset").raise_for_status()
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1000}, accept_downloads=True)
        page.set_default_timeout(15000)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        rows = page.locator(".stock-roles .stock-row")
        def choose(event_id):
            page.locator("select").first.select_option(event_id)
            page.wait_for_timeout(450)
        def cutoff(day):
            field = page.locator('input[type="date"]')
            field.fill(day)
            page.wait_for_timeout(400)
        def current():
            page.get_by_role("button", name="全部资料", exact=True).first.click()
            page.wait_for_timeout(350)

        try:
            page.goto(BASE, wait_until="networkidle")
            expect(page.locator("h1")).to_contain_text("关联证券研究")
            expect(rows).to_have_count(2)
            narrative = page.locator(".path-narrative").inner_text()
            assert re.search(r"GLM-5\s*由\s*智谱\s*研发", narrative), narrative
            record("initial research shows real roles and correct factual direction", narrative)

            page.locator(".evidence-step .step-meta button").nth(1).click()
            expect(page.locator(".evidence-card")).to_contain_text("来源")
            assert page.locator(".evidence-card a[href^='https://']").count()
            page.locator(".evidence-card").screenshot(path=str(REVIEW / "source-detail.png"))
            record("a path opens original quote, publisher and a real source link")

            with page.expect_download() as download:
                page.get_by_role("button", name="研究简报", exact=True).click()
            target = ROOT / "docs" / "results" / "GLM5-下载简报.md"
            download.value.save_as(target)
            text = target.read_text(encoding="utf-8-sig")
            assert "02513.HK" in text and "https://" in text and "关系路径与来源" in text
            record("research brief download includes actual securities and citations")

            page.get_by_role("button", name="历史日期", exact=True).click()
            expect(rows).to_have_count(1)
            page.get_by_role("button", name=re.compile("^其他候选")).first.click()
            expect(page.locator(".excluded-lens")).to_contain_text("发布日期")
            record("historical view explains unverified publication dates without backdating")

            choose("event:deepseek-r1-release")
            expect(rows).to_have_count(4)
            page.get_by_role("button", name="历史日期", exact=True).click()
            expect(rows).to_have_count(0)
            cutoff("2025-02-03")
            expect(rows).to_have_count(2)
            cutoff("2025-02-05")
            expect(rows).to_have_count(4)
            page.locator(".temporal-panel").screenshot(path=str(OUT / "new_time.png"))
            record("DeepSeek evidence accumulates across real dates: zero, two, four securities")

            choose("event:qwen3-release")
            expect(rows).to_have_count(3)
            rows.filter(has_text="摩尔线程").click()
            expect(page.locator(".research-bottom")).to_contain_text("尚未上市")
            page.locator(".research-bottom").screenshot(path=str(REVIEW / "pre-listing-boundary.png"))
            page.get_by_role("button", name="历史日期", exact=True).click()
            expect(rows).to_have_count(2)
            record("Qwen preserves technical facts while distinguishing a later stock listing")

            choose("event:glm5-release")
            expect(rows).to_have_count(2)
            page.get_by_role("button", name="操作演示", exact=True).click()
            overlay = page.get_by_role("dialog", name="操作演示")
            expect(overlay).to_be_visible()
            for index in range(4):
                overlay.get_by_role("button", name="下一步").click()
                expect(overlay).to_contain_text(f"第 {index + 2} / 5 步")
            expect(page.locator(".update-grid")).to_be_visible()
            record("five guided steps retain the selected event through the update journey")

            page.locator(".sample-item").filter(has_text="GLM-5").first.click()
            page.locator(".mode-card").filter(has=page.locator("strong", has_text="回放")).click()
            page.get_by_role("button", name="执行知识抽取", exact=True).click()
            expect(page.locator(".validation.ok")).to_be_visible()
            expect(page.locator(".result-top")).to_contain_text("未调用模型")
            expect(page.locator(".result-metrics")).to_contain_text("1 节点 / 3 关系")
            page.locator(".result-top").scroll_into_view_if_needed()
            top = page.locator(".result-top").bounding_box()
            last = page.locator(".result-metrics").bounding_box()
            clip = {"x": top["x"], "y": top["y"], "width": top["width"],
                    "height": last["y"] + last["height"] - top["y"] + 4}
            page.screenshot(path=str(OUT / "new_update_full.png"), clip=clip)
            preview_cells = page.locator(".align-grid > div")
            preview_cells.first.scroll_into_view_if_needed()
            first = preview_cells.nth(0).bounding_box()
            second = preview_cells.nth(1).bounding_box()
            page.screenshot(path=str(OUT / "new_update.png"), clip={
                "x": first["x"], "y": first["y"],
                "width": second["x"] + second["width"] - first["x"],
                "height": max(first["height"], second["height"])})
            record("validated replay is visibly labelled and previews its real graph delta")

            page.get_by_role("button", name="确认入图", exact=True).click()
            expect(page.locator(".ingest-success")).to_contain_text("已写入图谱")
            page.get_by_role("button", name="再次导入", exact=True).click()
            expect(page.locator(".ingest-success")).to_contain_text("没有新增内容")
            record("repeat ingestion does not duplicate nodes or relations")
            page.get_by_role("button", name=re.compile("查看更新后的图谱")).click()
            expect(page.locator("select").first).to_have_value("event:glm5-release")
            expect(rows).to_have_count(3)
            expect(page.locator(".evidence-card .path-heading")).to_contain_text("摩尔线程")
            if page.get_by_role("button", name="结束演示", exact=True).count():
                page.get_by_role("button", name="结束演示", exact=True).click()
            record("returning from update highlights the newly explained security in the same event")
            # Let transient notifications disappear before producing slide art.
            page.wait_for_timeout(6000)

            page.get_by_role("button", name="硬件适配", exact=True).click()
            graph_counts = page.locator(".graph-top-right").inner_text()
            nums = [int(n) for n in re.findall(r"\d+", graph_counts)]
            assert len(nums) >= 2 and nums[0] >= 5 and nums[1] >= 4, graph_counts
            page.wait_for_timeout(1000)
            page.locator(".research-main").screenshot(path=str(OUT / "new_graph.png"))
            page.locator(".evidence-step").nth(1).screenshot(path=str(OUT / "new_evidence.png"))
            record("role filtering preserves a complete product-company-security evidence path", graph_counts)

            page.get_by_role("button", name="全部关系", exact=True).click()
            if page.get_by_role("button", name="取消选中", exact=True).count():
                page.get_by_role("button", name="取消选中", exact=True).click()
            page.evaluate("window.scrollTo(0,0)")
            page.locator(".evidence-card").evaluate("el => el.scrollTop = 0")
            page.wait_for_timeout(1000)
            page.screenshot(path=str(OUT / "new_workspace.png"))
            page.locator(".research-main").screenshot(path=str(OUT / "new_overview.png"))
            rows.filter(has_text="智谱").click()
            page.locator(".research-bottom > section").last.screenshot(path=str(OUT / "new_market.png"))

            page.get_by_role("button", name="案例库", exact=True).click()
            expect(page.locator("h1")).to_contain_text("案例")
            page.screenshot(path=str(OUT / "new_cases.png"))
            record("case library opens from the live research workspace")
            page.get_by_role("button", name="资料与方法", exact=True).click()
            expect(page.locator("h1")).to_contain_text("来源")
            page.screenshot(path=str(REVIEW / "sources-page.png"), full_page=True)
            record("source and method view remains available")

            assert not errors, errors
            record("no uncaught browser errors during the complete journey")
            return {"passed": True, "created_at": datetime.now(timezone.utc).isoformat(),
                    "checks": checks, "check_count": len(checks), "page_errors": errors,
                    "viewport": {"width": 1600, "height": 1000}}
        except Exception as exc:
            page.screenshot(path=str(REVIEW / "flow-failure.png"), full_page=True)
            return {"passed": False, "created_at": datetime.now(timezone.utc).isoformat(),
                    "checks": checks, "check_count": len(checks), "error": str(exc), "page_errors": errors}
        finally:
            browser.close()
            client.post("/api/reset").raise_for_status()


if __name__ == "__main__":
    report = check()
    write_json(ROOT / "docs" / "results" / "browser_validation.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)
