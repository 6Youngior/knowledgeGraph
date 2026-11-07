"""FinGraph final demo recording (Playwright + Edge).

The script drives the real, frozen UI at http://127.0.0.1:8000:
research roles -> path evidence -> historical lens -> replay extraction ->
ingest -> focused new stock -> market observation -> DeepSeek temporal build-up.

It only injects a recording caption and a visible pointer into the page DOM.
No product source is modified. It resets the graph before and after recording.

Usage:
    python visualization/record_demo.py
    python visualization/record_demo.py --url http://127.0.0.1:8000

Outputs:
    visualization/FinGraph-demo.webm
    visualization/FinGraph-demo.mp4   (H.264, yuv420p, CRF 18, faststart)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent
WEBM = ROOT / "FinGraph-demo.webm"
MP4 = ROOT / "FinGraph-demo.mp4"
EDGE = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")


def request_json(base: str, path: str, method: str = "GET") -> dict:
    request = urllib.request.Request(base + path, method=method)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def reset_graph(base: str) -> dict:
    return request_json(base, "/api/reset", "POST").get("stats", {})


def caption(page: Page, number: str, title: str, note: str) -> None:
    page.evaluate(
        """([number, title, note]) => {
          let el = document.getElementById('rec-caption');
          if (!el) {
            el = document.createElement('div');
            el.id = 'rec-caption';
            document.body.appendChild(el);
          }
          el.style.cssText = [
            'position:fixed','left:270px','bottom:18px','z-index:2147483000',
            'display:flex','align-items:center','gap:12px',
            'padding:11px 16px','max-width:940px',
            'border:1px solid #dce3ea','border-radius:4px',
            'background:rgba(255,255,255,.97)','pointer-events:none',
            'font-family:Inter,-apple-system,Segoe UI,PingFang SC,Microsoft YaHei,sans-serif',
            'color:#20364b'
          ].join(';');
          el.innerHTML = `
            <span style="flex:none;color:#336a9a;font-size:16px;font-weight:600;">${number}</span>
            <span style="display:flex;flex-direction:column;gap:2px;min-width:0;">
              <b style="font-size:18px;line-height:1.35;font-weight:600;white-space:nowrap;">${title}</b>
              <small style="font-size:14px;line-height:1.45;color:#64748b;white-space:normal;">${note}</small>
            </span>`;
        }""",
        [number, title, note],
    )


def install_pointer(page: Page) -> None:
    page.evaluate(
        """() => {
          const el = document.createElement('div');
          el.id = 'rec-pointer';
          el.style.cssText = [
            'position:fixed','left:0','top:0','z-index:2147483001',
            'width:18px','height:18px','border-radius:50%',
            'border:2px solid rgba(255,255,255,.95)',
            'background:rgba(37,99,235,.34)',
            'box-shadow:0 2px 9px rgba(15,23,42,.45)',
            'transform:translate(-50%,-50%)','pointer-events:none',
            'transition:left .10s linear,top .10s linear'
          ].join(';');
          document.body.appendChild(el);
        }"""
    )


def cursor(page: Page, x: float, y: float) -> None:
    page.mouse.move(x, y, steps=10)
    page.evaluate(
        "([x, y]) => { const el = document.getElementById('rec-pointer'); if (el) { el.style.left = x + 'px'; el.style.top = y + 'px'; } }",
        [x, y],
    )


def move_to(page: Page, selector: str, wait_ms: int = 450) -> None:
    locator = page.locator(selector).first
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box:
        cursor(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(wait_ms)


def click(page: Page, selector: str, wait_ms: int = 650) -> None:
    move_to(page, selector, 500)
    page.locator(selector).first.click()
    page.wait_for_timeout(wait_ms)


def click_text(page: Page, selector: str, text: str, wait_ms: int = 650) -> None:
    locator = page.locator(selector, has_text=text).first
    locator.scroll_into_view_if_needed()
    box = locator.bounding_box()
    if box:
        cursor(page, box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.wait_for_timeout(400)
    locator.click()
    page.wait_for_timeout(wait_ms)


def scroll_to(page: Page, selector: str, offset: int = 90, wait_ms: int = 1200) -> None:
    page.evaluate(
        """([selector, offset]) => {
          const el = document.querySelector(selector);
          if (!el) return;
          const top = el.getBoundingClientRect().top + window.scrollY - offset;
          window.scrollTo({ top, behavior: 'smooth' });
        }""",
        [selector, offset],
    )
    page.wait_for_timeout(wait_ms)


def cleanup_temp(path: Path) -> None:
    target = path.resolve()
    intended_parent = Path(tempfile.gettempdir()).resolve()
    if target.parent != intended_parent or not target.name.startswith("fingraph-final-"):
        raise ValueError("Unexpected temporary recording directory")
    shutil.rmtree(target, ignore_errors=True)


def main() -> int:
    base = "http://127.0.0.1:8000"
    if "--url" in sys.argv:
        base = sys.argv[sys.argv.index("--url") + 1]

    before = reset_graph(base)
    print("reset before:", before, flush=True)

    temp_dir = Path(tempfile.mkdtemp(prefix="fingraph-final-"))
    video_path: Path | None = None
    success = False
    browser = None
    context = None
    console_errors: list[str] = []

    try:
        with sync_playwright() as playwright:
            launch_options = {
                "headless": True,
                "args": ["--force-device-scale-factor=1", "--hide-scrollbars"],
            }
            if EDGE.exists():
                launch_options["executable_path"] = str(EDGE)
            browser = playwright.chromium.launch(**launch_options)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(temp_dir),
                record_video_size={"width": 1920, "height": 1080},
                device_scale_factor=1,
                locale="zh-CN",
                timezone_id="Asia/Shanghai",
            )
            page = context.new_page()
            page.on(
                "console",
                lambda msg: console_errors.append(msg.text)
                if msg.type == "error" and "favicon" not in msg.text
                else None,
            )
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))

            page.goto(base + "/", wait_until="domcontentloaded", timeout=60000)
            page.locator(".research-page").wait_for(timeout=30000)
            page.wait_for_timeout(2600)
            install_pointer(page)
            page.locator(".event-select select").select_option("event:glm5-release")
            page.wait_for_timeout(1700)

            # 01 — problem and roles
            caption(
                page,
                "01",
                "GLM-5 关联公司",
                "初始资料关联智谱与阿里巴巴，分别对应模型研发和云服务接入。",
            )
            # Hold on the event title for about four seconds before moving.
            page.wait_for_timeout(4500)
            move_to(page, ".roles-panel", 700)
            page.wait_for_timeout(6000)

            # 02 — click a stock, read the path and original evidence
            caption(
                page,
                "02",
                "查看原文",
                "选中智谱，查看研发关系、来源及公开日期。",
            )
            move_to(page, ".stock-row", 600)
            click(page, ".stock-row", 1200)
            scroll_to(page, ".research-main", 80, 1200)
            page.wait_for_timeout(4200)
            move_to(page, ".evidence-step", 700)
            page.wait_for_timeout(3700)
            click(page, ".evidence-step .step-meta button", 1000)
            page.wait_for_timeout(4200)
            click(page, ".back-action", 1200)

            # 03 — time lens: excluded and historical
            caption(
                page,
                "03",
                "按日期查询",
                "切换历史日期，检查哪些资料在当时已公开。",
            )
            scroll_to(page, ".temporal-panel", 80, 1100)
            click_text(page, ".lens-tabs button", "其他候选", 1000)
            page.wait_for_timeout(5000)
            click_text(page, ".lens-tabs button", "历史日期", 1200)
            page.wait_for_timeout(4700)
            click_text(page, ".lens-tabs button", "全部资料", 1200)

            # 04 — replay extraction
            caption(
                page,
                "04",
                "导入适配公告",
                "选择摩尔线程的 GLM-5 适配资料，以回放方式预览结果。",
            )
            page.locator(".side-nav button").nth(2).click()
            page.locator(".update-grid").wait_for(timeout=15000)
            page.wait_for_timeout(1500)
            click(page, ".mode-card:nth-child(3)", 1000)
            move_to(page, ".sample-item", 700)
            page.wait_for_timeout(3700)

            # 05 — validation preview
            click(page, ".update-actions .button.primary", 500)
            page.locator(".mode-badge.replay").wait_for(timeout=60000)
            page.wait_for_timeout(1200)
            caption(
                page,
                "05",
                "查看新增内容",
                "新增 1 个适配事件、3 条关系。已有产品、公司和证券继续使用。",
            )
            scroll_to(page, ".preview-metrics", 100, 1300)
            page.wait_for_timeout(5200)
            scroll_to(page, ".ingest-block", 160, 1100)
            move_to(page, ".ingest-block", 700)
            page.wait_for_timeout(3400)

            # 06 — ingest
            click(page, ".ingest-block .button.primary", 500)
            page.locator(".ingested-panel").wait_for(timeout=30000)
            caption(
                page,
                "06",
                "确认入图",
                "保存结果后，返回 GLM-5 查看新增关联。",
            )
            page.wait_for_timeout(5000)

            click(page, ".ingest-actions .button.primary", 700)
            page.locator(".research-page").wait_for(timeout=15000)
            page.wait_for_timeout(2600)

            # 07 — new focused path
            caption(
                page,
                "07",
                "摩尔线程的关联路径",
                "GLM-5 经 MTT S5000 连接摩尔线程及 688795.SH。",
            )
            scroll_to(page, ".research-main", 80, 1300)
            page.wait_for_timeout(5900)

            # 08 — market observation
            caption(
                page,
                "08",
                "查看行情",
                "比较股票与基准的同窗口累计收益。",
            )
            scroll_to(page, ".research-bottom", 80, 1300)
            move_to(page, ".market-panel", 700)
            page.wait_for_timeout(7400)

            # 09 — real research brief download
            # Hide only the transient toast layer, not any research content.
            page.add_style_tag(content=".toast-stack{display:none !important;}")
            caption(
                page,
                "09",
                "导出研究简报",
                "简报保存关联公司、关系原文、来源链接和行情。",
            )
            with page.expect_download(timeout=30000) as download_info:
                click(page, ".brief-button", 400)
            download = download_info.value
            brief_path = temp_dir / "research-brief.md"
            download.save_as(str(brief_path))
            print(f"brief: {brief_path} ({brief_path.stat().st_size:,} bytes)", flush=True)
            page.wait_for_timeout(6500)

            # 10 — DeepSeek temporal accumulation
            caption(
                page,
                "10",
                "DeepSeek-R1 历史查询",
                "切换研究事件，按不同截止日期查看关联公司。",
            )
            page.locator(".event-select select").select_option("event:deepseek-r1-release")
            page.wait_for_timeout(1900)
            scroll_to(page, ".temporal-panel", 80, 1200)
            click_text(page, ".lens-tabs button", "历史日期", 1200)
            caption(
                page,
                "10",
                "2025-01-20：0 只",
                "已收集资料在发布日尚未形成完整的证券路径。",
            )
            page.wait_for_timeout(5600)
            click_text(page, ".date-chips button", "2025-02-03", 1300)
            caption(
                page,
                "10",
                "2025-02-03：2 只",
                "腾讯与百度的云接入资料已公开。",
            )
            page.wait_for_timeout(5600)
            click_text(page, ".date-chips button", "2025-02-05", 1300)
            caption(
                page,
                "10",
                "2025-02-05：4 只",
                "加入海光适配及中国电信云接入的资料。",
            )
            page.wait_for_timeout(6000)

            # 11 — close
            click_text(page, ".lens-tabs button", "全部资料", 1100)
            caption(
                page,
                "11",
                "DeepSeek-R1：全部资料",
                "当前关联腾讯、百度、海光和中国电信。",
            )
            window = page.evaluate(
                """() => {
                  const el = document.querySelector('.research-heading h1');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                  return el ? el.textContent : '';
                }"""
            )
            page.wait_for_timeout(7000)
            print("final heading:", window, flush=True)

            video = page.video
            context.close()
            context = None
            browser.close()
            browser = None
            video_path = Path(video.path())
            success = True
    except Exception as exc:  # noqa: BLE001
        print(f"recording failed: {exc}", file=sys.stderr, flush=True)
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
    finally:
        after = reset_graph(base)
        print("reset after:", after, flush=True)
        if before and after and any(after.get(k) != v for k, v in before.items()):
            print("warning: stats not restored to initial snapshot", before, after, file=sys.stderr)

    if not success or video_path is None or not video_path.exists():
        print("no video produced", file=sys.stderr)
        cleanup_temp(temp_dir)
        return 1

    shutil.move(str(video_path), str(WEBM))
    cleanup_temp(temp_dir)
    print(f"webm: {WEBM} ({WEBM.stat().st_size:,} bytes)", flush=True)

    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("ffmpeg not found; keeping webm only", file=sys.stderr)
        return 1
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(WEBM),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(MP4),
        ],
        check=True,
    )
    print(f"mp4: {MP4} ({MP4.stat().st_size:,} bytes)", flush=True)

    probe = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(MP4)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", probe.stderr)
    if match:
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        print(f"duration: {duration:.1f}s", flush=True)
        if duration < 100 or duration > 210:
            print("warning: target is about 2–3 minutes", file=sys.stderr)
    print("console errors:", console_errors[:5], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
