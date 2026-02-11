class BaseGameConfig:
    uri: str = ""  # The base URI for the game
    code_input_xpath: str = ""  # The XPath for the game code input field
    submit_code_button_selector: str = ""  # The selector for the submit code button
    nickname_input_xpath: str = ""  # The XPath for the nickname input field
    submit_nickname_button_selector: str = (
        ""  # The selector for the submit nickname button
    )
    require_secondary_code: bool = False  # Whether a secondary code is required
    secondary_code_input_xpath: str = ""  # The XPath for the secondary code input field
    secondary_code_submit_button_selector: str = (
        ""  # The selector for the secondary code submit button
    )
    excute_additional_js: bool = (
        False  # Whether to execute additional JavaScript after joining
    )
    excute_additional_js_wait_xpath: str = (
        ""  # The XPath to wait to be visible for before executing additional JS
    )
    excute_additional_js_code: str = (
        ""  # Additional JavaScript to execute after joining
    )
    use_custom_run_client: bool = False
    custom_run_client_custom_kargs: list[
        dict
    ] = []  # [{"prompt": "prompt to ask user when running", "key": "key"},...]

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
        {"prompt": "Enter cookies JSON (part 1/2): ", "key": "cookies1"},
        {"prompt": "Enter cookies JSON (part 2/2): ", "key": "cookies2"},
    ]

    @classmethod
    async def run_client(cls, code, browser, **kwargs):
        import random
        import string
        import asyncio
        import json

        form_url = kwargs.get("form_url", code)
        if not form_url.startswith("http"):
            form_url = "https://" + form_url

        c1 = kwargs.get("cookies1", "")
        c2 = kwargs.get("cookies2", "")
        combined = (c1 + c2).strip()
        cookies = cls._parse_cookies(combined, json)

        def generate_random_text(min_len=5, max_len=50):
            length = random.randint(min_len, max_len)
            return "".join(
                random.choices(string.ascii_letters + string.digits + " ", k=length)
            )

        page = None
        try:
            page = await browser.new_page()
            if cookies:
                try:
                    await page.context.add_cookies(cookies)
                except Exception:
                    pass
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

    @staticmethod
    def _parse_cookies(cookie_data, json_module=None):
        if (
            not cookie_data
            or cookie_data.strip().lower() == "none"
            or cookie_data.strip() == "[]"
        ):
            return None
        try:
            if json_module is None:
                import json

                json_module = json
            raw = json_module.loads(cookie_data)
            if not raw:
                return None
            cookies = []
            for c in raw:
                if isinstance(c, dict):
                    cookie = {
                        "name": c.get("n") or c.get("name", ""),
                        "value": c.get("v") or c.get("value", ""),
                        "domain": c.get("d") or c.get("domain", ""),
                        "path": c.get("p") or c.get("path", "/"),
                    }
                    if c.get("s") == 1 or c.get("secure"):
                        cookie["secure"] = True
                    exp = c.get("e") or c.get("expirationDate")
                    if exp:
                        cookie["expires"] = exp
                    cookies.append(cookie)
            return cookies if cookies else None
        except Exception:
            return None
        try:
            if json_module is None:
                import json

                json_module = json
            raw = json_module.loads(cookie_data)
            if not raw:
                return None
            cookies = []
            for c in raw:
                if isinstance(c, dict):
                    cookie = {
                        "name": c.get("n") or c.get("name", ""),
                        "value": c.get("v") or c.get("value", ""),
                        "domain": c.get("d") or c.get("domain", ""),
                        "path": c.get("p") or c.get("path", "/"),
                    }
                    if c.get("s") == 1 or c.get("secure"):
                        cookie["secure"] = True
                    exp = c.get("e") or c.get("expirationDate")
                    if exp:
                        cookie["expires"] = exp
                    cookies.append(cookie)
            return cookies if cookies else None
        except Exception:
            return None
        try:
            raw = json.loads(cookie_data)
            if not raw:
                return None
            cookies = []
            for c in raw:
                if isinstance(c, dict):
                    cookie = {
                        "name": c.get("n") or c.get("name", ""),
                        "value": c.get("v") or c.get("value", ""),
                        "domain": c.get("d") or c.get("domain", ""),
                        "path": c.get("p") or c.get("path", "/"),
                    }
                    if c.get("s") == 1 or c.get("secure"):
                        cookie["secure"] = True
                    exp = c.get("e") or c.get("expirationDate")
                    if exp:
                        cookie["expires"] = exp
                    cookies.append(cookie)
            return cookies if cookies else None
        except json.JSONDecodeError:
            return None


class LoginProvider:
    name: str = ""
    login_url: str = ""
    email_input_xpath: str = ""
    password_input_xpath: str = ""
    next_button_text: str = ""
    create_account_xpath: str = ""

    @classmethod
    async def login(cls, browser_context, page, email, password):
        pass


class GoogleLogin(LoginProvider):
    name = "Google"
    login_url = "https://accounts.google.com/signin"
    email_input_xpath = '//input[@type="email"]'
    password_input_xpath = '//input[@type="password"]'
    next_button_text = "Next"

    @classmethod
    async def login(cls, browser_context, page, email, password):
        import asyncio

        await page.goto(cls.login_url)
        await page.wait_for_load_state("networkidle")

        email_input = page.locator(cls.email_input_xpath)
        for _ in range(10):
            if await email_input.count() > 0:
                try:
                    await email_input.fill(email)
                    break
                except:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.5)

        await asyncio.sleep(0.5)

        next_btn = page.get_by_role("button", name=cls.next_button_text)
        for _ in range(10):
            if await next_btn.count() > 0:
                try:
                    await next_btn.click()
                    break
                except:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.5)

        await asyncio.sleep(1.5)

        password_input = page.locator(cls.password_input_xpath)
        for _ in range(10):
            if await password_input.count() > 0:
                try:
                    await password_input.fill(password)
                    break
                except:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.5)

        await asyncio.sleep(0.5)

        next_btn = page.get_by_role("button", name=cls.next_button_text)
        for _ in range(10):
            if await next_btn.count() > 0:
                try:
                    await next_btn.click()
                    break
                except:
                    await asyncio.sleep(0.5)
            else:
                await asyncio.sleep(0.5)

        await asyncio.sleep(1.0)


login_providers = {
    "google": GoogleLogin,
}

supported_games = {
    "kahoot": Kahoot,
    "myshortanswer": MyShortAnswer,
    "blooket": Blooket,
    "magicschoolai": MagicSchoolAI,
    "googleforms": GoogleForms,
}
