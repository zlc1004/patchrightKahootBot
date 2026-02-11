import asyncio
import json
import sys
from patchright.async_api import async_playwright


STEALTH_SCRIPT = """const defaultGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;defaultGetter.apply(navigator),defaultGetter.toString(),Object.defineProperty(Navigator.prototype,"webdriver",{set:void 0,enumerable:!0,configurable:!0,get:new Proxy(defaultGetter,{apply:(e,t,r)=>(Reflect.apply(e,t,r),!1)})});const patchedGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;patchedGetter.apply(navigator),patchedGetter.toString();"""


async def load_auth_state(state_path: str):
    with open(state_path, "r") as f:
        state = json.load(f)

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

    context = await browser.new_context(storage_state=state)
    page = await context.new_page()
    await page.add_init_script(script=STEALTH_SCRIPT)

    print("\n" + "=" * 50, file=sys.stderr)
    print("Browser opened with saved state!", file=sys.stderr)
    print("When done, come back to this terminal and press ENTER.", file=sys.stderr)
    print("=" * 50 + "\n", file=sys.stderr)

    input()

    print("\nClosing browser...", file=sys.stderr)

    await context.close()
    await browser.close()
    await p.stop()

    print("Done.", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print("Usage: python auth_test.py <path_to_state_json>", file=sys.stderr)
        sys.exit(1)

    state_path = sys.argv[1]

    try:
        asyncio.run(load_auth_state(state_path))
    except FileNotFoundError:
        print(f"Error: File not found: {state_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in: {state_path}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nCancelled by user.", file=sys.stderr)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
