import os
import asyncio
import hashlib
import json
import logging
import time
from io import BytesIO
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
import config
import main

STEALTH_SCRIPT = config.STEALTH_SCRIPT

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "").lower().replace("@", "")

admins = {ADMIN_USERNAME} if ADMIN_USERNAME else set()
sessions = {}

(
    SELECTING_GAME,
    ENTERING_CUSTOM_KWARGS,
    ENTERING_PIN,
    ENTERING_CLIENTS,
    SELECTING_STATE,
    ENTERING_STATE_SHA256,
    UPLOADING_STATE,
) = range(7)

STATES_DIR = "./states"
os.makedirs(STATES_DIR, exist_ok=True)


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

    keyboard = [
        [InlineKeyboardButton("No", callback_data="no_state")],
        [InlineKeyboardButton("Yes", callback_data="use_state")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Do you want to use a saved authentication state?", reply_markup=reply_markup
    )
    return SELECTING_STATE


async def state_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "no_state":
        context.user_data["use_storage_state"] = False
        context.user_data.pop("storage_state_path", None)

        keyboard = []
        for game_name in config.supported_games.keys():
            keyboard.append(
                [InlineKeyboardButton(game_name.capitalize(), callback_data=game_name)]
            )

        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Please select a game:", reply_markup=reply_markup
        )
        return SELECTING_GAME

    elif query.data == "use_state":
        await query.edit_message_text("Enter the SHA256 hash of the saved state:")
        return ENTERING_STATE_SHA256


async def state_sha256_entered(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sha256 = update.message.text.strip().lower()

    state_path = os.path.join(STATES_DIR, f"{sha256}.json")

    if not os.path.exists(state_path):
        keyboard = [
            [InlineKeyboardButton("No", callback_data="no_state")],
            [InlineKeyboardButton("Yes", callback_data="use_state")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"State not found for hash: {sha256}\nDo you want to try again?",
            reply_markup=reply_markup,
        )
        return SELECTING_STATE

    context.user_data["use_storage_state"] = True
    context.user_data["storage_state_path"] = state_path

    keyboard = []
    for game_name in config.supported_games.keys():
        keyboard.append(
            [InlineKeyboardButton(game_name.capitalize(), callback_data=game_name)]
        )

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "State loaded! Please select a game:", reply_markup=reply_markup
    )
    return SELECTING_GAME


async def upload_state(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    await update.message.reply_text("Please upload the JSON state file.")
    return UPLOADING_STATE


async def handle_state_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.username):
        await update.message.reply_text("You are not authorized to use this bot.")
        return ConversationHandler.END

    if not update.message.document:
        await update.message.reply_text("Please upload a JSON file.")
        return UPLOADING_STATE

    document = update.message.document
    if not document.file_name.endswith(".json"):
        await update.message.reply_text("Please upload a JSON file.")
        return UPLOADING_STATE

    try:
        file = await context.bot.get_file(document.file_id)
        buffer = BytesIO()
        await file.download_to_memory(buffer)
        content = buffer.getvalue().decode("utf-8")
        json.loads(content)
        sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        state_path = os.path.join(STATES_DIR, f"{sha256}.json")
        with open(state_path, "w") as f:
            f.write(content)

        await update.message.reply_text(f"State saved successfully!\nSHA256: {sha256}")
    except json.JSONDecodeError:
        await update.message.reply_text("Error: Invalid JSON file.")
        return UPLOADING_STATE
    except Exception as e:
        await update.message.reply_text(f"Error saving state: {e}")
        return UPLOADING_STATE

    return ConversationHandler.END


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

    storage_state = None
    if context.user_data.get("use_storage_state"):
        storage_state = context.user_data.get("storage_state_path")

    asyncio.create_task(
        run_session(
            session_id,
            game_choice,
            pin,
            num_clients,
            update.effective_chat.id,
            context,
            custom_kwargs,
            storage_state,
        )
    )

    return ConversationHandler.END


async def run_session(
    session_id,
    game_name,
    pin,
    num_clients,
    chat_id,
    context,
    custom_kwargs=None,
    storage_state=None,
):
    if custom_kwargs is None:
        custom_kwargs = {}
    game_class = config.supported_games[game_name]

    try:
        p = await async_playwright().start()
        browser_args = [
            "--use-fake-ui-for-media-stream",
            "--allow-http-screen-capture",
            "--enable-usermedia-screen-capturing",
            "--auto-select-desktop-capture-source=Entire screen",
        ]

        if storage_state and os.path.exists(storage_state):
            context_opts = {"storage_state": storage_state}
        else:
            context_opts = {}

        browser = await p.chromium.launch(headless=False, args=browser_args)
        browser_context = await browser.new_context(**context_opts)
        # await browser_context.add_init_script(script=STEALTH_SCRIPT)

        session = {
            "playwright": p,
            "browser": browser,
            "browser_context": browser_context,
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
            lines.append(f"📝 {key}: {value}")
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


def main_bot():
    if not TOKEN:
        print("Error: TELEGRAM_TOKEN environment variable not set.")
        return

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("uploadstate", upload_state),
        ],
        states={
            SELECTING_STATE: [
                CallbackQueryHandler(state_selection),
            ],
            ENTERING_STATE_SHA256: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_sha256_entered),
            ],
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
            UPLOADING_STATE: [
                MessageHandler(filters.ALL & ~filters.COMMAND, handle_state_upload),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("addadmin", add_admin))
    application.add_handler(CallbackQueryHandler(button_handler, pattern="^close_"))

    print("Bot is starting...")
    application.run_polling()


if __name__ == "__main__":
    main_bot()
