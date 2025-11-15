import os
import logging
import sqlite3

from datetime import datetime
from typing import Optional
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages database operations for notification history."""

    def __init__(self, db_path: Optional[str] = None, use_postgres: bool = False):
        """
        Initialize database manager.

        Parameters
        ----------
        db_path : str, optional
            Path to SQLite database file. If None, uses 'notifications.db'
        use_postgres : bool
            If True, uses PostgreSQL (requires DATABASE_URL env var)
        """
        self.use_postgres = use_postgres
        self.placeholder = "%s" if use_postgres else "?"

        if use_postgres:
            try:
                import psycopg2
                from psycopg2.extras import RealDictCursor

                self.psycopg2 = psycopg2
                self.RealDictCursor = RealDictCursor
            except ImportError:
                raise ImportError(
                    "psycopg2 not installed. Install psycopg2-binary via pip"
                )

            self.USER = os.getenv("user") or os.getenv("PGUSER")
            self.PASSWORD = os.getenv("password") or os.getenv("PGPASSWORD")
            self.HOST = os.getenv("host") or os.getenv("PGHOST")
            self.PORT = os.getenv("port") or os.getenv("PGPORT", "5432")
            self.DBNAME = os.getenv("dbname") or os.getenv("PGDATABASE")
            self._init_postgres_db()
        else:
            self.db_path = db_path or "notifications.db"
            self._init_sqlite_db()

    def _init_postgres_db(self):
        """Initialize PostgreSQL database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id SERIAL PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    command TEXT NOT NULL,
                    device_name TEXT,
                    os_name TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_id 
                ON notifications(chat_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON notifications(timestamp DESC)
            """)
            conn.commit()

    def _init_sqlite_db(self):
        """Initialize SQLite database with required schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    command TEXT NOT NULL,
                    device_name TEXT,
                    os_name TEXT,
                    status TEXT DEFAULT 'completed',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_id 
                ON notifications(chat_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp 
                ON notifications(timestamp DESC)
            """)
            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        if self.use_postgres:
            conn = self.psycopg2.connect(
                user=self.USER,
                password=self.PASSWORD,
                host=self.HOST,
                port=self.PORT,
                dbname=self.DBNAME,
                sslmode="require",
                connect_timeout= 10
            )
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def add_notification(
        self,
        chat_id: str,
        message_id: int,
        command: str,
        device_name: Optional[str] = None,
        os_name: Optional[str] = None,
        status: str = "completed",
    ) -> Optional[int]:
        """Add a notification to the database."""
        timestamp = datetime.now().isoformat()
        values = (chat_id, message_id, timestamp, command, device_name, os_name, status)
        placeholders = ", ".join([self.placeholder] * len(values))

        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                f"""
                INSERT INTO notifications 
                (chat_id, message_id, timestamp, command, device_name, os_name, status)
                VALUES ({placeholders})
                """,
                values,
            )

            return cursor.lastrowid

    def get_notifications_for_chat(
        self, chat_id: str, limit: Optional[int] = None
    ) -> list[dict]:
        """
        Retrieve all notifications for a specific chat.

        Parameters
        ----------
        chat_id : str
            The chat ID to retrieve notifications for
        limit : int, optional
            Maximum number of notifications to retrieve

        Returns
        -------
        list[dict]
            List of notification records
        """

        with self._get_connection() as conn:
            cursor = (
                conn.cursor(cursor_factory=self.RealDictCursor) # type: ignore
                if self.use_postgres
                else conn.cursor()
            )

            query = f"""
                SELECT * FROM notifications 
                WHERE chat_id = {self.placeholder}
                ORDER BY timestamp DESC
            """
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query, (chat_id,))

            return [dict(row) for row in cursor.fetchall()]

    def delete_notifications_for_chat(self, chat_id: str) -> int:
        """
        Delete all notification records for a chat.

        Returns
        -------
        int
            Number of records deleted
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"DELETE FROM notifications WHERE chat_id = {self.placeholder}",
                (chat_id,),
            )
            return cursor.rowcount

    def get_statistics(self) -> dict:
        """Get usage statistics from the database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT 
                    COUNT(*) as total_notifications,
                    COUNT(DISTINCT chat_id) as unique_chats,
                    COUNT(DISTINCT device_name) as unique_devices
                    COUNT(DISTINCT os_name) as unique_os
                FROM notifications
            """
            )
            row = cursor.fetchone() # fetech all together
            return dict(row) if row else {}
