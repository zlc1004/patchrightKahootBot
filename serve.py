import os
import asyncio
import logging
import time
import io
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from patchright.async_api import async_playwright
from fake_useragent import UserAgent
import config
import main

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lower().replace("@", "")

admins = {ADMIN_USERNAME} if ADMIN_USERNAME else set()
sessions = {}

SELECTING_GAME, ENTERING_CUSTOM_KWARGS, ENTERING_PIN, ENTERING_CLIENTS = range(4)
(
    GETSTATE_SELECTING_LOGIN,
    GETSTATE_ENTERING_EMAIL,
    GETSTATE_ENTERING_PASSWORD,
    GETSTATE_BROWSER_CONTROL,
) = range(4, 8)
getstate_sessions = {}


def is_admin(username):
    if not username:
        return False
    return username.lower().replace("@", "") in admins


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.application.bot_data.get("updater_running"):
        context.application.bot_data["updater_running"] = True
        asyncio.create_task(status_updater_loop(context))

    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    keyboard = []
    for game_name in config.supported_games.keys():
        keyboard.append(
            [InlineKeyboardButton(game_name.capitalize(), callback_data=game_name)]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Please select a game:", reply_markup=reply_markup)
    return SELECTING_GAME


async def game_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    game_name = query.data
    context.user_data["game_choice"] = game_name
    game_class = config.supported_games[game_name]
    context.user_data["custom_kwargs"] = {}

    if game_class.use_custom_run_client and game_class.custom_run_client_custom_kargs:
        kargs_list = game_class.custom_run_client_custom_kargs
        context.user_data["custom_kwargs_queue"] = list(kargs_list)
        context.user_data["custom_kwargs_pending"] = None

        first_karg = kargs_list[0]
        await query.edit_message_text(
            text=f"Selected {game_name.capitalize()}. {first_karg.get('prompt', 'Enter value:')}"
        )
        return ENTERING_CUSTOM_KWARGS
    elif game_class.use_custom_run_client:
        await query.edit_message_text(
            text=f"Selected {game_name.capitalize()}. Please enter the number of clients:"
        )
        return ENTERING_CLIENTS
    else:
        await query.edit_message_text(
            text=f"Selected {game_name.capitalize()}. Please enter the game PIN:"
        )
        return ENTERING_PIN


async def custom_kwarg_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kwarg = context.user_data["custom_kwargs_queue"].pop(0)
    key = kwarg.get("key", "value")
    context.user_data["custom_kwargs"][key] = update.message.text

    if context.user_data["custom_kwargs_queue"]:
        next_karg = context.user_data["custom_kwargs_queue"][0]
        await update.message.reply_text(text=next_karg.get("prompt", "Enter value:"))
        return ENTERING_CUSTOM_KWARGS
    else:
        await update.message.reply_text("Please enter the number of clients:")
        return ENTERING_CLIENTS


async def pin_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["pin"] = update.message.text
    await update.message.reply_text("Please enter the number of clients:")
    return ENTERING_CLIENTS


async def clients_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        num_clients = int(update.message.text)
    except ValueError:
        await update.message.reply_text("Please enter a valid number.")
        return ENTERING_CLIENTS

    game_choice = context.user_data["game_choice"]
    pin = context.user_data.get("pin", "")
    custom_kwargs = context.user_data.get("custom_kwargs", {})

    session_id = f"{update.effective_chat.id}_{int(time.time())}"
    await update.message.reply_text(
        f"Launching {num_clients} clients for {game_choice.capitalize()}..."
    )

    asyncio.create_task(
        run_session(
            session_id,
            game_choice,
            pin,
            num_clients,
            update.effective_chat.id,
            context,
            custom_kwargs,
        )
    )

    return ConversationHandler.END


async def run_session(
    session_id, game_name, pin, num_clients, chat_id, context, custom_kwargs=None
):
    if custom_kwargs is None:
        custom_kwargs = {}
    game_class = config.supported_games[game_name]

    try:
        ua = UserAgent()
        user_agent = ua.chrome

        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=False,
            args=[
                f"--user-agent={user_agent}",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-web-security",
                "--disable-infobars",
                "--disable-extensions",
                "--use-fake-ui-for-media-stream",
                "--allow-http-screen-capture",
                "--enable-usermedia-screen-capturing",
                "--auto-select-desktop-capture-source=Entire screen",
            ],
        )

        session = {
            "playwright": p,
            "browser": browser,
            "game_name": game_name,
            "pin": pin,
            "num_clients": num_clients,
            "custom_kwargs": custom_kwargs,
            "clients": [
                {"id": i, "status": "Initializing"} for i in range(num_clients)
            ],
            "start_time": time.time(),
            "chat_id": chat_id,
            "message_id": None,
            "last_update": 0,
            "update_pending": False,
        }
        sessions[session_id] = session

        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text=get_status_text(session_id),
            reply_markup=get_status_markup(session_id),
        )
        session["message_id"] = status_msg.message_id

        async def run_one_client(client_idx):
            session["clients"][client_idx]["status"] = "Joining"
            await update_status_message(session_id, context)

            try:
                if game_class.use_custom_run_client:
                    await game_class.run_client(pin, browser, **custom_kwargs)
                else:
                    await main.run_client(pin, browser, game_class)
                session["clients"][client_idx]["status"] = "Joined ✅"
            except Exception as e:
                session["clients"][client_idx]["status"] = f"Error ❌"
                logger.error(f"Client {client_idx} failed: {e}")

            await update_status_message(session_id, context)

        for i in range(num_clients):
            asyncio.create_task(run_one_client(i))

        asyncio.create_task(auto_close_session(session_id, 600, context))

    except Exception as e:
        logger.error(f"Failed to start session: {e}")
        await context.bot.send_message(
            chat_id=chat_id, text=f"Failed to start session: {e}"
        )


async def auto_close_session(session_id, delay, context):
    await asyncio.sleep(delay)
    if session_id in sessions:
        await close_session(session_id, context)


async def close_session(session_id, context):
    if session_id in sessions:
        session = sessions.pop(session_id)
        try:
            await session["browser"].close()
            await session["playwright"].stop()
        except Exception as e:
            logger.error(f"Error closing browser/playwright: {e}")

        try:
            await context.bot.edit_message_text(
                chat_id=session["chat_id"],
                message_id=session["message_id"],
                text=f"Session {session_id} has been closed (Auto-close or manual).",
            )
        except Exception as e:
            logger.error(f"Error updating status message on close: {e}")


def get_status_text(session_id):
    if session_id not in sessions:
        return "Session not found or already closed."
    session = sessions[session_id]
    lines = [
        f"🎮 Game: {session['game_name'].capitalize()}",
        f"👥 Clients: {session['num_clients']}",
    ]
    if session.get("pin"):
        lines.append(f"🔢 PIN: {session['pin']}")
    if session.get("custom_kwargs"):
        for key, value in session["custom_kwargs"].items():
            if key.startswith("cookies"):
                lines.append(f"🍪 {key}: {len(str(value))} chars")
            else:
                val = str(value)[:50] + "..." if len(str(value)) > 50 else value
                lines.append(f"📝 {key}: {val}")
    lines.append("----------------")
    for client in session["clients"]:
        lines.append(f"Client {client['id'] + 1}: {client['status']}")
    return "\n".join(lines)


def get_status_markup(session_id):
    keyboard = [
        [
            InlineKeyboardButton(
                "🛑 Close All Clients", callback_data=f"close_{session_id}"
            )
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


async def update_status_message(session_id, context):
    if session_id not in sessions:
        return
    session = sessions[session_id]

    current_time = time.time()
    if current_time - session["last_update"] < 0.75:
        session["update_pending"] = True
        return

    await _perform_update(session_id, context)


async def _perform_update(session_id, context):
    if session_id not in sessions:
        return
    session = sessions[session_id]

    session["last_update"] = time.time()
    session["update_pending"] = False

    try:
        await context.bot.edit_message_text(
            chat_id=session["chat_id"],
            message_id=session["message_id"],
            text=get_status_text(session_id),
            reply_markup=get_status_markup(session_id),
        )
    except Exception as e:
        if "Message is not modified" not in str(e):
            logger.debug(f"Update status message error: {e}")


async def status_updater_loop(context):
    while True:
        await asyncio.sleep(0.75)
        for session_id in list(sessions.keys()):
            session = sessions.get(session_id)
            if session and session.get("update_pending"):
                await _perform_update(session_id, context)


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("close_"):
        session_id = query.data.split("_", 1)[1]
        await close_session(session_id, context)


async def add_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.username.lower().replace("@", "") != ADMIN_USERNAME:
        await update.message.reply_text("Only the main admin can add other admins.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /addadmin @username")
        return

    new_admin = context.args[0].lower().replace("@", "")
    admins.add(new_admin)
    await update.message.reply_text(f"Admin @{new_admin} added.")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled.")
    return ConversationHandler.END


async def getstate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    keyboard = []
    for login_name in config.login_providers.keys():
        keyboard.append(
            [
                InlineKeyboardButton(
                    login_name.capitalize(), callback_data=f"login_{login_name}"
                )
            ]
        )
    keyboard.append([InlineKeyboardButton("Custom URL", callback_data="login_custom")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select login type:", reply_markup=reply_markup)
    return GETSTATE_SELECTING_LOGIN


async def getstate_login_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    login_type = query.data.replace("login_", "")

    if login_type == "custom":
        context.user_data["getstate_login_type"] = "custom"
        await query.edit_message_text("Enter custom login URL:")
        return GETSTATE_ENTERING_EMAIL
    else:
        login_class = config.login_providers.get(login_type)
        context.user_data["getstate_login_type"] = login_type
        context.user_data["getstate_login_class"] = login_class
        await query.edit_message_text(f"Enter email for {login_type.capitalize()}:")
        return GETSTATE_ENTERING_EMAIL


async def getstate_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip()
    context.user_data["getstate_email"] = email
    await update.message.reply_text("Enter password:")
    return GETSTATE_ENTERING_PASSWORD


async def getstate_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    context.user_data["getstate_password"] = password

    await update.message.reply_text("Starting browser... Please wait.")

    session_id = f"getstate_{update.effective_chat.id}_{int(time.time())}"

    try:
        ua = UserAgent()
        user_agent = ua.chrome

        p = await async_playwright().start()
        browser = await p.chromium.launch(
            headless=False,
            args=[
                # f"--user-agent={user_agent}",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-infobars",
                "--disable-extensions",
            ],
        )

        browser_context = await browser.new_context(user_agent=user_agent)
        stealth_page = await browser_context.new_page()
        await stealth_page.add_init_script(
            script="""const defaultGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;defaultGetter.apply(navigator),defaultGetter.toString(),Object.defineProperty(Navigator.prototype,"webdriver",{set:void 0,enumerable:!0,configurable:!0,get:new Proxy(defaultGetter,{apply:(e,t,r)=>(Reflect.apply(e,t,r),!1)})});const patchedGetter=Object.getOwnPropertyDescriptor(Navigator.prototype,"webdriver").get;patchedGetter.apply(navigator),patchedGetter.toString();"""
        )
        page = await browser_context.new_page()

        login_type = context.user_data.get("getstate_login_type", "custom")
        email = context.user_data.get("getstate_email", "")
        password = context.user_data.get("getstate_password", "")

        if login_type == "custom":
            custom_url = context.user_data.get("getstate_custom_url", "")
            if custom_url:
                await page.goto(custom_url)
            else:
                await page.goto("about:blank")
        else:
            login_class = context.user_data.get("getstate_login_class")
            if login_class:
                await login_class.login(browser_context, page, email, password)

        getstate_sessions[session_id] = {
            "playwright": p,
            "browser": browser,
            "browser_context": browser_context,
            "page": page,
            "chat_id": update.effective_chat.id,
            "message_id": None,
            "email": email[:5] + "***",
        }
        email = context.user_data.get("getstate_email", "")
        password = context.user_data.get("getstate_password", "")

        if login_type == "custom":
            custom_url = context.user_data.get("getstate_custom_url", "")
            if custom_url:
                await page.goto(custom_url)
            else:
                await page.goto("about:blank")
        else:
            login_class = context.user_data.get("getstate_login_class")
            if login_class:
                await login_class.login(browser_context, page, email, password)

        getstate_sessions[session_id] = {
            "playwright": p,
            "browser": browser,
            "browser_context": browser_context,
            "page": page,
            "chat_id": update.effective_chat.id,
            "message_id": None,
            "email": email[:5] + "***",
        }

        keyboard = [
            [
                InlineKeyboardButton(
                    "📸 Screenshot", callback_data=f"gs_screenshot_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🔗 Go to URL", callback_data=f"gs_url_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "💻 Click Element", callback_data=f"gs_click_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "⌨️ Type Text", callback_data=f"gs_type_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "🖱️ Find Elements", callback_data=f"gs_find_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "✅ Save State & Exit", callback_data=f"gs_save_{session_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "❌ Exit Without Saving", callback_data=f"gs_exit_{session_id}"
                )
            ],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        screenshot = await page.screenshot(type="jpeg", quality=70)
        bio = io.BytesIO(screenshot)
        bio.seek(0)

        msg = await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=bio,
            caption=f"Browser started. Session: {session_id[:12]}...\nEmail: {email[:10]}***",
            reply_markup=reply_markup,
        )

        getstate_sessions[session_id]["message_id"] = msg.message_id

    except Exception as e:
        logger.error(f"Failed to start browser: {e}")
        await update.message.reply_text(f"Failed to start browser: {e}")
        return ConversationHandler.END

    return GETSTATE_BROWSER_CONTROL


async def getstate_browser_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data
    session_id = None

    for key in getstate_sessions.keys():
        if key in data:
            session_id = key
            break

    if not session_id or session_id not in getstate_sessions:
        await query.edit_message_text("Session expired or not found.")
        return ConversationHandler.END

    session = getstate_sessions[session_id]
    page = session["page"]

    try:
        if "_screenshot_" in data:
            screenshot = await page.screenshot(type="jpeg", quality=70)
            bio = io.BytesIO(screenshot)
            bio.seek(0)

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔄 Refresh", callback_data=f"gs_screenshot_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back", callback_data=f"gs_back_{session_id}"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await query.edit_message_media(
                    media=InputMediaPhoto(
                        media=bio, caption=f"Session: {session_id[:12]}..."
                    ),
                    reply_markup=reply_markup,
                )
            except Exception:
                try:
                    await query.delete_message()
                except:
                    pass
                msg = await context.bot.send_photo(
                    chat_id=session["chat_id"],
                    photo=bio,
                    caption=f"Session: {session_id[:12]}...",
                    reply_markup=reply_markup,
                )
                session["message_id"] = msg.message_id

        elif "_url_" in data:
            context.user_data["getstate_session_id"] = session_id
            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_message(
                chat_id=session["chat_id"],
                text="Enter URL to navigate to:",
            )
            session["message_id"] = msg.message_id

        elif "_click_" in data:
            context.user_data["getstate_session_id"] = session_id
            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_message(
                chat_id=session["chat_id"],
                text="Enter element number or XPath to click:",
            )
            session["message_id"] = msg.message_id

        elif "_type_" in data:
            context.user_data["getstate_session_id"] = session_id
            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_message(
                chat_id=session["chat_id"],
                text="Enter text to type:",
            )
            session["message_id"] = msg.message_id

        elif "_find_" in data:
            elements = []

            buttons = page.locator("button")
            btn_count = await buttons.count()
            for i in range(min(btn_count, 15)):
                try:
                    txt = await buttons.nth(i).inner_text()
                    if txt:
                        elements.append(f"[Button] {txt[:30]}")
                except:
                    pass

            links = page.locator("a")
            link_count = await links.count()
            for i in range(min(link_count, 15)):
                try:
                    txt = await links.nth(i).inner_text()
                    if txt:
                        elements.append(f"[Link] {txt[:30]}")
                except:
                    pass

            inputs = page.locator(
                "input[type='text'],input[type='email'],input[type='password']"
            )
            inp_count = await inputs.count()
            for i in range(min(inp_count, 10)):
                try:
                    ph = await inputs.nth(i).get_attribute("placeholder")
                    name = await inputs.nth(i).get_attribute("name")
                    id_ = await inputs.nth(i).get_attribute("id")
                    label = ph or name or id_ or f"input#{i}"
                    elements.append(f"[Input] {label[:30]}")
                except:
                    pass

            text_content = await page.evaluate(
                """() => {
                const texts = [];
                document.querySelectorAll('h1,h2,h3,h4,p,span,label').forEach(el => {
                    const t = el.innerText.trim().substring(0, 25);
                    if (t && t.length > 2 && !texts.includes(t)) texts.push(t);
                });
                return texts.slice(0, 10);
            }"""
            )
            for t in text_content:
                elements.append(f"[Text] {t}")

            if not elements:
                elements = ["No interactive elements found"]

            elements_list = "\n".join(elements[:25])
            full_text = f"Found {len(elements)} elements:\n\n{elements_list}\n\nReply with number or XPath:"

            keyboard = [
                [
                    InlineKeyboardButton(
                        "🔄 Refresh", callback_data=f"gs_find_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔙 Back", callback_data=f"gs_back_{session_id}"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_message(
                chat_id=session["chat_id"],
                text=full_text,
                reply_markup=reply_markup,
            )
            session["message_id"] = msg.message_id

        elif "_save_" in data:
            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_message(
                chat_id=session["chat_id"],
                text="Saving state...",
            )

            try:
                state = await page.context.storage_state()
                state_json = json.dumps(state, indent=2)
                bio = io.BytesIO(state_json.encode())
                bio.seek(0)

                await context.bot.send_document(
                    chat_id=session["chat_id"],
                    document=bio,
                    filename=f"storage_state_{int(time.time())}.json",
                    caption="Storage state saved!",
                )

                await session["browser"].close()
                await session["playwright"].stop()
                getstate_sessions.pop(session_id, None)

                await context.bot.send_message(
                    chat_id=session["chat_id"], text="Browser closed. State saved."
                )
            except Exception as e:
                logger.error(f"Save error: {e}")
                await context.bot.send_message(
                    chat_id=session.get("chat_id", 0), text=f"Save error: {e}"
                )
            return ConversationHandler.END

        elif "_exit_" in data:
            try:
                s = getstate_sessions.get(session_id)
                if s:
                    browser = s.get("browser")
                    p = s.get("playwright")
                    if browser:
                        await browser.close()
                    if p:
                        await p.stop()
                    getstate_sessions.pop(session_id, None)
                try:
                    await query.delete_message()
                except:
                    pass
                await context.bot.send_message(
                    chat_id=session["chat_id"], text="Browser closed without saving."
                )
            except Exception as e:
                logger.error(f"Exit error: {e}")
            return ConversationHandler.END

        elif "_back_" in data:
            screenshot = await page.screenshot(type="jpeg", quality=70)
            bio = io.BytesIO(screenshot)
            bio.seek(0)

            keyboard = [
                [
                    InlineKeyboardButton(
                        "📸 Screenshot", callback_data=f"gs_screenshot_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🔗 Go to URL", callback_data=f"gs_url_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "💻 Click Element", callback_data=f"gs_click_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⌨️ Type Text", callback_data=f"gs_type_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "🖱️ Find Elements", callback_data=f"gs_find_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "✅ Save State & Exit", callback_data=f"gs_save_{session_id}"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "❌ Exit Without Saving", callback_data=f"gs_exit_{session_id}"
                    )
                ],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await query.delete_message()
            except:
                pass
            msg = await context.bot.send_photo(
                chat_id=session["chat_id"],
                photo=bio,
                caption=f"Session: {session_id[:12]}...",
                reply_markup=reply_markup,
            )
            session["message_id"] = msg.message_id

    except Exception as e:
        logger.error(f"Browser handler error: {e}")
        chat_id = session.get("chat_id") if session else None
        if chat_id:
            await context.bot.send_message(chat_id=chat_id, text=f"Error: {e}")

    return GETSTATE_BROWSER_CONTROL


async def getstate_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get("getstate_session_id")
    if not session_id or session_id not in getstate_sessions:
        await update.message.reply_text("Session expired.")
        return ConversationHandler.END

    session = getstate_sessions[session_id]
    page = session["page"]

    url = update.message.text.strip()
    if not url.startswith("http"):
        url = "https://" + url

    await page.goto(url)
    await page.wait_for_load_state("networkidle")
    await update.message.reply_text(f"Navigated to {url}")

    return await getstate_browser_send_screenshot(update, context, session_id)


async def getstate_click_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get("getstate_session_id")
    if not session_id or session_id not in getstate_sessions:
        await update.message.reply_text("Session expired.")
        return ConversationHandler.END

    session = getstate_sessions[session_id]
    page = session["page"]

    user_input = update.message.text.strip()

    try:
        if user_input.isdigit():
            idx = int(user_input) - 1
            elements = []

            buttons = page.locator("button")
            for i in range(await buttons.count()):
                try:
                    txt = await buttons.nth(i).inner_text()
                    if txt:
                        elements.append(("button", i, txt))
                except:
                    pass

            links = page.locator("a")
            for i in range(await links.count()):
                try:
                    txt = await links.nth(i).inner_text()
                    if txt:
                        elements.append(("link", i, txt))
                except:
                    pass

            if idx < len(elements) and idx >= 0:
                type_, i, txt = elements[idx]
                if type_ == "button":
                    await buttons.nth(i).click()
                else:
                    await links.nth(i).click()
        else:
            locator = page.locator(user_input)
            if await locator.count() > 0:
                await locator.first.click()
            else:
                await page.locator(f"xpath={user_input}").first.click()

        await page.wait_for_load_state("networkidle")
        await update.message.reply_text("Clicked!")

    except Exception as e:
        await update.message.reply_text(f"Click failed: {e}")

    return await getstate_browser_send_screenshot(update, context, session_id)


async def getstate_type_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = context.user_data.get("getstate_session_id")
    if not session_id or session_id not in getstate_sessions:
        await update.message.reply_text("Session expired.")
        return ConversationHandler.END

    session = getstate_sessions[session_id]
    page = session["page"]

    text = update.message.text

    active = page.locator(":focus")
    if await active.count() > 0:
        await active.fill(text)
    else:
        inputs = page.locator(
            "input[type='text'],input[type='email'],input[type='password']"
        )
        if await inputs.count() > 0:
            await inputs.first.fill(text)

    await update.message.reply_text("Text entered!")

    return await getstate_browser_send_screenshot(update, context, session_id)


async def getstate_browser_send_screenshot(update, context, session_id):
    session = getstate_sessions.get(session_id)
    if not session:
        try:
            await update.callback_query.edit_message_text("Session expired.")
        except:
            await update.message.reply_text("Session expired.")
        return ConversationHandler.END

    chat_id = session.get("chat_id")
    if not chat_id:
        try:
            await update.callback_query.edit_message_text("Session error: no chat_id.")
        except:
            await update.message.reply_text("Session error: no chat_id.")
        return ConversationHandler.END

    page = session["page"]

    screenshot = await page.screenshot(type="jpeg", quality=70)
    bio = io.BytesIO(screenshot)
    bio.seek(0)

    keyboard = [
        [
            InlineKeyboardButton(
                "📸 Screenshot", callback_data=f"gs_screenshot_{session_id}"
            )
        ],
        [InlineKeyboardButton("🔗 Go to URL", callback_data=f"gs_url_{session_id}")],
        [
            InlineKeyboardButton(
                "💻 Click Element", callback_data=f"gs_click_{session_id}"
            )
        ],
        [InlineKeyboardButton("⌨️ Type Text", callback_data=f"gs_type_{session_id}")],
        [
            InlineKeyboardButton(
                "🖱️ Find Elements", callback_data=f"gs_find_{session_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "✅ Save State & Exit", callback_data=f"gs_save_{session_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "❌ Exit Without Saving", callback_data=f"gs_exit_{session_id}"
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        msg = await context.bot.send_photo(
            chat_id=chat_id,
            photo=bio,
            caption=f"Session: {session_id[:12]}...",
            reply_markup=reply_markup,
        )
        session["message_id"] = msg.message_id
    except Exception as e:
        logger.error(f"Failed to send screenshot: {e}")
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=f"Error sending screenshot: {e}"
            )
        except:
            pass

    return GETSTATE_BROWSER_CONTROL


async def getstate_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END


def main_bot():
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECTING_GAME: [CallbackQueryHandler(game_selected)],
            ENTERING_CUSTOM_KWARGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, custom_kwarg_entered)
            ],
            ENTERING_PIN: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, pin_entered)
            ],
            ENTERING_CLIENTS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, clients_entered)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^close_"))

    getstate_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("getstate", getstate)],
        states={
            GETSTATE_SELECTING_LOGIN: [CallbackQueryHandler(getstate_login_selected)],
            GETSTATE_ENTERING_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, getstate_email)
            ],
            GETSTATE_ENTERING_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, getstate_password)
            ],
            GETSTATE_BROWSER_CONTROL: [
                CallbackQueryHandler(getstate_browser_handler, pattern="^gs_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, getstate_url_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, getstate_click_input),
                MessageHandler(filters.TEXT & ~filters.COMMAND, getstate_type_input),
            ],
        },
        fallbacks=[CommandHandler("cancel", getstate_cancel)],
        allow_reentry=True,
    )
    application.add_handler(getstate_conv_handler)

    print("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main_bot()
