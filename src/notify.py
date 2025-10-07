# PYTHON_ARGCOMPLETE_OK
import argparse
import asyncio
import json
import os
import utils
import argcomplete

from pathlib import Path
from dataclasses import dataclass
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.ext._extbot import ExtBot

from stdout import Formatter, logger
from utils import UNUSED


@dataclass
class NotifyBot:
    """A Telegram bot designed to notify users about the completion status of
    wrapped shell commands and provide chat management functionalities."""

    # ==== Constructor ====
    fmt: Formatter = Formatter()

    def __post_init__(self) -> None:
        """Initializes the NotifyBot instance, loading environment variables
        and configuration, and setting up an empty notification history."""

        prj_root = Path(__file__).parent.parent
        _confpath = prj_root / "conf.json"
        self.secret: dict[str, str] = utils.get_env_variables()
        config: dict[str, str] = utils.load_config(_confpath)
        self.notification_history: dict[str, list[dict[str, str | int]]] = {}

        self.storage_path = prj_root / config["STORAGE_PATH"]
        self.log_path = prj_root / config["LOG_PATH"]
        self.alive_period = config["ALIVE_PERIOD"]

    # ==== PERSISTENT HISTORY ====
    def load_past_notifications(self) -> None:
        """Loads past notification history from the configured storage path.

        If the storage file does not exist, the history remains an empty
        dictionary.
        """

        if os.path.exists(path=self.storage_path):
            with open(file=self.storage_path, mode="r") as f:
                self.notification_history = json.load(fp=f)
        else:
            # ensure that if the file doesn't exist, notification_history
            # is still initialized as an empty dict
            self.notification_history = {}

    def save_sent_notifications(
        self, data: dict[str, list[dict[str, str | int]]]
    ) -> None:
        """Saves the current notification history to the configured storage
        path.

        Parameters:
        ----------
        data : dict[str, list[dict[str, str | int]]]
            The dictionary containing chat IDs as keys and lists of message
            metadata as values to be saved.
        """

        with open(file=self.storage_path, mode="w") as f:
            json.dump(obj=data, fp=f, indent=2, sort_keys=False)

    def progress_bar(self, current: int, total: int, length: int = 50) -> str:
        """Generates a text-based progress bar.

        Parameters:
        ----------
        current : int
            The current progress value.
        total : int
            The total value representing 100% progress.
        length : int, optional
            The total character length of the progress bar, by default 50.

        Returns:
        -------
        str
            A string representing the progress bar (e.g., "█████-----").
        """

        done: int = int(length * current / total)
        return "█" * done + "-" * (length - done)

    def display_progress_bar(
        self, fmt: str, mode: str = "fstring", **kwargs: str
    ) -> None:
        """Displays a formatted progress bar using the internal formatter.

        Parameters
        ----------
        fmt : str
            The format string for the progress display, which can include placeholders
            for `bar`, `current_iter`, `total`, etc.
        mode : str, optional
            The formatting mode (e.g., "fstring"), by default "fstring".
        **kwargs : str
            Arbitrary keyword arguments to be used for formatting the `fmt` string.
        """

        self.fmt.safe_fprint(fmt=fmt, mode=mode, **kwargs)

    # ==== Telegram handlers ====
    async def clearchat(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Telegram command handler for `/clearchat`. Deletes all bot messages
        from the chat that are recorded in the history, then clears the chat's
        history from the bot's storage. Includes a countdown message and a
        disclaimer about Telegram bot limitations.

        Parameters
        ----------
        update : telegram.Update
            The incoming Telegram update.
        context : telegram.ext.ContextTypes.DEFAULT_TYPE
            The context object for the current update.
        """

        assert update.effective_chat is not None
        chat_id: str = str(update.effective_chat.id)
        bot: ExtBot = context.bot
        deleted: int = 0

        # load all existing notifications
        self.load_past_notifications()

        # get is safer than ["field"] since if the key do not exists it
        # doesn't raise a keyerror and return the default
        for entry in self.notification_history.get(chat_id, []):
            msg_id: str | int | None = entry.get("message_id")
            try:
                if not msg_id:
                    raise ValueError("message_id is missing or invalid.")
                await bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
                deleted += 1
            except Exception as e:
                logger.warning(f"❌ Failed to delete message {msg_id}: {e} ❌")

        # after attempting to delete all messages, clear the history for this chat and save
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
        """Telegram command handler for `/start`. Sends a welcome message to
        the user, introducing the bot and available commands.

        Parameters
        ----------
        update : telegram.Update
            The incoming Telegram update.
        context : telegram.ext.ContextTypes.DEFAULT_TYPE
            The context object for the current update.
        """

        UNUSED(context)
        assert update.message is not None
        await update.message.reply_text(
            "👋 Bot is ready.👋\n"
            "Available commands:\n"
            "  - /clearchat to clear pre-existing bot notifications."
        )

    # ==== SEND AND TRACK NOTIFICATIONS ====
    async def send_notification(self, text: str, bot, command: list) -> None:
        """Sends a text notification to the configured Telegram chat and
        records its metadata.

        Parameters
        ----------
        text : str
            The message text to send.
        bot : telegram.ext._extbot.ExtBot
            The Telegram bot instance used to send the message.
        command : list
            The command list that triggered this notification. Used for history tracking.
        """

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
        """Executes a shell command as a subprocess, sends a "started"
        notification, logs stdout/stderr to files, and then sends a final
        notification (success or failure) to Telegram.

        Parameters
        ----------
        command : list
            A list of strings representing the command and its arguments.
        bot : telegram.ext._extbot.ExtBot
            The Telegram bot instance to send notifications.
        """

        # notification of start
        command_str: str = " ".join(command)
        start_message_text: str = f"🚀 Command `{command_str}` started! 🚀"
        await self.send_notification(text=start_message_text, bot=bot, command=command)

        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        stdout: str = stdout_bytes.decode().strip()
        stderr: str = stderr_bytes.decode().strip()

        date: str = datetime.today().strftime(format="%Y-%m-%d")
        time: str = datetime.now().strftime(format="%H-%M-%S")
        common_prefix: str = os.path.join(self.log_path, date, time)
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
            error_lines = [line for line in stderr.splitlines() if line.strip()]
            last_error = error_lines[-1] if error_lines else "Unknown error"
            text = (
                f"❌ Command `{' '.join(command)}` failed ❌!\n"
                f"Error encountered: \n{last_error}"
            )


        await self.send_notification(text, bot, command)

    # ==== Entrypoint ====
    async def main(self) -> None:
        """The main entry point for the NotifyBot application.

        Parses command-line arguments, initializes the Telegram bot,
        starts polling, runs the wrapped command with notifications, and
        manages the bot's alive period with a progress bar.
        """

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
        # print(f"Bot still alive for {self.config["ALIVE_PERIOD"]} seconds")
        text_to_update: str = "Bot still alive for: [{bar}] {current_iter}/{total} [seconds]"

        for i in range(int(self.alive_period) + 1):
            bar = self.progress_bar(current=i, total=int(self.alive_period))
            self.display_progress_bar(
                fmt=text_to_update,
                bar=bar,
                current_iter=str(i),
                total=self.alive_period
            )
            await asyncio.sleep(delay=1)

        print()

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    nb: NotifyBot = NotifyBot()
    asyncio.run(nb.main())
