"""
Option 1: Playwright-based Streamlit uptime monitor.
Wakes hibernated apps by detecting and clicking the 'Wake up' button,
or refreshes the page if the app is already running.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# ── Configuration ─────────────────────────────────────────────────────────────
APP_URL = os.environ.get("APP_URL", "https://your-app.streamlit.app")
WAKE_TIMEOUT_MS  = 120_000   
PAGE_TIMEOUT_MS  =  30_000   
POLL_INTERVAL_MS =   2_000   

# Updated to match Streamlit's new hibernation screen text
HIBERNATION_TEXT   = "gone to sleep"
WAKE_BUTTON_TEXT   = "Yes, get this app back up"          
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
log = logging.getLogger("uptime_monitor")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

async def check_and_wake() -> bool:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            log.info("Navigating to %s", APP_URL)
            await page.goto(APP_URL, wait_until="domcontentloaded")
            body_text = await page.inner_text("body")

            if HIBERNATION_TEXT in body_text or WAKE_BUTTON_TEXT in body_text:
                log.info("Hibernation screen detected — looking for Wake-up button.")
                
                # Relaxed the locator to find the button even if there are extra characters
                locator = page.locator(f"text={WAKE_BUTTON_TEXT}")
                
                if await locator.count():
                    log.info("Clicking '%s' button.", WAKE_BUTTON_TEXT)
                    await locator.first.click()
                else:
                    log.warning("Wake-up button not found. Reloading page.")
                    await page.reload(wait_until="domcontentloaded")

                log.info("Waiting for app to wake...")
                deadline = asyncio.get_event_loop().time() + WAKE_TIMEOUT_MS / 1000
                while asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(POLL_INTERVAL_MS / 1000)
                    current_text = await page.inner_text("body")
                    if HIBERNATION_TEXT not in current_text and WAKE_BUTTON_TEXT not in current_text:
                        log.info("✅  App is now awake!  [%s]", _now())
                        return True
                log.error("❌  App did not wake within the timeout window.")
                return False
            else:
                log.info("App is already awake. Refreshing to reset hibernation timer.")
                await page.reload(wait_until="domcontentloaded")
                log.info("✅  Refresh complete.  [%s]", _now())
                return True

        except PlaywrightTimeoutError as exc:
            log.error("Playwright timeout: %s", exc)
            return False
        except Exception as exc: 
            log.error("Unexpected error: %s", exc, exc_info=True)
            return False
        finally:
            await browser.close()

if __name__ == "__main__":
    success = asyncio.run(check_and_wake())
    sys.exit(0 if success else 1)
