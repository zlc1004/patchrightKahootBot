import asyncio
import json
import sys
from patchright.async_api import async_playwright


STEALTH_SCRIPT = """const defaultGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;defaultGetter.apply(navigator),defaultGetter.toString(),Object.defineProperty(Navigator.prototype,"webdriver",{set:void 0,enumerable:!0,configurable:!0,get:new Proxy(defaultGetter,{apply:(e,t,r)=>(Reflect.apply(e,t,r),!1)})});const patchedGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;patchedGetter.apply(navigator),patchedGetter.toString();"""


async def capture_auth_state():
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=False,
        args=[
            "--no-sandbox",
            "--disable-infobars",
            "--disable-extensions",
            "--disable-blink-features=AutomationControlled",
        ],
    )

    context = await browser.new_context()
    page = await context.new_page()
    await page.add_init_script(script=STEALTH_SCRIPT)

    print("\n" + "=" * 50, file=sys.stderr)
    print("Browser opened! Manually login in the browser window.", file=sys.stderr)
    print("When done, come back to this terminal and press ENTER.", file=sys.stderr)
    print("=" * 50 + "\n", file=sys.stderr)

    input()

    print("\nSaving authentication state...", file=sys.stderr)

    state = await context.storage_state()

    await browser.close()
    await p.stop()

    state_json = json.dumps(state, indent=2)

    print(state_json)


def main():
    try:
        asyncio.run(capture_auth_state())
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
