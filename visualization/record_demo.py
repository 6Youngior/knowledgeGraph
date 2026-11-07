"""Record the real research workflow using Playwright and Edge.

The recording adds a subtitle strip and a pointer. It uses the visible replay
option for extraction, and restores the initial graph before and after use.
Requires the running service, Playwright, Edge and ffmpeg.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import Page, expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "visualization"
REVIEW = ROOT / "docs" / "tasks" / "demo_redesign"
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def reset(base: str) -> dict:
    request = urllib.request.Request(base + "/api/reset", method="POST")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["stats"]


def subtitle(page: Page, chapter: str, note: str) -> None:
    page.evaluate("""([chapter, note]) => {
      let band = document.getElementById('record-subtitle');
      if (!band) {
        band = document.createElement('div'); band.id = 'record-subtitle';
        band.innerHTML = '<span></span><p></p>';
        document.body.appendChild(band);
      }
      band.querySelector('span').textContent = chapter;
      band.querySelector('p').textContent = note;
    }""", [chapter, note])


def install_recording_ui(page: Page) -> None:
    page.add_style_tag(content="""
      body.recording .research-main { height: calc(100dvh - 420px); min-height: 500px; }
      body.recording .update-input, body.recording .update-result { height: calc(100dvh - 300px); }
      body.recording .toast-stack { bottom: 88px; }
      #record-subtitle {
        position:fixed; z-index:2000; inset:auto 0 0; height:72px;
        display:flex; align-items:center; gap:26px; padding:0 32px;
        background:#fff; border-top:1px solid #cbd5df; color:#253b50;
        font-family:"Segoe UI","Microsoft YaHei",sans-serif; pointer-events:none;
      }
      #record-subtitle > span { flex:none; font-size:19px; font-weight:600; }
      #record-subtitle > p { margin:0; padding-left:26px; border-left:1px solid #cbd5df; font-size:21px; line-height:1.5; font-weight:400; }
      #record-pointer { position:fixed; z-index:2100; pointer-events:none; display:none; width:21px; height:26px; left:0; top:0; }
    """)
    page.evaluate("""() => {
      document.body.classList.add('recording');
      const pointer = document.createElement('div'); pointer.id='record-pointer';
      pointer.innerHTML='<svg width="21" height="26" viewBox="0 0 21 26"><path d="M2 2V21L7.5 16.5L11 24L14 22.5L10.5 15H18Z" fill="#244e73" stroke="white" stroke-width="1.5" stroke-linejoin="round"/></svg>';
      document.body.appendChild(pointer);
      document.addEventListener('mousemove', event => {
        pointer.style.display='block'; pointer.style.left=event.clientX+'px'; pointer.style.top=event.clientY+'px';
      });
    }""")


def click(page: Page, locator, pause: int = 500) -> None:
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=22)
    page.wait_for_timeout(350)
    locator.click()
    page.wait_for_timeout(pause)


def park(page: Page) -> None:
    page.mouse.move(196, 160, steps=18)


def assert_graph_fits(page: Page) -> None:
    page.wait_for_timeout(200)
    counts=re.findall(r"\d+",page.locator(".graph-count").inner_text())
    expect(page.locator(".react-flow__edge-path")).to_have_count(int(counts[-1]))
    outside=page.evaluate("""() => {
        const area=document.querySelector('.research-graph-canvas').getBoundingClientRect();
        return [...document.querySelectorAll('.react-flow__node')].filter(el=>{
            const r=el.getBoundingClientRect();
            return getComputedStyle(el).visibility==='hidden'||r.x<area.x-2||r.y<area.y-2||r.right>area.right+2||r.bottom>area.bottom+2;
        }).map(el=>el.dataset.id);
    }""")
    assert not outside, outside


def main() -> int:
    base = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else "http://127.0.0.1:8000"
    REVIEW.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix="fingraph-record-")).resolve()
    before = reset(base)
    errors: list[str] = []
    chapters: list[dict] = []
    browser = context = None
    video = None
    trim = 0.0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(EDGE), args=["--hide-scrollbars", "--force-device-scale-factor=1"])
            context = browser.new_context(
                viewport={"width":1920,"height":1080}, record_video_dir=str(temp),
                record_video_size={"width":1920,"height":1080}, device_scale_factor=1,
                locale="zh-CN", timezone_id="Asia/Shanghai", accept_downloads=True,
            )
            epoch = time.monotonic()
            page = context.new_page()
            page.set_default_timeout(20000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base, wait_until="networkidle")
            page.get_by_label("选择研究案例").select_option("event:glm5-release")
            expect(page.locator(".stock-row")).to_have_count(2)
            expect(page.locator(".react-flow__node")).to_have_count(7)
            install_recording_ui(page)
            subtitle(page, "01  关联查询", "GLM-5 发布后，哪些上市公司有明确的关系记录？")
            page.wait_for_timeout(1800)
            assert_graph_fits(page)
            page.screenshot(path=str(REVIEW / "opening-reference.png"))
            # The first browser frames may precede viewport setup. Keep only
            # the stable opening, with an extra second of timing margin.
            trim = time.monotonic() - epoch + 1.0
            page.wait_for_timeout(8000)
            def mark(title: str) -> None:
                chapters.append({"seconds": round(max(0,time.monotonic()-epoch-trim),2), "title":title})
                print(title, flush=True)
            mark("关联证券与研发原文")
            click(page, page.locator('.stock-row[data-symbol="02513.HK"]'))
            subtitle(page, "01  关联查询", "智谱是研发主体。右侧逐条列出模型、公司、证券之间的关系与原文。")
            park(page);page.wait_for_timeout(6500)
            click(page, page.locator(".evidence-step .step-meta button").nth(1))
            expect(page.locator(".evidence-card")).to_contain_text("研发主体")
            park(page);page.wait_for_timeout(6500)
            click(page, page.locator(".back-action"))
            click(page, page.locator('.stock-row[data-symbol="09988.HK"]'))
            subtitle(page, "01  关联查询", "阿里巴巴经百炼云服务接入 GLM-5，产业角色与模型研发不同。")
            park(page);page.wait_for_timeout(5000)

            mark("导入适配公告")
            click(page, page.get_by_role("button", name="导入资料", exact=True))
            expect(page.locator(".sample-picker")).to_be_visible()
            subtitle(page, "02  资料入图", "这篇适配公告提到 MTT S5000 和 GLM-5，没有证券代码。")
            park(page);page.wait_for_timeout(8500)
            click(page, page.locator(".mode-card").nth(2))
            subtitle(page, "02  资料入图", "选择样例回放，读取已保存的模型抽取结果，再核对候选关系。")
            park(page);page.wait_for_timeout(2500)
            click(page, page.get_by_role("button", name="抽取关系", exact=True))
            expect(page.locator(".validation.ok")).to_be_visible()
            expect(page.locator(".result-summary")).to_contain_text("3")
            park(page);page.wait_for_timeout(6500)
            click(page, page.locator(".alignment-details summary"))
            subtitle(page, "02  资料入图", "产品和模型对齐到已有实体；本次增加 1 个适配事件、3 条关系。")
            park(page);page.wait_for_timeout(4500)
            click(page, page.locator(".alignment-details summary"))
            click(page, page.get_by_role("button", name="确认入图", exact=True))
            expect(page.locator(".ingest-success")).to_contain_text("已写入图谱")
            park(page);page.wait_for_timeout(3500)
            click(page, page.get_by_role("button", name="查看新增证券", exact=True))
            expect(page.locator(".stock-row")).to_have_count(3)
            expect(page.locator(".path-heading")).to_contain_text("摩尔线程")
            assert_graph_fits(page)
            subtitle(page, "02  资料入图", "关联证券由 2 只变为 3 只，新增摩尔线程（688795.SH）。")
            park(page);page.wait_for_timeout(8500)
            click(page, page.locator(".evidence-step .step-meta button").nth(1))
            expect(page.locator(".edge-statement")).to_contain_text("MTT S5000")
            expect(page.locator(".quote")).to_contain_text("适配")
            park(page);page.wait_for_timeout(5000)
            click(page, page.locator(".back-action"))

            mark("行情对照与简报")
            click(page, page.locator('.stock-row[data-symbol="02513.HK"]'))
            click(page, page.get_by_role("tab", name="行情对照", exact=True))
            expect(page.locator(".return-table")).to_contain_text("+56.22%")
            subtitle(page, "03  行情与简报", "选中智谱，对照恒生指数的同窗口走势；行情结果作描述性比较。")
            park(page);page.wait_for_timeout(8500)
            with page.expect_download() as info:
                click(page, page.get_by_role("button", name="导出简报", exact=True))
            info.value.save_as(str(temp / "research-brief.md"))
            brief = (temp / "research-brief.md").read_text(encoding="utf-8-sig")
            assert "688795.SH" in brief and "https://" in brief
            subtitle(page, "03  行情与简报", "导出的简报包含关联证券、关系路径、原文链接和行情结果。")
            park(page);page.wait_for_timeout(5000)

            mark("按历史日期查看资料")
            subtitle(page, "04  历史资料", "切换到 DeepSeek-R1，按当时已公开的资料查看关联变化。")
            page.get_by_label("选择研究案例").select_option("event:deepseek-r1-release")
            expect(page.locator(".stock-row")).to_have_count(4)
            click(page, page.get_by_role("button", name="历史日期", exact=True))
            expect(page.locator(".stock-row")).to_have_count(0)
            assert_graph_fits(page)
            subtitle(page, "04  历史资料", "2025-01-20：本次已收集资料在发布日还没有形成完整的证券路径。")
            park(page);page.wait_for_timeout(5000)
            subtitle(page, "04  历史资料", "查询截至 2025-02-03 已公开的资料。")
            click(page, page.locator(".date-chips button").filter(has_text="2025-02-03"))
            expect(page.locator(".stock-row")).to_have_count(2)
            assert_graph_fits(page)
            subtitle(page, "04  历史资料", "截至 2025-02-03，腾讯与百度的云接入资料支持 2 只证券的关联。")
            park(page);page.wait_for_timeout(5500)
            subtitle(page, "04  历史资料", "查询截至 2025-02-05 已公开的资料。")
            click(page, page.locator(".date-chips button").filter(has_text="2025-02-05"))
            expect(page.locator(".stock-row")).to_have_count(4)
            assert_graph_fits(page)
            subtitle(page, "04  历史资料", "截至 2025-02-05，再加入海光适配与中国电信云接入，累计 4 只证券。")
            park(page);page.wait_for_timeout(6000)
            page.get_by_label("选择研究案例").select_option("event:glm5-release")
            expect(page.locator(".stock-row")).to_have_count(3)
            assert_graph_fits(page)
            subtitle(page, "FinGraph", "公告入图后，GLM-5 新增摩尔线程的证券路径；每条关系仍可查看原文。")
            park(page);page.wait_for_timeout(6500)
            assert not errors, errors
            video = page.video
            context.close();context=None
            assert video is not None
            raw = Path(video.path())
            browser.close();browser=None
        ffmpeg = shutil.which("ffmpeg")
        assert ffmpeg, "ffmpeg is required"
        webm = OUT / "FinGraph-demo.webm"
        mp4 = OUT / "FinGraph-demo.mp4"
        # Both formats start on the same complete, verified product frame.
        subprocess.run([ffmpeg,"-y","-v","error","-ss",str(trim),"-i",str(raw),"-c:v","libvpx-vp9","-crf","26","-b:v","0","-deadline","realtime","-cpu-used","6","-row-mt","1","-an",str(webm)],check=True)
        print("WebM encoded",flush=True)
        subprocess.run([ffmpeg,"-y","-v","error","-ss",str(trim),"-i",str(raw),"-c:v","libx264","-preset","slow","-crf","18","-pix_fmt","yuv420p","-movflags","+faststart","-an",str(mp4)],check=True)
        cover = OUT / "FinGraph-demo-cover.png"
        subprocess.run([ffmpeg,"-y","-v","error","-i",str(mp4),"-frames:v","1",str(cover)],check=True)
        expected=Image.open(REVIEW/"opening-reference.png").convert("RGB")
        actual=Image.open(cover).convert("RGB")
        assert actual.size == expected.size == (1920,1080)
        difference=sum(ImageStat.Stat(ImageChops.difference(expected,actual)).mean)/3
        assert difference < 8, "Opening frame does not match the stable product page"
        probe=json.loads(subprocess.check_output([shutil.which("ffprobe"),"-v","error","-show_format","-show_streams","-of","json",str(mp4)],text=True))
        duration=float(probe["format"]["duration"])
        assert 120 <= duration <= 180, duration
        report={"created_at":datetime.now(timezone.utc).isoformat(),"duration_seconds":duration,"trimmed_warmup_seconds":round(trim,3),
                "opening_frame_mean_error":round(difference,3),"opening_frame_matches_ready_ui":True,
                "chapters":chapters,"page_errors":errors,"mp4_sha256":hashlib.sha256(mp4.read_bytes()).hexdigest()}
        (REVIEW/"recording.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False),flush=True)
        return 0
    finally:
        for item in (context, browser):
            if item:
                try:
                    item.close()
                except Exception:
                    pass
        after=reset(base)
        assert before == after, (before,after)
        intended_parent=Path(tempfile.gettempdir()).resolve()
        if temp.parent != intended_parent or not temp.name.startswith("fingraph-record-"):
            raise ValueError("Unexpected temporary recording directory")
        shutil.rmtree(temp)


if __name__ == "__main__":
    raise SystemExit(main())
