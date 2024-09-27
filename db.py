import logging
import sqlite3
from typing import Optional

# Class to handle SQLite database operations
class SQLiteDB:
    def __init__(self, db_name: str = "lost_and_found.db"):
        self.db_name = db_name
        self._create_tables()

    def _connect(self):
        """Helper method to connect to the database."""
        return sqlite3.connect(self.db_name)

    def _create_tables(self):
        """Create necessary tables if they don't exist."""
        with self._connect() as conn:
            cursor = conn.cursor()
            # Table for lost/found applications
            cursor.execute('''CREATE TABLE IF NOT EXISTS applications (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                user_id INTEGER,
                                item_type TEXT,
                                description TEXT,
                                location TEXT,
                                image_url TEXT,
                                contact TEXT,
                                status TEXT DEFAULT 'pending'
                            )''')
            # Table for tracking users who interact with the bot
            cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                                user_id INTEGER PRIMARY KEY,
                                username TEXT,
                                first_name TEXT,
                                last_name TEXT
                            )''')
            conn.commit()

    def user_exists(self, user_id: int) -> bool:
        """Check if a user already exists in the database."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''SELECT COUNT(1) FROM users WHERE user_id = ?''', (user_id,))
            return cursor.fetchone()[0] > 0

    def save_user(self, user_id: int, username: Optional[str], first_name: Optional[str], last_name: Optional[str]):
        """Save or update user details only if the user does not exist."""
        if not self.user_exists(user_id):
            with self._connect() as conn:
                cursor = conn.cursor()
                cursor.execute('''INSERT INTO users (user_id, username, first_name, last_name)
                                  VALUES (?, ?, ?, ?)''', (user_id, username, first_name, last_name))
                conn.commit()
        else:
            logging.info(f"User {user_id} is already registered. Skipping save.")


    def save_application(self, user_id: int, item_type: str, description: str, location: str, contact: str, image_url: Optional[str] = None):
        """Save a new lost/found application to the database, with optional image."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO applications (user_id, item_type, description, location, contact, image_url)
                              VALUES (?, ?, ?, ?, ?, ?)''', (user_id, item_type, description, location, contact, image_url))
            conn.commit()
            return cursor.lastrowid


    def get_application_by_id(self, application_id: int) -> Optional[dict]:
        """Retrieve an application by its ID."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM applications WHERE id = ?", (application_id,))
            row = cursor.fetchone()
            if row:
                return {
                    "id": row[0],
                    "user_id": row[1],
                    "item_type": row[2],
                    "description": row[3],
                    "location": row[4],
                    "image_url": row[5],
                    "contact": row[6],
                    "status": row[7]
                }
            return None

    def update_application_status(self, application_id: int, status: str):
        """Update the status of an application (e.g., approved/rejected)."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))
            conn.commit()

    def get_pending_applications(self):
        """Retrieve all applications that are pending approval."""
        with self._connect() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM applications WHERE status = 'pending'")
            return cursor.fetchall()
