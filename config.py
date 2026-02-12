STEALTH_SCRIPT = """const defaultGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;defaultGetter.apply(navigator),defaultGetter.toString(),Object.defineProperty(Navigator.prototype,"webdriver",{set:void 0,enumerable:!0,configurable:!0,get:new Proxy(defaultGetter,{apply:(e,t,r)=>(Reflect.apply(e,t,r),!1)})});const patchedGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;patchedGetter.apply(navigator),patchedGetter.toString();"""

class BaseGameConfig:
    uri: str = ""
    code_input_xpath: str = ""
    submit_code_button_selector: str = ""
    nickname_input_xpath: str = ""
    submit_nickname_button_selector: str = ""
    require_secondary_code: bool = False
    secondary_code_input_xpath: str = ""
    secondary_code_submit_button_selector: str = ""
    excute_additional_js: bool = False
    excute_additional_js_wait_xpath: str = ""
    excute_additional_js_code: str = ""
    use_custom_run_client: bool = False
    custom_run_client_custom_kargs: list[dict] = []

    @classmethod
    async def run_client(cls, code, browser, **kargs):
        pass


class Kahoot(BaseGameConfig):
    uri = "https://kahoot.it"
    code_input_xpath = '//*[@id="game-input"]'
    submit_code_button_selector = "xpath=/html/body/div/div[1]/div/div/div[1]/div/div[2]/div[2]/main/div/form/button"
    nickname_input_xpath = '//*[@id="nickname"]'
    submit_nickname_button_selector = (
        "xpath=/html/body/div/div[1]/div/div/div[1]/div/div[2]/main/div/form/button"
    )


class MyShortAnswer(BaseGameConfig):
    uri = "https://app.myshortanswer.com/join"
    code_input_xpath = '//*[@id=":r1:"]'
    submit_code_button_selector = "xpath=/html/body/div/div/div/form/button"
    nickname_input_xpath = '//*[@id="text-input-go-input"]'
    submit_nickname_button_selector = "xpath=/html/body/div/form/div/div/div/button"


class Blooket(BaseGameConfig):
    uri = "https://play.blooket.com/play"
    code_input_xpath = "/html/body/main/div/form/div[1]/div/div/input"
    submit_code_button_selector = "xpath=/html/body/main/div/form/div[1]/div/button"
    nickname_input_xpath = "/html/body/div/div/div/div[2]/div/form/div[2]/div[1]/input"
    submit_nickname_button_selector = (
        "xpath=/html/body/div/div/div/div[2]/div/form/div[2]/div[2]"
    )


class MagicSchoolAI(BaseGameConfig):
    uri = "https://student.magicschool.ai/s/join"
    code_input_xpath = '//*[@id="field2"]'
    submit_code_button_selector = 'xpath=//*[@id="field1"]'
    nickname_input_xpath = '//*[@id="field1"]'
    submit_nickname_button_selector = "xpath=/html/body/div[2]/div/button"


class GoogleForms(BaseGameConfig):
    uri = ""
    use_custom_run_client = True
    custom_run_client_custom_kargs = [
        {"prompt": "Enter Google Forms URL: ", "key": "form_url"},
    ]

    @classmethod
    async def run_client(cls, code, browser, **kwargs):
        import random
        import string
        import asyncio

        form_url = kwargs.get("form_url", code)
        if not form_url.startswith("http"):
            form_url = "https://" + form_url

        def generate_random_text(min_len=5, max_len=50):
            length = random.randint(min_len, max_len)
            return "".join(
                random.choices(string.ascii_letters + string.digits + " ", k=length)
            )

        page = None
        try:
            page = await browser.new_page()
            page.add_init_script(script=STEALTH_SCRIPT)
            page = await browser.new_page()
            await page.goto(form_url)
            await page.wait_for_load_state("networkidle")

            radio_groups = page.locator("div[role='radiogroup']")
            count = await radio_groups.count()

            for i in range(count):
                group = radio_groups.nth(i)
                try:
                    options = group.locator("div.Od2TWd[data-value]")
                    opt_count = await options.count()
                    if opt_count > 0:
                        rand_idx = random.randint(0, opt_count - 1)
                        await options.nth(rand_idx).click()
                        await asyncio.sleep(0.05)
                except:
                    pass

            textareas = page.locator("textarea.KHxj8b")
            txt_count = await textareas.count()
            for i in range(txt_count):
                try:
                    textarea = textareas.nth(i)
                    await textarea.fill(generate_random_text())
                    await asyncio.sleep(0.05)
                except:
                    pass

            checkboxes = page.locator("div[role='checkbox']")
            cb_count = await checkboxes.count()
            for i in range(cb_count):
                try:
                    cb = checkboxes.nth(i)
                    is_checked = await cb.get_attribute("aria-checked")
                    if is_checked == "false" and random.random() > 0.3:
                        await cb.click()
                        await asyncio.sleep(0.05)
                except:
                    pass

            await asyncio.sleep(0.5)

            submit_btn = page.locator("div[jsname='M2UYVd'][role='button']").first
            if await submit_btn.count() > 0:
                await submit_btn.click()

            await asyncio.sleep(1)
            print(f"Form submitted")

        except Exception as e:
            print(f"Error: {e}")
            if page and not page.is_closed():
                await page.close()


supported_games = {
    "kahoot": Kahoot,
    "myshortanswer": MyShortAnswer,
    "blooket": Blooket,
    "magicschoolai": MagicSchoolAI,
    "googleforms": GoogleForms,
}
