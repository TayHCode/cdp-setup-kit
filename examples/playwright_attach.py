"""Documentation example; Playwright is installed separately by the reader."""
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.connect_over_cdp("http://127.0.0.1:9333")
    try:
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://example.com")
        print(page.title())
    finally:
        # For an attached browser, this disconnects and leaves the window open.
        browser.close()
