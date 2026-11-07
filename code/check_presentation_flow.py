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

GRAPH_GEOMETRY = """() => {
    const area=document.querySelector('.research-graph-canvas').getBoundingClientRect();
    const nodes=[...document.querySelectorAll('.react-flow__node')].map(el=>{
        const r=el.getBoundingClientRect(),style=getComputedStyle(el);
        return {id:el.dataset.id,x:r.x,y:r.y,w:r.width,h:r.height,visible:style.visibility!=='hidden'&&Number(style.opacity)>0};
    });
    return {count:nodes.length,outside:nodes.filter(n=>n.x<area.x-2||n.y<area.y-2||n.x+n.w>area.right+2||n.y+n.h>area.bottom+2).map(n=>n.id),
        hidden:nodes.filter(n=>!n.visible).map(n=>n.id)};
}"""


def assert_historical_graph(page, expected_stocks):
    page.wait_for_timeout(200)
    expected_edges={0:1,2:7,4:13}[expected_stocks]
    expect(page.locator(".react-flow__edge-path")).to_have_count(expected_edges)
    geometry=page.evaluate(GRAPH_GEOMETRY)
    geometry["rendered_edges"]=page.locator(".react-flow__edge-path").count()
    assert not geometry["outside"] and not geometry["hidden"], geometry
    return {"stocks":expected_stocks,**geometry}


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
        page = browser.new_page(viewport={"width": 1920, "height": 1080}, accept_downloads=True)
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
            expect(page.locator("h1")).to_contain_text("GLM-5 发布")
            expect(rows).to_have_count(2)
            expect(page.locator(".evidence-step").nth(1)).to_contain_text("研发主体")
            expect(page.locator(".evidence-step").nth(1)).to_contain_text("智谱")
            expect(page.locator(".react-flow__node")).to_have_count(7)
            expect(page.locator(".react-flow__edge")).to_have_count(7)
            record("initial research shows two securities and the actual development relationship")

            page.locator(".evidence-step .step-meta button").nth(1).click()
            expect(page.locator(".evidence-card")).to_contain_text("来源")
            assert page.locator(".evidence-card a[href^='https://']").count()
            page.locator(".evidence-card").screenshot(path=str(REVIEW / "source-detail.png"))
            record("a path opens original quote, publisher and a real source link")

            with page.expect_download() as download:
                page.get_by_role("button", name="导出简报", exact=True).click()
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
            historical_geometry=[assert_historical_graph(page,0)]
            cutoff("2025-02-03")
            expect(rows).to_have_count(2)
            historical_geometry.append(assert_historical_graph(page,2))
            cutoff("2025-02-05")
            expect(rows).to_have_count(4)
            historical_geometry.append(assert_historical_graph(page,4))
            page.locator(".temporal-panel").screenshot(path=str(OUT / "new_time.png"))
            record("DeepSeek evidence accumulates across real dates: zero, two, four securities")
            record("all historical graph nodes remain visible for zero, two and four securities",historical_geometry)

            choose("event:qwen3-release")
            expect(rows).to_have_count(3)
            rows.filter(has_text="摩尔线程").click()
            page.get_by_role("tab", name="行情对照").click()
            expect(page.locator(".market-panel")).to_contain_text("尚未上市")
            page.locator(".market-panel").screenshot(path=str(REVIEW / "pre-listing-boundary.png"))
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
            page.get_by_role("button", name="结束演示", exact=True).click()

            sample_option = page.locator(".sample-picker option").first.get_attribute("value")
            page.get_by_label("选择示例资料").select_option(sample_option)
            page.locator(".mode-card").filter(has=page.locator("strong", has_text="回放")).click()
            page.get_by_role("button", name="抽取关系", exact=True).click()
            expect(page.locator(".validation.ok")).to_be_visible()
            expect(page.locator(".result-top")).to_contain_text("未调用模型")
            expect(page.locator(".result-summary")).to_contain_text(re.compile(r"新增\s*1\s*个节点、\s*3\s*条关系"))
            page.locator(".update-result").screenshot(path=str(OUT / "new_update_full.png"))
            page.locator(".result-summary").screenshot(path=str(OUT / "new_update.png"))
            confirm = page.get_by_role("button", name="确认入图", exact=True)
            assert confirm.bounding_box()["y"] + confirm.bounding_box()["height"] < 1080
            record("validated replay is visibly labelled and previews its real graph delta")

            page.get_by_role("button", name="确认入图", exact=True).click()
            expect(page.locator(".ingest-success")).to_contain_text("已写入图谱")
            page.get_by_role("button", name="再次导入", exact=True).click()
            expect(page.locator(".ingest-success")).to_contain_text("没有新增内容")
            record("repeat ingestion does not duplicate nodes or relations")
            page.get_by_role("button", name=re.compile("查看新增证券")).click()
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
            page.get_by_role("tab", name="行情对照").click()
            expect(page.locator(".market-meta")).to_contain_text("智谱")
            expect(page.locator(".return-table")).to_contain_text("+56.22%")
            page.locator(".market-panel").screenshot(path=str(OUT / "new_market.png"))
            record("market tab shows the selected security and same-window benchmark returns")

            page.get_by_role("button", name="事件目录", exact=True).click()
            expect(page.locator("h1")).to_contain_text("事件目录")
            page.screenshot(path=str(OUT / "new_cases.png"))
            record("case library opens from the live research workspace")
            page.get_by_role("button", name="资料与方法", exact=True).click()
            expect(page.locator("h1")).to_contain_text("资料与方法")
            page.screenshot(path=str(REVIEW / "sources-page.png"), full_page=True)
            record("source and method view remains available")

            page.get_by_label("筛选来源类型").select_option("official_news")
            expect(page.locator(".source-row")).to_have_count(8)
            record("source browser filters real records without a row of repeated badges")
            page.get_by_role("button", name="事件研究", exact=True).click()
            page.get_by_role("tab", name="关系图谱").click()
            page.get_by_role("button", name="全部关系", exact=True).click()
            if page.get_by_role("button", name="取消选中", exact=True).count():
                page.get_by_role("button", name="取消选中", exact=True).click()
            for width, height in [(1920,1080),(1536,960),(1280,900)]:
                page.set_viewport_size({"width":width,"height":height})
                page.wait_for_timeout(700)
                geometry = page.evaluate('''() => {
                  const area = document.querySelector('.research-graph-canvas').getBoundingClientRect();
                  const nodes = [...document.querySelectorAll('.react-flow__node')].map(el => {
                    const r=el.getBoundingClientRect();
                    return {id:el.dataset.id,x:r.x,y:r.y,w:r.width,h:r.height};
                  });
                  const overlaps=[];
                  for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++) {
                    const a=nodes[i],b=nodes[j];
                    if(Math.min(a.x+a.w,b.x+b.w)>Math.max(a.x,b.x)+1 && Math.min(a.y+a.h,b.y+b.h)>Math.max(a.y,b.y)+1) overlaps.push([a.id,b.id]);
                  }
                  return {overlaps, outside:nodes.filter(n=>n.x<area.x-2||n.y<area.y-2||n.x+n.w>area.right+2||n.y+n.h>area.bottom+2).map(n=>n.id),minNameSize:Math.min(...nodes.map(n=>16*n.w/174)),overflow:document.documentElement.scrollWidth>innerWidth};
                }''')
                assert not geometry["overlaps"] and not geometry["outside"] and not geometry["overflow"], geometry
                page.screenshot(path=str(REVIEW / ("workspace-%s.png" % width)))
                record("graph nodes fit without overlaps at %s px" % width, geometry)
            page.set_viewport_size({"width":1920,"height":1080})
            page.wait_for_timeout(700)
            facts = client.get("/api/events/event:glm5-release").json()["graph"]["edges"]
            endpoints = page.evaluate('''() => [...document.querySelectorAll('.react-flow__edge')].map(edge => {
                const p=edge.querySelector('.react-flow__edge-path');
                const start=p.getPointAtLength(0), end=p.getPointAtLength(p.getTotalLength()), matrix=p.getScreenCTM();
                const a=new DOMPoint(start.x,start.y).matrixTransform(matrix), b=new DOMPoint(end.x,end.y).matrixTransform(matrix);
                return {id:edge.dataset.id,start:{x:a.x,y:a.y},end:{x:b.x,y:b.y},arrow:p.getAttribute('marker-end')};
            })''')
            boxes = page.evaluate('''() => Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map(el => {
                const r=el.getBoundingClientRect();return [el.dataset.id,{x:r.x,y:r.y,right:r.right,bottom:r.bottom}];
            }))''')
            def distance(point, box):
                return max(box["x"]-point["x"],0,point["x"]-box["right"])**2 + max(box["y"]-point["y"],0,point["y"]-box["bottom"])**2
            fact_map = {edge["id"]:edge for edge in facts}
            for edge in endpoints:
                fact = fact_map[edge["id"]]
                assert edge["arrow"] and distance(edge["start"],boxes[fact["source"]]) < 196 and distance(edge["end"],boxes[fact["target"]]) < 196, edge
            record("visible arrows attach to the original factual source and target", {"edges":len(endpoints)})
            crossings = page.evaluate('''(facts) => {
                const map=Object.fromEntries(facts.map(e=>[e.id,e]));
                const nodes=[...document.querySelectorAll('.react-flow__node')].map(el=>({id:el.dataset.id,box:el.getBoundingClientRect()}));
                const hits=[];
                for(const el of document.querySelectorAll('.react-flow__edge')) {
                    const fact=map[el.dataset.id], path=el.querySelector('.react-flow__edge-path'), matrix=path.getScreenCTM();
                    for(let d=0;d<path.getTotalLength();d+=4) {
                        const local=path.getPointAtLength(d),point=new DOMPoint(local.x,local.y).matrixTransform(matrix);
                        for(const node of nodes) {
                            if(node.id===fact.source||node.id===fact.target)continue;
                            const r=node.box;
                            if(point.x>r.x+3&&point.x<r.right-3&&point.y>r.y+3&&point.y<r.bottom-3)hits.push({edge:el.dataset.id,node:node.id});
                        }
                    }
                }
                return hits;
            }''', facts)
            assert not crossings, crossings
            record("graph lines avoid unrelated node rectangles")

            page.get_by_role("button", name="全屏", exact=True).click()
            expect(page.locator(".research-graph.fullscreen")).to_be_visible()
            page.keyboard.press("Escape")
            expect(page.locator(".research-graph.fullscreen")).to_have_count(0)
            record("graph fullscreen opens and exits with Escape")
            assert not errors, errors
            record("no uncaught browser errors during the complete journey")
            return {"passed": True, "created_at": datetime.now(timezone.utc).isoformat(),
                    "checks": checks, "check_count": len(checks), "page_errors": errors,
                    "viewport": {"width": 1920, "height": 1080}}
        except Exception as exc:
            page.screenshot(path=str(REVIEW / "flow-failure.png"), full_page=True)
            return {"passed": False, "created_at": datetime.now(timezone.utc).isoformat(),
                    "checks": checks, "check_count": len(checks), "error": str(exc), "page_errors": errors}
        finally:
            browser.close()
            client.post("/api/reset").raise_for_status()


async def check_date_transitions():
    """A slow response must not clear the diagram or its date controls."""
    import asyncio
    from playwright.async_api import async_playwright, expect as async_expect

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        try:
            page = await browser.new_page(viewport={"width":1920,"height":1080})
            await page.goto(BASE, wait_until="networkidle")
            await page.add_style_tag(content=".research-main{height:660px !important}")
            await async_expect(page.locator(".stock-row")).to_have_count(2)
            await page.get_by_role("button",name="导入资料",exact=True).click()
            await page.locator(".mode-card").nth(2).click()
            await page.get_by_role("button",name="抽取关系",exact=True).click()
            await async_expect(page.locator(".validation.ok")).to_be_visible()
            await page.get_by_role("button",name="确认入图",exact=True).click()
            await async_expect(page.locator(".ingest-success")).to_contain_text("已写入")
            await page.get_by_role("button",name="查看新增证券",exact=True).click()
            await async_expect(page.locator(".stock-row")).to_have_count(3)
            await page.get_by_role("tab",name="行情对照",exact=True).click()
            await page.wait_for_timeout(15000)
            await page.get_by_label("选择研究案例").select_option("event:deepseek-r1-release")
            await async_expect(page.locator(".stock-row")).to_have_count(4)
            await page.wait_for_timeout(1500)
            await page.get_by_role("button", name="历史日期", exact=True).click()
            await async_expect(page.locator(".stock-row")).to_have_count(0)
            await async_expect(page.locator(".react-flow__edge-path")).to_have_count(1)
            await async_expect(page.locator(".date-chips button")).to_have_count(5)
            async def delayed(route):
                await asyncio.sleep(0.9)
                await route.continue_()
            await page.route("**/api/events/*", delayed)
            await page.route("**/api/research/*", delayed)
            for day, before, after in [("2025-02-03",0,2),("2025-02-05",2,4)]:
                previous = await page.locator(".react-flow__node").count()
                await page.get_by_role("button", name=day, exact=True).click()
                await page.wait_for_timeout(180)
                assert await page.locator(".react-flow__node").count() == previous
                assert await page.locator(".skeleton").count() == 0
                assert await page.locator(".date-chips button").count() == 5
                assert await page.locator(".stock-row").count() == before
                await async_expect(page.locator(".temporal-summary")).to_contain_text("正在更新")
                await async_expect(page.locator(".stock-row")).to_have_count(after)
                await async_expect(page.locator(".react-flow__edge-path")).to_have_count({2:7,4:13}[after])
                await page.wait_for_timeout(200)
                geometry=await page.evaluate(GRAPH_GEOMETRY)
                assert not geometry["outside"] and not geometry["hidden"],geometry
            await page.get_by_label("选择研究案例").select_option("event:glm5-release")
            await async_expect(page.locator(".stock-row")).to_have_count(3)
            await async_expect(page.locator(".react-flow__edge-path")).to_have_count(10)
            await page.wait_for_timeout(500)
            geometry=await page.evaluate(GRAPH_GEOMETRY)
            assert not geometry["outside"] and not geometry["hidden"],geometry
            return {"name":"historical date changes preserve the diagram and date controls during a slow response",
                    "passed":True,"detail":{"response_delay_ms":900,"transitions":[[0,2],[2,4]],"market_dwell_ms":15000,"return_to_original_case":True}}
        finally:
            await browser.close()
            with httpx.Client(base_url=BASE) as client:
                client.post("/api/reset").raise_for_status()


if __name__ == "__main__":
    import asyncio
    report = check()
    if report["passed"]:
        try:
            transition = asyncio.run(check_date_transitions())
            report["checks"].append(transition)
            report["check_count"] = len(report["checks"])
            print("PASS",transition["name"],flush=True)
        except Exception as exc:
            report["passed"] = False
            report["error"] = str(exc)
    write_json(ROOT / "docs" / "results" / "browser_validation.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}, ensure_ascii=False))
    raise SystemExit(0 if report["passed"] else 1)
