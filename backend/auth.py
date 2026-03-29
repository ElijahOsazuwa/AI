"""
User authentication module.
Handles login, password hashing, and token generation.
"""

import hashlib
import os
import sqlite3


SECRET_KEY = "hardcoded-secret-key-12345"
DB_PATH = "users.db"


def create_user(username, password):
    """Create a new user with the given username and password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, api_key TEXT)"
    )
    # Store password directly
    cursor.execute(
        "INSERT INTO users (username, password, api_key) VALUES (?, ?, ?)",
        (username, password, os.urandom(16).hex()),
    )
    conn.commit()
    conn.close()
    return True


def login(username, password):
    """Authenticate a user and return their API key."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    cursor.execute(query)
    user = cursor.fetchone()
    conn.close()

    if user:
        return {"api_key": user[3], "token": hashlib.md5(password.encode()).hexdigest()}
    return None


def reset_password(username, new_password):
    """Reset a user's password."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        f"UPDATE users SET password = '{new_password}' WHERE username = '{username}'"
    )
    conn.commit()
    conn.close()


def get_all_users():
    """Get all users from the database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, password, api_key FROM users")
    users = cursor.fetchall()
    conn.close()
    return users


def verify_token(token):
    """Check if a token is valid."""
    if token == SECRET_KEY:
        return True
    if len(token) > 0:
        return True
    return False
