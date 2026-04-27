"""
Option 1: Playwright-based Streamlit uptime monitor.
Wakes hibernated apps by waiting for the React shell to load, 
detecting the sleep screen, and clicking the Wake up button.
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
PAGE_TIMEOUT_MS  =  60_000   
POLL_INTERVAL_MS =   2_000   
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s", datefmt="%Y-%m-%dT%H:%M:%SZ")
log = logging.getLogger("uptime_monitor")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

async def check_and_wake() -> bool:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Using a standard user agent to avoid bot detection
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        page = await context.new_page()
        page.set_default_timeout(PAGE_TIMEOUT_MS)

        try:
            log.info("Navigating to %s", APP_URL)
            # Wait until the network is idle, not just when the DOM loads
            await page.goto(APP_URL, wait_until="networkidle")
            
            log.info("Waiting 10 seconds for Streamlit's React app to evaluate server status...")
            await asyncio.sleep(10)
            
            body_text = await page.inner_text("body")
            
            # Case-insensitive partial matching
            if "gone to sleep" in body_text.lower() or "get this app back up" in body_text.lower():
                log.info("Hibernation screen detected!")
                
                # Look for a button containing the text
                locator = page.locator("button:has-text('get this app back up')")
                
                if await locator.count() == 0:
                    # Fallback locator if Streamlit removes the strict <button> tag
                    locator = page.locator("text=/get this app back up/i").first
                
                if await locator.count():
                    log.info("Clicking the Wake-up button...")
                    await locator.click()
                else:
                    log.warning("Could not find the clickable element. Reloading page.")
                    await page.reload(wait_until="networkidle")

                log.info("Waiting for app to wake (this can take 1-2 minutes)...")
                deadline = asyncio.get_event_loop().time() + WAKE_TIMEOUT_MS / 1000
                while asyncio.get_event_loop().time() < deadline:
                    await asyncio.sleep(POLL_INTERVAL_MS / 1000)
                    current_text = await page.inner_text("body")
                    if "gone to sleep" not in current_text.lower() and "get this app back up" not in current_text.lower():
                        log.info("✅  App is now awake!  [%s]", _now())
                        return True
                        
                log.error("❌  App did not wake within the timeout window.")
                return False
            else:
                log.info("App appears to be awake already. Refreshing to reset timer.")
                await page.reload(wait_until="networkidle")
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
