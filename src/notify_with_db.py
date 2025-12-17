"""
NotifyBot with Database Support
================================
Enhanced version of `notify.py` with PostgreSQL/SQLite database for shared notification history.

Setup:
    1. PostgreSQL: Set DATABASE_URL in environment
    2. SQLite: Will auto-create local database file
"""


import os
import asyncio
import argparse
import platform
import socket
import re
import utils
import logging
import time

from datetime import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes, ExtBot

from stdout import Formatter
from logger_config import setup_logger

from db_manager import DatabaseManager


logger = logging.getLogger(__name__)

@dataclass
class NotifyBot:
    """A Telegram bot designed to notify users about the completion status of
    wrapped shell commands and provide chat management functionalities."""

    db_type: type[DatabaseManager] = field(init=True)

    # invisible fields
    db: DatabaseManager = field(init=False, repr=False)
    db_path: Optional[str] = field(init=False, repr=False)
    use_postgres: bool = field(init=False, default=False, repr=False)
    chat_id: Optional[str] = field(init=False, default=None, repr=False)
    bot_token: Optional[str] = field(init=False, default=None, repr=False)
    device_name: Optional[str] = field(init=False, default=None, repr=False)
    fmt: Formatter = field(default_factory=Formatter)

    def __post_init__(self) -> None:
        """Initializes the NotifyBot instance, loading environment variables
        and configuration, and setting up an empty notification history."""

        prj_root = Path(__file__).parent.parent
        _confpath = prj_root / "conf.json"

        self.chat_id = os.getenv(key="CHAT_ID")
        self.bot_token = os.getenv(key="BOT_TOKEN")
        self.device_name = socket.gethostname()
        self.os_name = platform.system()

        if not all([self.chat_id, self.bot_token]):
                raise ValueError("Missing required PostgreSQL connection parameters")

        config: dict[str, str] = utils.load_config(_confpath)
        self.log_path = prj_root / config["LOG_PATH"]
        self.alive_period = config["ALIVE_PERIOD"]

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

        # fetch notifications from database
        notifications = self.db.get_notifications_for_chat(chat_id)

        for entry in notifications:
            msg_id: Optional[str | int] = entry.get("message_id")
            try:
                if not msg_id:
                    raise ValueError("message_id is missing or invalid.")
                await bot.delete_message(chat_id=int(chat_id), message_id=int(msg_id))
                deleted += 1
            except Exception as e:
                logger.exception(f"❌ Failed to delete message {msg_id} ❌")

        # clear chat_id entries from db
        self.db.delete_notifications_for_chat(chat_id=chat_id)

        cdown_seconds: int = 5
        countdown_text = (
            f"🧹 Cleared {deleted} message(s). 🧹\n"
            f"This message will self-destruct in {cdown_seconds} seconds..."
        )

        countdown_msg = await bot.send_message(
            chat_id=int(chat_id), text=countdown_text
        )

        for i in range((cdown_seconds - 1), 0, -1):
            await asyncio.sleep(1)
            try:
                await bot.edit_message_text(
                    chat_id=int(chat_id),
                    message_id=countdown_msg.message_id,
                    text=countdown_text.replace(str(cdown_seconds), str(i)),
                )

            except Exception as e:
                logger.exception(f"❗ Failed to update countdown message ❗")
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

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show database statistics."""
        assert update.message is not None

        _ = context

        stats = self.db.get_statistics()
        chat_id = str(update.effective_chat.id)
        chat_notifications = self.db.get_notifications_for_chat(chat_id, limit=5)

        stats_text = (
            f"📊 <b>Database Statistics</b> 📊\n\n"
            f"Total notifications: {stats.get('total_notifications', 0)}\n"
            f"Unique chats: {stats.get('unique_chats', 0)}\n"
            f"Unique devices: {stats.get('unique_devices', 0)}\n\n"
            f"Recent commands in this chat:\n"
        )

        for notif in chat_notifications[:5]:
            cmd_short = (
                notif["command"][:40] + "..."
                if len(notif["command"]) > 40
                else notif["command"]
            )
            device = notif.get("device_name", "unknown")
            stats_text += f"  • <code>{cmd_short}</code> ({device})\n"

        await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

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

        _ = context

        assert update.message is not None
        await update.message.reply_text(
            "👋 Bot is ready.👋\n"
            "Available commands:\n"
            "  - /clearchat to clear pre-existing bot notifications.\n"
            "  - /stats to view usage statistics."
        )

    # ==== SEND AND TRACK NOTIFICATIONS ====
    async def send_notification(self, text: str, bot: ExtBot, command: list, status: str="completed") -> None:
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

        msg = await bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode=ParseMode.HTML
        )
        logger.info("Telegram message sent")

        # update db
        self.db.add_notification(
            chat_id=self.chat_id,
            message_id=msg.message_id,
            command=" ".join(command),
            device_name=self.device_name,
            os_name=self.os_name,
            status=status
        )

    # ==== RUN SHELL COMMAND ====
    async def run_with_notification(
        self, command: list, bot: ExtBot, log_path: Optional[Path]
    ) -> None:
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

        job_name = os.environ.get("SLURM_JOB_NAME", "unknown")
        job_id = os.environ.get("SLURM_JOB_ID")

        # notification of start
        command_str: str = " ".join(command)
        start_message_text: str = (
            f"🚀 Command `{command_str}` started on {self.device_name}! 🚀"
        )

        if job_id and job_name != "unknown":
            start_message_text += "\n"
            start_message_text += 30 * "="
            start_message_text += f"\nJob ID: `{job_id}`"
            start_message_text += f"\nJob Name: `{job_name}`"

        await self.send_notification(
            text=start_message_text, bot=bot, command=command, status="started"
        )

        start: float = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        elapsed = time.perf_counter() - start
        format_elapsed = utils.format_duration(elapsed)

        stdout: str = stdout_bytes.decode().strip()
        stderr: str = stderr_bytes.decode().strip()

        if log_path:
            date: str = datetime.today().strftime(format="%Y-%m-%d")
            clock: str = datetime.now().strftime(format="%H-%M-%S")
            log_dir: Path = self.log_path / date / clock
            log_dir.mkdir(parents=True, exist_ok=True)

            out_log: Path = log_dir / "stdout.log"
            err_log: Path = log_dir / "stderr.log"

            out_log.write_text(data=f"$ {command_str}\n\nSTDOUT:\n{stdout}")
            await asyncio.sleep(1)
            err_log.write_text(data=f"$ {command_str}\n\nSTDERR:\n{stderr}")
            await asyncio.sleep(1)

        if proc.returncode == 0:
            text = f"✅ Command `{command_str}` succeeded on `{self.device_name}`!\n"
            text += 30 * "="
            text += f"\nRuntime {format_elapsed} ✅"
            status = "success"
        else:
            error_summary = self.extract_main_error(stderr=stderr)
            text = (
                f"❌ Command `{command_str}` failed on `{self.device_name}` after {format_elapsed} ❌\n\n"
                f"**Error:** `{error_summary}`\n\n"
            )
            if log_path:
                text += f"Full log in: `{err_log}`"  # type: ignore[reportPossiblyUnboundVariable]

            status = "failed"

        if job_id and job_name != "unknown":
            text += "\n"
            text += 30 * "="
            text += f"\nJob ID: `{job_id}`"
            text += f"\nJob Name: `{job_name}`"

        await self.send_notification(text=text, bot=bot, command=command, status=status)

    def extract_main_error(self, stderr: str, max_length: int = 200) -> str:
        """Extract the main error message from stderr output.

        Handles chained exceptions by prioritizing the first error when
        'During handling' messages are present.

        Parameters
        ----------
        stderr : str
            The stderr output from the subprocess.
        max_length : int
            Maximum length for the error message.

        Returns
        -------
        str
            The extracted error message, truncated if necessary.
        """

        if not stderr.strip():
            return "Unknown error (no stderr output)"

        lines = stderr.strip().splitlines()

        has_chained_exception = any(
            "During handling of the above exception" in line
            or "The above exception was the direct cause" in line
            for line in lines
        )

        exception_pattern = re.compile(
            r"^(?:\[rank\d+\]:\s*)?"  # Optional rank prefix like [rank0]:
            r"([A-Z][a-zA-Z0-9]*(?:Error|Exception|Interrupt))"  # Exception type
            r":\s*(.+)$"  # Colon and error message
        )

        exception_lines = []
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            ma = exception_pattern.match(line_stripped)
            if ma:
                exception_type = ma.group(1)
                exception_message = ma.group(2)
                full_error = f"{exception_type}: {exception_message}"
                exception_lines.append((i, full_error))

        if not exception_lines:
            error = "Unknown error"
        elif has_chained_exception:
            error = exception_lines[0][1]
        else:
            error = exception_lines[-1][1]

        if len(error) > max_length:
            error = error[:max_length] + "..."

        return error

    # ==== Entrypoint ====
    async def main(self) -> None:
        """The main entry point for the NotifyBot application.

        Parses command-line arguments, initializes the Telegram bot,
        starts polling, runs the wrapped command with notifications, and
        manages the bot's alive period with a progress bar.
        """

        parser = argparse.ArgumentParser(
            description="NotifyBot with Database (PostgreSQL/SQLite) - Multi-device command notifications",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=(
                "Examples:\n"
                "%(prog)s --use_postgres --cmd python script.py\n"
                "%(prog)s --db_path path_to_db.db --cmd python script.py\n"
            ),
        )
        parser.add_argument(
            "--cmd",
            nargs=argparse.REMAINDER,
            required=True,
            help="Command to run",
        )
        parser.add_argument(
            "--db_path",
            type=str,
            default=None,
            help="Db file in case of SQLite",
        )
        parser.add_argument(
            "--use_postgres",
            action="store_true",
            help="Use PostgreSQL as SQL system (default=SQLite)",
        )
        args = parser.parse_args()

        if args.db_path is not None and args.use_postgres:
            logger.warning("db_path will be ignored since precedence is given to PostgreSQL")

        self.db = self.db_type(
            db_path=args.db_path,
            use_postgres=args.use_postgres
        )

        app = Application.builder().token(self.bot_token).build()
        app.add_handler(CommandHandler("start", self.start))
        app.add_handler(CommandHandler("clearchat", self.clearchat))
        app.add_handler(CommandHandler("stats", self.stats))

        await app.initialize()
        await app.start()
        assert app.updater is not None
        await app.updater.start_polling()
        await asyncio.sleep(2)

        await self.run_with_notification(
            command=args.cmd, bot=app.bot, log_path=self.log_path
        )

        text_to_update: str = "🤖 Bot still alive for: [{bar}] {current_iter}/{total} [seconds]"
        for i in range(int(self.alive_period) + 1):
            bar = self.progress_bar(current=i, total=int(self.alive_period))
            self.display_progress_bar(
                fmt=text_to_update,
                bar=bar,
                current_iter=str(i),
                total=self.alive_period
            )
            await asyncio.sleep(delay=1)

        print("\n")

        await app.updater.stop()
        await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    setup_logger()
    load_dotenv()
    nb: NotifyBot = NotifyBot(db_type=DatabaseManager)
    asyncio.run(nb.main())
