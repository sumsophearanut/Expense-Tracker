"""SQLite data layer: users, transactions, budgets, goals."""
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager

import pandas as pd

DB_PATH = os.environ.get("EXPENSE_DB", "expense_tracker.db")


@contextmanager
def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db():
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT, full_name TEXT,
            user_type TEXT DEFAULT 'Young Adult',
            currency TEXT DEFAULT '$',
            password_hash TEXT NOT NULL, salt TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS transactions(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            date TEXT NOT NULL, type TEXT NOT NULL, category TEXT NOT NULL,
            description TEXT, amount REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS budgets(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            category TEXT NOT NULL, monthly_limit REAL NOT NULL,
            UNIQUE(user_id, category));
        CREATE TABLE IF NOT EXISTS goals(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL, target_amount REAL NOT NULL,
            saved_amount REAL DEFAULT 0, deadline TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)


# ------------------------------------------------------------------ users
def _hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()


def register_user(username, email, password, full_name, user_type):
    username = username.strip().lower()
    if len(username) < 3:
        return False, "Username must be at least 3 characters."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if email and "@" not in email:
        return False, "Please enter a valid email."
    salt = secrets.token_hex(16)
    try:
        with conn() as c:
            c.execute("INSERT INTO users(username,email,full_name,user_type,password_hash,salt) "
                      "VALUES(?,?,?,?,?,?)",
                      (username, email.strip(), full_name.strip(), user_type, _hash(password, salt), salt))
    except sqlite3.IntegrityError:
        return False, "That username is already taken."
    return True, "Account created. You can log in now."


def authenticate(username, password):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (username.strip().lower(),)).fetchone()
    if row and hmac.compare_digest(row["password_hash"], _hash(password, row["salt"])):
        return dict(row)
    return None


def get_user(user_id):
    with conn() as c:
        row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


def update_profile(user_id, full_name, email, user_type, currency):
    with conn() as c:
        c.execute("UPDATE users SET full_name=?, email=?, user_type=?, currency=? WHERE id=?",
                  (full_name.strip(), email.strip(), user_type, currency, user_id))


def change_password(user_id, old, new):
    u = get_user(user_id)
    if not u or not hmac.compare_digest(u["password_hash"], _hash(old, u["salt"])):
        return False, "Current password is incorrect."
    if len(new) < 6:
        return False, "New password must be at least 6 characters."
    salt = secrets.token_hex(16)
    with conn() as c:
        c.execute("UPDATE users SET password_hash=?, salt=? WHERE id=?", (_hash(new, salt), salt, user_id))
    return True, "Password updated."


def delete_user(user_id):
    with conn() as c:
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


# ----------------------------------------------------------- transactions
def add_transaction(user_id, date, ttype, category, description, amount):
    with conn() as c:
        c.execute("INSERT INTO transactions(user_id,date,type,category,description,amount) VALUES(?,?,?,?,?,?)",
                  (user_id, str(date), ttype, category, description, float(amount)))


def bulk_add(user_id, df):
    with conn() as c:
        c.executemany(
            "INSERT INTO transactions(user_id,date,type,category,description,amount) VALUES(?,?,?,?,?,?)",
            [(user_id, str(pd.Timestamp(r.date).date()), r.type, r.category, r.description, float(r.amount))
             for r in df.itertuples()])


def update_transaction(tx_id, user_id, date, ttype, category, description, amount):
    with conn() as c:
        c.execute("UPDATE transactions SET date=?,type=?,category=?,description=?,amount=? "
                  "WHERE id=? AND user_id=?",
                  (str(date), ttype, category, description, float(amount), tx_id, user_id))


def delete_transaction(tx_id, user_id):
    with conn() as c:
        c.execute("DELETE FROM transactions WHERE id=? AND user_id=?", (tx_id, user_id))


def get_transactions(user_id):
    with conn() as c:
        df = pd.read_sql_query(
            "SELECT id,date,type,category,description,amount FROM transactions "
            "WHERE user_id=? ORDER BY date DESC, id DESC", c, params=(user_id,))
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------- budgets
def set_budget(user_id, category, limit):
    with conn() as c:
        c.execute("INSERT INTO budgets(user_id,category,monthly_limit) VALUES(?,?,?) "
                  "ON CONFLICT(user_id,category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
                  (user_id, category, float(limit)))


def delete_budget(budget_id, user_id):
    with conn() as c:
        c.execute("DELETE FROM budgets WHERE id=? AND user_id=?", (budget_id, user_id))


def get_budgets(user_id):
    with conn() as c:
        return pd.read_sql_query("SELECT id,category,monthly_limit FROM budgets WHERE user_id=? ORDER BY category",
                                 c, params=(user_id,))


# ------------------------------------------------------------------ goals
def add_goal(user_id, name, target, saved, deadline):
    with conn() as c:
        c.execute("INSERT INTO goals(user_id,name,target_amount,saved_amount,deadline) VALUES(?,?,?,?,?)",
                  (user_id, name.strip(), float(target), float(saved), str(deadline) if deadline else None))


def add_to_goal(goal_id, user_id, amount):
    with conn() as c:
        c.execute("UPDATE goals SET saved_amount = MAX(saved_amount + ?, 0) WHERE id=? AND user_id=?",
                  (float(amount), goal_id, user_id))


def delete_goal(goal_id, user_id):
    with conn() as c:
        c.execute("DELETE FROM goals WHERE id=? AND user_id=?", (goal_id, user_id))


def get_goals(user_id):
    with conn() as c:
        return pd.read_sql_query("SELECT * FROM goals WHERE user_id=? ORDER BY id", c, params=(user_id,))
