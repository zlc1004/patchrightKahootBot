
import random
import string
import asyncio
from patchright.async_api import async_playwright

from config import Kahoot as config

def generate_hex_string(length):
    return ''.join(random.choices(string.hexdigits, k=length)).lower()

async def run_client(join_code, browser):
    try:
        page = await browser.new_page()
        await page.goto("https://kahoot.it")

        await page.wait_for_selector(f"xpath={config.code_input_xpath}", timeout=60000)
        await page.locator(f"xpath={config.code_input_xpath}").fill(join_code)
        await page.wait_for_timeout(500)

        await page.locator(config.submit_code_button_selector).click()
        await page.wait_for_timeout(500)

        await page.wait_for_selector(f"xpath={config.nickname_input_xpath}")

        random_hex_1 = generate_hex_string(5)
        random_hex_2 = generate_hex_string(5)
        text_to_type = f"{random_hex_1} {random_hex_2}"

        await page.locator(f"xpath={config.nickname_input_xpath}").fill(text_to_type)
        await page.wait_for_timeout(500)

        await page.locator(config.submit_nickname_button_selector).click()
        await page.wait_for_timeout(500)
    except Exception as e:
        print(f"An error occurred in a client: {e}")
        # Optionally close the page if an error occurs to free up resources
        if 'page' in locals() and not page.is_closed():
            await page.close()

async def main():
    join_code = input("Please enter the code to join: ")
    num_clients_str = input("Please enter the number of clients to run: ")
    try:
        num_clients = int(num_clients_str)
    except ValueError:
        print("Invalid number of clients. Please enter an integer.")
        return

    if num_clients <= 0:
        print("Number of clients must be greater than 0.")
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False) # Launch browser once

        tasks = []
        for i in range(num_clients):
            # No delay here, as browser.new_page() is fast, and the navigation/interactions have delays
            tasks.append(asyncio.create_task(run_client(join_code, browser)))

        await asyncio.gather(*tasks)
        
        input(f"All {num_clients} tabs launched in a single browser. Press Enter to close the script (browser will remain open until manually closed).")
        # Keep the browser open until the user manually closes it
        # await browser.close() # Commented out to keep browser open

if __name__ == "__main__":
    asyncio.run(main())
