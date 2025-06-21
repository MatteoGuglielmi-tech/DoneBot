# PYTHON_ARGCOMPLETE_OK
import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime

import argcomplete
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext._extbot import ExtBot

import utils
from stdout import Formatter, logger
from utils import UNUSED


@dataclass
class NotifyBot:
    # ==== Constructor ====
    fmt: Formatter = Formatter()

    def __post_init__(self) -> None:
        self.secret: dict[str, str] = utils.get_env_variables()
        self.config: dict[str, str] = utils.get_env_variables(pth=".conf")
        self.notification_history: dict[str, list[dict[str, str | int]]] = {}

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

    def progress_bar(self, current: int, total: int, length: int = 50) -> str:
        done: int = int(length * current / total)
        return "█" * done + "-" * (length - done)

    def display_progress_bar(
        self, fmt: str, mode: str = "fstring", **kwargs: str
    ) -> None:
        self.fmt.safe_fprint(fmt=fmt, mode=mode, **kwargs)

    # ==== Telegram handlers ====
    async def clearchat(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        assert update.effective_chat is not None
        chat_id: str = str(update.effective_chat.id)
        bot: ExtBot = context.bot
        deleted: int = 0

        # get is safer than ["field"] since if the key do not exists it
        # doesn't raise a keyerror and return the default
        for entry in self.notification_history.get(chat_id, []):
            msg_id: str | int | None = entry.get("message_id")
            try:
                if not msg_id:
                    raise Exception()
                await bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
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

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        UNUSED(context)
        assert update.message is not None
        await update.message.reply_text(
            "👋 Bot is ready.👋\n"
            "Available commands:\n"
            "  - /clearchat to clear pre-existing bot notifications."
        )

    # ==== SEND AND TRACK NOTIFICATIONS ====
    async def send_notification(self, text: str, bot, command: list) -> None:
        msg = await bot.send_message(chat_id=int(self.secret["CHAT_ID"]), text=text)
        logger.info("Telegram message sent")

        # Add metadata
        entry = {
            "message_id": msg.message_id,
            "timestamp": datetime.now().isoformat(),
            "command": " ".join(command),
        }

        # returns the value of the item with the specified key.
        # If the key does not exist, insert the key, with the specified value
        self.notification_history.setdefault(self.secret["CHAT_ID"], []).append(entry)
        self.save_sent_notifications(data=self.notification_history)

    # ==== RUN SHELL COMMAND ====
    async def run_with_notification(self, command: list, bot: ExtBot) -> None:
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout: str = stdout_bytes.decode().strip()
        stderr: str = stderr_bytes.decode().strip()

        date: str = datetime.today().strftime(format="%Y-%m-%d")
        time: str = datetime.now().strftime(format="%H-%M-%S")
        common_prefix: str = os.path.join(self.config["LOG_PATH"], date, time)
        if not os.path.isdir(s=common_prefix):
            os.makedirs(name=common_prefix)

        log_files: dict[str, str] = {
            "stderr": os.path.join(common_prefix, "stderr.log"),
            "stdout": os.path.join(common_prefix, "stdout.log"),
        }

        for file in log_files:
            with open(file=log_files[file], mode="w") as log_file:
                log_file.write(f"$ {' '.join(command)}\n\n")
                if file == "stdout":
                    log_file.write("STDOUT:\n" + stdout + "\n\n")
                    await asyncio.sleep(1)
                else:
                    log_file.write("STDERR:\n" + stderr + "\n")
                    await asyncio.sleep(1)

        if proc.returncode == 0:
            text = f"✅ Command `{' '.join(command)}` succeeded! ✅ "
        else:
            text = f"❌ Command `{' '.join(command)}` failed ❌! \nError encountered: \n{stderr}"

        await self.send_notification(text, bot, command)

    # ==== Entrypoint ====
    async def main(self) -> None:
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
        assert app.updater is not None
        await app.updater.start_polling()
        await asyncio.sleep(2)  # Let bot initialize

        await self.run_with_notification(args.cmd, app.bot)

        # bot awake period
        # cmnds can be executed here
        print(f"Bot still alive for {self.config["ALIVE_PERIOD"]} seconds")
        text_to_update: str = "Progress: [{bar}] {current_iter}/{total} [seconds]"

        # await asyncio.sleep(delay=int(self.config["ALIVE_PERIOD"]))
        for i in range(int(self.config["ALIVE_PERIOD"]) + 1):
            bar = self.progress_bar(current=i, total=int(self.config["ALIVE_PERIOD"]))
            self.display_progress_bar(
                fmt=text_to_update,
                bar=bar,
                current_iter=str(i),
                total=self.config["ALIVE_PERIOD"],
            )
            await asyncio.sleep(delay=1)

        print()

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    nb: NotifyBot = NotifyBot()
    nb.load_past_notifications()
    asyncio.run(nb.main())
