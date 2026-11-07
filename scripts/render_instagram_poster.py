#!/usr/bin/env python3
"""Render Swarnam4U Instagram posters; --preview renders all ten with a visible watermark."""
from __future__ import annotations
import asyncio
import base64
import pathlib
import sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "output" / "instagram"
OUT.mkdir(parents=True, exist_ok=True)

async def main() -> None:
    preview = "--preview" in sys.argv
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 1800}, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        if preview:
            for design in range(1, 11):
                url = f"http://127.0.0.1:8765/instagram-poster.html?preview=1&design={design}"
                await page.goto(url, wait_until="networkidle", timeout=90000)
                await page.wait_for_function(
                    """() => { const c=document.querySelector('#poster'); const s=document.querySelector('#pStatus'); return c && !c.hidden && c.width>0 && s && /PREVIEW ONLY/.test(s.textContent); }""",
                    timeout=90000,
                )
                status = await page.locator("#pStatus").inner_text()
                canvas = page.locator("#poster")
                size = await canvas.evaluate("(c) => ({w:c.width,h:c.height})")
                if size["w"] < 900 or size["h"] < 1300:
                    raise RuntimeError(f"Unexpected poster dimensions for design {design}: {size}")
                target = OUT / f"preview-design-{design:02d}.png"
                png = await canvas.evaluate("c => c.toDataURL('image/png').split(',')[1]")
                target.write_bytes(base64.b64decode(png))
                print(f"PREVIEW_FILE={target} SIZE={size['w']}x{size['h']} STATUS={status}")
        else:
            await page.goto("http://127.0.0.1:8765/instagram-poster.html", wait_until="networkidle", timeout=90000)
            await page.wait_for_function(
                """() => { const c=document.querySelector('#poster'); const s=document.querySelector('#pStatus'); return c && !c.hidden && c.width>0 && s && /Poster updated automatically/.test(s.textContent); }""",
                timeout=90000,
            )
            status = await page.locator("#pStatus").inner_text()
            if "older than 24 hours" in status or "LAST UPDATED" in status:
                raise RuntimeError("Poster rates are stale; refusing to create an Instagram post.")
            canvas = page.locator("#poster")
            size = await canvas.evaluate("(c) => ({w:c.width,h:c.height})")
            if size["w"] < 900 or size["h"] < 1300:
                raise RuntimeError(f"Unexpected poster dimensions: {size}")
            date = await page.evaluate("new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date())")
            target = OUT / f"swarnam4u-rates-{date}.png"
            png = await canvas.evaluate("c => c.toDataURL('image/png').split(',')[1]")
            target.write_bytes(base64.b64decode(png))
            print(f"POSTER_FILE={target}")
            print(f"POSTER_SIZE={size['w']}x{size['h']}")
            print(f"POSTER_STATUS={status}")

        if errors:
            print("Browser page errors:", errors, file=sys.stderr)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
