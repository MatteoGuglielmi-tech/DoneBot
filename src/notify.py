# PYTHON_ARGCOMPLETE_OK
import argparse
import asyncio
import json
import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage

import argcomplete
import requests
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext._extbot import ExtBot

import utils
from stdout import logger
from utils import UNUSED


@dataclass
class NotifyBot:
    # ==== Constructor ====

    def __post_init__(self) -> None:
        self.secret: dict[str, str] = utils.get_env_variables()
        self.config: dict[str, str] = utils.get_env_variables(pth=".conf")
        self.notification_history: dict[str, list[dict[str, str | int]]] = {}

    # ==== NOTIFICATIONS ====
    def send_telegram_message(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.secret["BOT_TOKEN"]}/sendMessage"
        try:
            res = requests.post(
                url, data={"chat_id": self.secret["CHAT_ID"], "text": message}
            )
            res.raise_for_status()
            logger.info("Telegram message sent")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    # for now, email feature has not been tested
    # tg is fine for me
    def send_email_notification(self, subject: str, body: str) -> None:
        if not self.secret["EMAIL_ENABLED"]:
            logger.debug(msg="Email not enabled")
            return
        try:
            msg = EmailMessage()
            msg.set_content(body)
            msg["Subject"] = subject
            msg["From"] = self.secret["EMAIL_ADDRESS"]
            msg["To"] = self.secret["EMAIL_RECIPIENT"]

            with smtplib.SMTP(
                self.secret["SMTP_SERVER"], int(self.secret["SMTP_PORT"])
            ) as smtp:
                smtp.starttls()
                smtp.login(self.secret["EMAIL_ADDRESS"], self.secret["EMAIL_PASSWORD"])
                smtp.send_message(msg)
            logger.info(msg="📨 Email sent 📨")
        except Exception as e:
            logger.error(f"⛔ Email send failed: {e} ⛔")

    # ==== PERSISTENT HISTORY ====
    def load_past_notifications(self) -> None:
        if os.path.exists(path=self.config["STORAGE_PATH"]):
            with open(file=self.config["STORAGE_PATH"], mode="r") as f:
                self.notification_history = json.load(fp=f)

    def save_sent_notifications(
        self, data: dict[str, list[dict[str, str | int]]]
    ) -> None:
        with open(file=self.config["STORAGE_PATH"], mode="w") as f:
            json.dump(obj=data, fp=f, indent=2, sort_keys=False)

    # ==== Telegram handlers ====
    async def clearchat(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id: str = str(update.effective_chat.id)
        bot: ExtBot = context.bot
        deleted: int = 0

        # get is safer than ["field"] since if the key do not exists it
        # doesn't raise a keyerror and return the default
        for entry in self.notification_history.get(chat_id, []):
            msg_id = entry.get("message_id")
            try:
                await bot.delete_message(chat_id=int(chat_id), message_id=msg_id)
                deleted += 1
            except Exception as e:
                logger.warning(f"❌ Failed to delete message {msg_id}: {e} ❌")

        self.notification_history[chat_id] = []
        self.save_sent_notifications(self.notification_history)

        cdown_seconds: int = 5
        countdown_text = (
            f"🧹 Cleared {deleted} message(s). 🧹\n"
            f"This message will self-destruct in {cdown_seconds} seconds..."
        )

        countdown_msg = await bot.send_message(
            chat_id=int(chat_id), text=countdown_text
        )

        # start, stop, step
        for i in range((cdown_seconds - 1), 0, -1):
            await asyncio.sleep(1)
            try:
                await bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=countdown_msg.message_id,
                    text=countdown_text.replace(str(cdown_seconds), str(i)),
                )

            except Exception as e:
                logger.warning(f"❗ Failed to update countdown message: {e} ❗")
                break

        await asyncio.sleep(1)  # leave room for animation to complete
        try:
            await bot.delete_message(
                chat_id=int(chat_id), message_id=countdown_msg.message_id
            )
        except Exception as e:
            logger.warning(f"❗ Failed to delete countdown message: {e}")

        limit_warning = await bot.send_message(
            chat_id=int(chat_id),
            text="⚠️ <b>Telegram does not allow bots to delete your own messages.</b> ⚠️\n\n"
            "To clear full history, long-press the chat > tap 'Delete' > tap 'Clear Chat History'.",
            parse_mode=ParseMode.HTML,
        )

        # 10 secs before the warning message disappears
        await asyncio.sleep(10)
        await bot.delete_message(
            chat_id=int(chat_id), message_id=limit_warning.message_id
        )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        UNUSED(context)
        await update.message.reply_text(
            "👋 Bot is ready.👋\n"
            "Available commands:\n"
            "  - /clearchat to clear pre-existing bot notifications."
        )

    # ==== SEND AND TRACK NOTIFICATIONS ====
    async def send_notification(self, text: str, bot, command: list):
        msg = await bot.send_message(chat_id=int(self.secret["CHAT_ID"]), text=text)

        # Add metadata
        entry = {
            "message_id": msg.message_id,
            "timestamp": datetime.now().isoformat(),
            "command": " ".join(command),
        }

        # returns the value of the item with the specified key.
        # If the key does not exist, insert the key, with the specified value, see example below
        self.notification_history.setdefault(self.secret["CHAT_ID"], []).append(entry)
        self.save_sent_notifications(data=self.notification_history)

    # ==== RUN SHELL COMMAND ====
    async def run_with_notification(self, command: list, bot: ExtBot):
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()

        if proc.returncode == 0:
            text = f"✅ Command `{' '.join(command)}` succeeded! ✅ "
        else:
            text = f"❌ Command `{' '.join(command)}` failed ❌! \nReturn Code: ({proc.returncode})\n{stderr.decode()}"

        await self.send_notification(text, bot, command)

    # ==== Entrypoint ====
    async def main(self):
        parser = argparse.ArgumentParser(description="Notify when a process finishes.")
        parser.add_argument(
            "--cmd",
            nargs=argparse.REMAINDER,
            required=True,
            help="Command to run (e.g. --cmd python --version)",
        )
        argcomplete.autocomplete(parser)
        args = parser.parse_args()

        app = Application.builder().token(self.secret["BOT_TOKEN"]).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("clearchat", self.clearchat))

        await app.initialize()
        await app.start()
        await app.updater.start_polling()
        await asyncio.sleep(2)  # Let bot initialize

        await self.run_with_notification(args.cmd, app.bot)

        # bot awake period
        # cmnds can be executed here
        await asyncio.sleep(delay=int(self.config["ALIVE_PERIOD"]))

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    nb: NotifyBot = NotifyBot()
    nb.load_past_notifications()
    asyncio.run(nb.main())
