import copy
import csv
import json
import logging
import os
import re
import secrets
import socket
import sqlite3
import urllib.request
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field, field_validator

app = FastAPI(title="Capacity Forecaster API", version="1.0.0")
logger = logging.getLogger("capacity_forecaster")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://localhost:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
# Load environment variables
load_dotenv(dotenv_path=BASE_DIR / ".env")
load_dotenv(dotenv_path=BASE_DIR.parent / ".env")
logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

DATA_PATH = BASE_DIR.parent / "data" / "enhanced_resource_metrics.csv"
HISTORY_DIR = BASE_DIR.parent / "data" / "history"
DB_PATH = BASE_DIR.parent / "data" / "capacity_forecast.db"
MAX_HISTORY_ITEMS = 50
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "30"))
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
MAX_LLM_PROMPT_CHARS = int(os.getenv("MAX_LLM_PROMPT_CHARS", "20000"))
INVALID_API_KEYS = {
    "",
    "your_gemini_api_key_here",
    "dummy_api_key",
    "placeholder",
    "paste_your_api_key_here",
}
MASKED_KEY_RE = re.compile(r"^\*{4,}\w{0,8}$")

DEFAULT_SETTINGS = {
    "forecast_days": 60,
    "forecast_method": "auto",
    "theme": "light",
    "alert_thresholds": {
        "cpu_usage": 85,
        "memory_usage": 80,
        "disk_usage": 80,
    },
    "email_alerts": False,
    "compact_mode": False,
}

USERS: dict[str, dict] = {}
SESSIONS: dict[str, str] = {}


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or only spaces")
        if not re.match(r"^[a-zA-Z\s\-']+$", v):
            raise ValueError("Name must contain only letters, spaces, hyphens, or apostrophes")
        return v

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForecastRequest(BaseModel):
    question: str
    forecast_days: int = 60
    method: str = "auto"


class SettingsUpdate(BaseModel):
    forecast_days: Optional[int] = None
    forecast_method: Optional[str] = None
    theme: Optional[str] = None
    alert_thresholds: Optional[dict[str, float]] = None
    email_alerts: Optional[bool] = None
    compact_mode: Optional[bool] = None
    api_key: Optional[str] = None


class ProfileUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Name cannot be empty or only spaces")
        if not re.match(r"^[a-zA-Z\s\-']+$", v):
            raise ValueError("Name must contain only letters, spaces, hyphens, or apostrophes")
        return v


class PasswordUpdate(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.islower() for c in v):
            raise ValueError("Password must contain at least one lowercase letter")
        return v


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrent read/write performance
    conn.execute("PRAGMA journal_mode=WAL")
    # Enable foreign key constraint enforcement
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def db_init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Check if users table is using the old schema (does not have an 'id' column)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
        table_exists = cursor.fetchone()

        if table_exists:
            cursor.execute("PRAGMA table_info(users)")
            columns = [row["name"] for row in cursor.fetchall()]
            if "id" not in columns:
                print("[DB] Old schema detected. Recreating database tables...")
                cursor.execute("DROP TABLE IF EXISTS history")
                cursor.execute("DROP TABLE IF EXISTS sessions")
                cursor.execute("DROP TABLE IF EXISTS settings")
                cursor.execute("DROP TABLE IF EXISTS users")
                conn.commit()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                password TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                user_id INTEGER PRIMARY KEY,
                forecast_days INTEGER DEFAULT 60,
                forecast_method TEXT DEFAULT 'auto',
                theme TEXT DEFAULT 'light',
                email_alerts INTEGER DEFAULT 0,
                compact_mode INTEGER DEFAULT 0,
                cpu_threshold REAL DEFAULT 85,
                memory_threshold REAL DEFAULT 80,
                disk_threshold REAL DEFAULT 80,
                api_key TEXT DEFAULT '',
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                metric TEXT NOT NULL,
                threshold REAL NOT NULL,
                crossing_date TEXT,
                forecast_engine TEXT NOT NULL,
                forecast_days INTEGER NOT NULL,
                method TEXT NOT NULL,
                created_at TEXT NOT NULL,
                details_json TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metrics (
                date TEXT PRIMARY KEY,
                server_id TEXT,
                environment TEXT,
                region TEXT,
                cpu_usage REAL,
                memory_usage REAL,
                disk_usage REAL,
                network_in_mb REAL,
                network_out_mb REAL,
                requests_per_min REAL,
                active_users REAL,
                response_time_ms REAL,
                error_rate_percent REAL
            )
        """)

        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            # Seed admin user with a hashed password
            admin_password = "admin123"
            hashed_pw = bcrypt.hashpw(admin_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

            cursor.execute(
                "INSERT INTO users (email, name, password) VALUES (?, ?, ?)",
                ("admin@example.com", "Admin", hashed_pw)
            )
            admin_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO settings (user_id) VALUES (?)",
                (admin_id,)
            )
            conn.commit()

        cursor.execute("SELECT COUNT(*) FROM metrics")
        if cursor.fetchone()[0] == 0:
            seed_metrics(conn)

        # Clean up expired sessions on startup
        cursor.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (datetime.now().isoformat(),)
        )
        conn.commit()
        print(f"[DB] Initialized successfully. Path: {DB_PATH.resolve()}")
    finally:
        conn.close()


def seed_metrics(conn):
    rows = []
    if DATA_PATH.exists():
        try:
            with DATA_PATH.open("r", newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                for row in reader:
                    rows.append(row)
        except Exception:
            pass
    if not rows:
        rows = generate_rows()

    cursor = conn.cursor()
    for row in rows:
        cursor.execute("""
            INSERT OR REPLACE INTO metrics (
                date, server_id, environment, region, cpu_usage, memory_usage, disk_usage,
                network_in_mb, network_out_mb, requests_per_min, active_users, response_time_ms, error_rate_percent
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row.get("date") or row.get("Date"),
            row.get("server_id", "app-server-01"),
            row.get("environment", "production"),
            row.get("region", "ap-south-1"),
            float(row.get("cpu_usage") or row.get("CPU") or 0),
            float(row.get("memory_usage") or row.get("Memory") or 0),
            float(row.get("disk_usage") or row.get("Disk") or 0),
            float(row.get("network_in_mb") or 0),
            float(row.get("network_out_mb") or 0),
            float(row.get("requests_per_min") or 0),
            float(row.get("active_users") or 0),
            float(row.get("response_time_ms") or 0),
            float(row.get("error_rate_percent") or 0)
        ))
    conn.commit()


def migrate_json_history():
    if not HISTORY_DIR.exists():
        return
    with get_db_connection() as conn:
        cursor = conn.cursor()
        for filepath in HISTORY_DIR.glob("*.json"):
            email = filepath.stem.replace("_at_", "@").replace("_", ".")

            # Get user ID or insert new user
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            user_row = cursor.fetchone()
            if not user_row:
                hashed_pw = bcrypt.hashpw("admin123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                cursor.execute(
                    "INSERT INTO users (email, name, password) VALUES (?, ?, ?)",
                    (email, email.split("@")[0].capitalize(), hashed_pw)
                )
                user_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO settings (user_id) VALUES (?)",
                    (user_id,)
                )
                conn.commit()
            else:
                user_id = user_row["id"]

            try:
                with filepath.open("r", encoding="utf-8") as file:
                    items = json.load(file)
                    if isinstance(items, list):
                        for item in items:
                            cursor.execute("SELECT COUNT(*) FROM history WHERE id = ?", (item.get("id"),))
                            if cursor.fetchone()[0] == 0:
                                details = {
                                    "history": item.get("history", []),
                                    "forecast": item.get("forecast", []),
                                    "agent_steps": item.get("agent_steps", [])
                                }
                                cursor.execute("""
                                    INSERT INTO history (
                                        id, user_id, question, answer, metric, threshold,
                                        crossing_date, forecast_engine, forecast_days, method, created_at, details_json
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    item.get("id"),
                                    user_id,
                                    item.get("question"),
                                    item.get("answer"),
                                    item.get("metric"),
                                    item.get("threshold"),
                                    item.get("crossing_date"),
                                    item.get("forecast_engine"),
                                    item.get("forecast_days", 60),
                                    item.get("method", "auto"),
                                    item.get("created_at") or datetime.now().isoformat(),
                                    json.dumps(details)
                                ))
                conn.commit()
            except Exception as e:
                print(f"Error migrating history file {filepath}: {e}")


db_init()
try:
    migrate_json_history()
except Exception as e:
    print(f"Error migrating history: {e}")


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = authorization.split(" ", 1)[1]
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT u.id, u.name, u.email, s.expires_at FROM sessions s JOIN users u ON s.user_id = u.id WHERE s.token = ?", (token,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid or expired session")

        # Enforce session expiry
        if row["expires_at"] < datetime.now().isoformat():
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
            raise HTTPException(status_code=401, detail="Session expired, please log in again")

        return {"id": row["id"], "name": row["name"], "email": row["email"]}
    finally:
        conn.close()


class LLMError(ValueError):
    def __init__(self, provider: str, message: str, status_code: Optional[int] = None, retryable: bool = False):
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.retryable = retryable
        self.public_message = message


def mask_api_key(api_key: Optional[str]) -> str:
    key = (api_key or "").strip()
    if not key:
        return ""
    return f"****{key[-6:]}" if len(key) > 6 else "****"


def is_masked_api_key(api_key: Optional[str]) -> bool:
    return bool(api_key and MASKED_KEY_RE.match(api_key.strip()))


def is_placeholder_api_key(api_key: Optional[str]) -> bool:
    key = (api_key or "").strip()
    if not key:
        return True
    key_lower = key.lower()
    return key_lower in INVALID_API_KEYS or "placeholder" in key_lower


def detect_api_provider(api_key: Optional[str]) -> Optional[str]:
    key = (api_key or "").strip()
    if is_placeholder_api_key(key) or is_masked_api_key(key):
        return None
    if key.startswith("sk-or-"):
        return "openrouter"
    if key.startswith("sk-"):
        return "openai"
    if key.startswith("AIza") or key.startswith("AQ."):
        return "gemini"
    return None


def validate_api_key_format(api_key: Optional[str]) -> tuple[bool, Optional[str], str]:
    if is_placeholder_api_key(api_key):
        return False, None, "API key is missing."
    if is_masked_api_key(api_key):
        return False, None, "Masked API key cannot be used as a new key."
    provider = detect_api_provider(api_key)
    if not provider:
        return (
            False,
            None,
            "Unsupported API key format. Use a Gemini key from Google AI Studio, an OpenAI key starting with sk-, or an OpenRouter key starting with sk-or-.",
        )
    return True, provider, "API key format is valid."


def resolve_configured_api_key(user_settings: dict) -> Optional[str]:
    env_candidates = [
        os.getenv("OPENROUTER_API_KEY"),
        os.getenv("OPENAI_API_KEY"),
        os.getenv("GEMINI_API_KEY"),
        os.getenv("GOOGLE_API_KEY"),
        os.getenv("LLM_API_KEY"),
    ]
    for candidate in env_candidates:
        valid, provider, _ = validate_api_key_format(candidate)
        if valid:
            logger.info("Using %s API key from environment", provider)
            return candidate.strip()
        if candidate and not is_placeholder_api_key(candidate):
            logger.warning("Ignoring environment API key with unsupported format")

    stored_key = user_settings.get("api_key")
    valid, provider, _ = validate_api_key_format(stored_key)
    if valid:
        logger.info("Using %s API key from user settings", provider)
        return stored_key.strip()
    return None


def get_user_settings(user_id: int, mask_secret: bool = False) -> dict:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("INSERT OR IGNORE INTO settings (user_id) VALUES (?)", (user_id,))
            conn.commit()
            cursor.execute("SELECT * FROM settings WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

        api_key = row["api_key"] or ""
        return {
            "forecast_days": row["forecast_days"],
            "forecast_method": row["forecast_method"],
            "theme": row["theme"],
            "email_alerts": bool(row["email_alerts"]),
            "compact_mode": bool(row["compact_mode"]),
            "alert_thresholds": {
                "cpu_usage": row["cpu_threshold"],
                "memory_usage": row["memory_threshold"],
                "disk_usage": row["disk_threshold"],
            },
            "api_key": mask_api_key(api_key) if mask_secret else api_key,
        }
    finally:
        conn.close()


def load_user_history(user_id: int) -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM history
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (user_id, MAX_HISTORY_ITEMS))
        rows = cursor.fetchall()

        history_list = []
        for row in rows:
            try:
                details = json.loads(row["details_json"])
            except Exception:
                details = {}

            history_list.append({
                "id": row["id"],
                "created_at": row["created_at"],
                "question": row["question"],
                "answer": row["answer"],
                "metric": row["metric"],
                "threshold": row["threshold"],
                "crossing_date": row["crossing_date"],
                "forecast_engine": row["forecast_engine"],
                "forecast_days": row["forecast_days"],
                "method": row["method"],
                **details,
            })
        return history_list
    finally:
        conn.close()


def add_history_entry(user_id: int, entry: dict) -> dict:
    record_id = secrets.token_urlsafe(8)
    created_at = datetime.now().isoformat()

    details = {
        "history": entry.get("history", []),
        "forecast": entry.get("forecast", []),
        "agent_steps": entry.get("agent_steps", []),
    }

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO history (
                id, user_id, question, answer, metric, threshold,
                crossing_date, forecast_engine, forecast_days, method, created_at, details_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            record_id,
            user_id,
            entry["question"],
            entry["answer"],
            entry["metric"],
            entry["threshold"],
            entry.get("crossing_date"),
            entry["forecast_engine"],
            entry["forecast_days"],
            entry["method"],
            created_at,
            json.dumps(details),
        ))
        conn.commit()
    finally:
        conn.close()

    return {
        "id": record_id,
        "created_at": created_at,
        **entry,
    }


def load_rows() -> list[dict]:
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM metrics ORDER BY date ASC")
        rows = cursor.fetchall()

        results = [dict(row) for row in rows]

        if not results:
            seed_metrics(conn)
            cursor.execute("SELECT * FROM metrics ORDER BY date ASC")
            results = [dict(r) for r in cursor.fetchall()]

        return results
    finally:
        conn.close()


def generate_rows() -> list[dict]:
    rows = []
    start = datetime(2024, 1, 1)

    for i in range(220):
        day = start + timedelta(days=i)
        rows.append({
            "date": day.strftime("%Y-%m-%d"),
            "server_id": "app-server-01",
            "environment": "production",
            "region": "ap-south-1",
            "cpu_usage": round(30 + i * 0.16, 2),
            "memory_usage": round(42 + i * 0.13, 2),
            "disk_usage": round(35 + i * 0.20, 2),
            "network_in_mb": round(120 + i * 0.6, 2),
            "network_out_mb": round(95 + i * 0.5, 2),
            "requests_per_min": round(800 + i * 3.5),
            "active_users": round(180 + i * 1.2),
            "response_time_ms": round(220 + i * 0.45, 2),
            "error_rate_percent": round(0.4 + i * 0.01, 2),
        })

    return rows


def normalize_row(row: dict) -> dict:
    return {
        "date": row.get("date") or row.get("Date"),
        "cpu_usage": row.get("cpu_usage") or row.get("CPU"),
        "memory_usage": row.get("memory_usage") or row.get("Memory"),
        "disk_usage": row.get("disk_usage") or row.get("Disk"),
    }


def parse_question(question: str) -> tuple[str, float]:
    text = question.lower()

    if "cpu" in text or "processor" in text:
        metric = "cpu_usage"
    elif any(word in text for word in ("memory", "ram", "mem")):
        metric = "memory_usage"
    elif any(word in text for word in ("disk", "storage", "drive")):
        metric = "disk_usage"
    else:
        raise ValueError("Ask about CPU, memory, or disk usage.")

    match = re.search(r"(\d+(?:\.\d+)?)", text)
    if not match:
        raise ValueError("Include a percentage threshold, e.g. 'When does disk hit 80%?'")

    threshold = float(match.group(1))
    if threshold <= 0 or threshold > 100:
        raise ValueError("Threshold must be between 1 and 100.")

    return metric, threshold


def prepare_series(rows: list[dict], metric: str) -> list[dict]:
    clean = []

    for row in rows:
        item = normalize_row(row)
        if not item["date"] or not item[metric]:
            continue

        try:
            clean.append({
                "date": datetime.strptime(str(item["date"])[:10], "%Y-%m-%d"),
                metric: float(item[metric]),
            })
        except (TypeError, ValueError):
            continue

    clean.sort(key=lambda x: x["date"])
    if len(clean) < 2:
        raise ValueError("Need at least 2 valid data rows for forecasting.")

    return clean


def linear_forecast(clean: list[dict], metric: str, threshold: float, days: int):
    start = clean[0]["date"]
    x_values = [(row["date"] - start).days for row in clean]
    y_values = [row[metric] for row in clean]

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    numerator = sum((x_values[i] - x_mean) * (y_values[i] - y_mean) for i in range(len(x_values)))
    denominator = sum((x - x_mean) ** 2 for x in x_values)

    slope = numerator / denominator if denominator else 0
    intercept = y_mean - slope * x_mean

    last_day = max(x_values)
    forecast = []
    crossing_date = None

    for day in range(last_day + 1, last_day + days + 1):
        predicted = intercept + slope * day
        predicted = max(0, min(100, predicted))
        date = start + timedelta(days=day)

        forecast.append({
            "date": date.strftime("%Y-%m-%d"),
            "predicted_usage": round(predicted, 2),
        })

        if crossing_date is None and predicted >= threshold:
            crossing_date = date.strftime("%Y-%m-%d")

    return forecast, crossing_date, "linear_regression"


def arima_forecast(clean: list[dict], metric: str, threshold: float, days: int):
    try:
        import pandas as pd
        from statsmodels.tsa.arima.model import ARIMA
    except ImportError as exc:
        raise ValueError("ARIMA dependencies not installed.") from exc

    series = pd.Series(
        [row[metric] for row in clean],
        index=pd.to_datetime([row["date"] for row in clean]),
    )

    model = ARIMA(series, order=(1, 1, 1))
    fitted = model.fit()
    predictions = fitted.forecast(steps=days)

    last_date = clean[-1]["date"]
    forecast = []
    crossing_date = None

    for i, predicted in enumerate(predictions, start=1):
        predicted = max(0, min(100, float(predicted)))
        date = (last_date + timedelta(days=i)).strftime("%Y-%m-%d")

        forecast.append({
            "date": date,
            "predicted_usage": round(predicted, 2),
        })

        if crossing_date is None and predicted >= threshold:
            crossing_date = date

    return forecast, crossing_date, "arima"


def run_forecast(rows: list[dict], metric: str, threshold: float, days: int, method: str):
    clean = prepare_series(rows, metric)

    if method == "linear":
        forecast, crossing_date, engine = linear_forecast(clean, metric, threshold, days)
    elif method == "arima":
        forecast, crossing_date, engine = arima_forecast(clean, metric, threshold, days)
    else:
        try:
            forecast, crossing_date, engine = arima_forecast(clean, metric, threshold, days)
        except Exception:
            forecast, crossing_date, engine = linear_forecast(clean, metric, threshold, days)

    history = [
        {
            "date": row["date"].strftime("%Y-%m-%d"),
            "usage": round(row[metric], 2),
        }
        for row in clean
    ]

    return history, forecast, crossing_date, engine


def compute_health(rows: list[dict], thresholds: dict[str, float]) -> dict:
    latest = normalize_row(rows[-1]) if rows else {}
    alerts = []
    scores = []

    metric_labels = {
        "cpu_usage": "CPU",
        "memory_usage": "Memory",
        "disk_usage": "Disk",
    }

    for metric, label in metric_labels.items():
        value = float(latest.get(metric) or 0)
        threshold = float(thresholds.get(metric, 80))
        headroom = max(0, threshold - value)
        score = max(0, min(100, round((headroom / threshold) * 100, 1)))
        scores.append(score)

        status = "healthy"
        if value >= threshold:
            status = "critical"
        elif value >= threshold * 0.9:
            status = "warning"

        if status != "healthy":
            alerts.append({
                "metric": metric,
                "label": label,
                "value": round(value, 2),
                "threshold": threshold,
                "status": status,
                "message": f"{label} at {value:g}% (threshold {threshold:g}%)",
            })

    overall = round(sum(scores) / len(scores), 1) if scores else 100
    grade = "Excellent" if overall >= 80 else "Good" if overall >= 60 else "At Risk" if overall >= 40 else "Critical"

    return {
        "score": overall,
        "grade": grade,
        "alerts": alerts,
        "latest": {
            "cpu_usage": latest.get("cpu_usage"),
            "memory_usage": latest.get("memory_usage"),
            "disk_usage": latest.get("disk_usage"),
        },
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "capacity-forecaster"}


@app.post("/auth/register")
def register(payload: RegisterRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users WHERE email = ?", (payload.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        hashed_pw = bcrypt.hashpw(payload.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            "INSERT INTO users (email, name, password) VALUES (?, ?, ?)",
            (payload.email, payload.name, hashed_pw),
        )
        user_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO settings (user_id) VALUES (?)",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()
    return {"message": "Registered successfully"}


@app.post("/auth/login")
def login(payload: LoginRequest):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, password FROM users WHERE email = ?", (payload.email,))
        row = cursor.fetchone()
        if not row or not bcrypt.checkpw(payload.password.encode('utf-8'), row["password"].encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        user_id = row["id"]
        token = secrets.token_urlsafe(32)
        expires_at = (datetime.now() + timedelta(days=7)).isoformat()

        # Clean up any expired sessions for this user before creating a new one
        cursor.execute(
            "DELETE FROM sessions WHERE user_id = ? AND expires_at < ?",
            (user_id, datetime.now().isoformat()),
        )
        cursor.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()

        return {
            "access_token": token,
            "user": {"name": row["name"], "email": payload.email},
        }
    finally:
        conn.close()


@app.post("/auth/logout")
def logout(user: dict = Depends(get_current_user), authorization: Optional[str] = Header(None)):
    token = authorization.split(" ", 1)[1] if authorization else None
    if token:
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sessions WHERE token = ?", (token,))
            conn.commit()
        finally:
            conn.close()
    return {"message": "Logged out successfully"}


@app.get("/auth/me")
def me(user: dict = Depends(get_current_user)):
    return user


@app.put("/auth/profile")
def update_profile(payload: ProfileUpdate, user: dict = Depends(get_current_user)):
    name_stripped = payload.name.strip()
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET name = ? WHERE id = ?", (name_stripped, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Profile updated", "user": {"name": name_stripped, "email": user["email"]}}


@app.put("/auth/password")
def update_password(payload: PasswordUpdate, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM users WHERE id = ?", (user["id"],))
        row = cursor.fetchone()
        if not row or not bcrypt.checkpw(payload.current_password.encode('utf-8'), row["password"].encode('utf-8')):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        hashed_new_pw = bcrypt.hashpw(payload.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute("UPDATE users SET password = ? WHERE id = ?", (hashed_new_pw, user["id"]))
        conn.commit()
    finally:
        conn.close()
    return {"message": "Password updated successfully"}


@app.get("/settings")
def get_settings(user: dict = Depends(get_current_user)):
    return get_user_settings(user["id"], mask_secret=True)


@app.put("/settings")
def update_settings(payload: SettingsUpdate, user: dict = Depends(get_current_user)):
    settings = get_user_settings(user["id"])

    forecast_days = max(7, min(365, payload.forecast_days)) if payload.forecast_days is not None else settings["forecast_days"]
    forecast_method = payload.forecast_method if payload.forecast_method is not None else settings["forecast_method"]
    theme = payload.theme if payload.theme is not None else settings["theme"]
    email_alerts = int(payload.email_alerts) if payload.email_alerts is not None else int(settings["email_alerts"])
    compact_mode = int(payload.compact_mode) if payload.compact_mode is not None else int(settings["compact_mode"])

    cpu_threshold = settings["alert_thresholds"]["cpu_usage"]
    memory_threshold = settings["alert_thresholds"]["memory_usage"]
    disk_threshold = settings["alert_thresholds"]["disk_usage"]

    if payload.alert_thresholds is not None:
        cpu_threshold = payload.alert_thresholds.get("cpu_usage", cpu_threshold)
        memory_threshold = payload.alert_thresholds.get("memory_usage", memory_threshold)
        disk_threshold = payload.alert_thresholds.get("disk_usage", disk_threshold)

    api_key = settings.get("api_key", "")
    if payload.api_key is not None:
        incoming_key = payload.api_key.strip()
        if is_masked_api_key(incoming_key):
            api_key = settings.get("api_key", "")
        elif incoming_key:
            valid_key, _, key_message = validate_api_key_format(incoming_key)
            if not valid_key:
                raise HTTPException(status_code=400, detail=key_message)
            api_key = incoming_key
        else:
            api_key = ""

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE settings
            SET forecast_days = ?, forecast_method = ?, theme = ?,
                email_alerts = ?, compact_mode = ?,
                cpu_threshold = ?, memory_threshold = ?, disk_threshold = ?,
                api_key = ?
            WHERE user_id = ?
        """, (
            forecast_days, forecast_method, theme,
            email_alerts, compact_mode,
            cpu_threshold, memory_threshold, disk_threshold,
            api_key,
            user["id"],
        ))
        conn.commit()
    finally:
        conn.close()

    return {"message": "Settings saved", "settings": get_user_settings(user["id"], mask_secret=True)}


@app.get("/metrics")
def metrics(user: dict = Depends(get_current_user)):
    rows = load_rows()
    return rows


@app.get("/metrics/summary")
def metrics_summary(user: dict = Depends(get_current_user)):
    rows = load_rows()
    if not rows:
        return {"rows": 0}

    latest = normalize_row(rows[-1])
    first = normalize_row(rows[0])

    def avg(metric: str) -> float:
        values = [float(normalize_row(r)[metric]) for r in rows if normalize_row(r)[metric]]
        return round(sum(values) / len(values), 2) if values else 0

    return {
        "rows": len(rows),
        "date_range": {
            "start": first.get("date"),
            "end": latest.get("date"),
        },
        "latest": {
            "cpu_usage": latest.get("cpu_usage"),
            "memory_usage": latest.get("memory_usage"),
            "disk_usage": latest.get("disk_usage"),
        },
        "averages": {
            "cpu_usage": avg("cpu_usage"),
            "memory_usage": avg("memory_usage"),
            "disk_usage": avg("disk_usage"),
        },
    }


@app.get("/metrics/trends")
def metrics_trends(user: dict = Depends(get_current_user)):
    rows = load_rows()
    trends = {"cpu_usage": [], "memory_usage": [], "disk_usage": []}

    for row in rows[-30:]:
        item = normalize_row(row)
        if not item["date"]:
            continue
        for metric in trends:
            if item[metric]:
                trends[metric].append({
                    "date": str(item["date"])[:10],
                    "value": round(float(item[metric]), 2),
                })

    return trends


@app.get("/metrics/health")
def metrics_health(user: dict = Depends(get_current_user)):
    rows = load_rows()
    settings = get_user_settings(user["id"])
    health = compute_health(rows, settings["alert_thresholds"])
    health["thresholds"] = settings["alert_thresholds"]
    return health


@app.post("/forecast/quick-scan")
def quick_scan(user: dict = Depends(get_current_user)):
    rows = load_rows()
    settings = get_user_settings(user["id"])
    days = settings["forecast_days"]
    method = settings["forecast_method"]
    results = []

    metric_labels = {
        "cpu_usage": "CPU",
        "memory_usage": "Memory",
        "disk_usage": "Disk",
    }

    for metric, threshold in settings["alert_thresholds"].items():
        try:
            history, forecast, crossing_date, engine = run_forecast(
                rows, metric, float(threshold), days, method
            )
            label = metric_labels.get(metric, metric.replace("_usage", "").title())
            latest = history[-1]["usage"] if history else 0

            if crossing_date:
                answer = f"{label} may hit {threshold:g}% by {crossing_date}"
                risk = "high" if crossing_date else "low"
            else:
                answer = f"{label} safe below {threshold:g}% for {days} days"
                risk = "low"

            if latest >= threshold * 0.9:
                risk = "high"
            elif latest >= threshold * 0.75:
                risk = "medium"

            results.append({
                "metric": metric,
                "label": label,
                "current": latest,
                "threshold": threshold,
                "crossing_date": crossing_date,
                "risk": risk,
                "answer": answer,
                "engine": engine,
            })
        except ValueError:
            continue

    return {"scan_results": results, "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M")}


def retrieve_relevant_metrics(question: str) -> str:
    text = question.lower()
    metric_cols = []

    if "cpu" in text or "processor" in text:
        metric_cols.append(("cpu_usage", "CPU Usage (%)"))
    if any(w in text for w in ("memory", "ram", "mem")):
        metric_cols.append(("memory_usage", "Memory Usage (%)"))
    if any(w in text for w in ("disk", "storage", "drive")):
        metric_cols.append(("disk_usage", "Disk Usage (%)"))
    if any(w in text for w in ("network", "bandwidth", "traffic", "mb")):
        metric_cols.append(("network_in_mb", "Network In (MB)"))
        metric_cols.append(("network_out_mb", "Network Out (MB)"))
    if any(w in text for w in ("request", "load", "rpm")):
        metric_cols.append(("requests_per_min", "Requests/Min"))
    if any(w in text for w in ("user", "visitor", "session")):
        metric_cols.append(("active_users", "Active Users"))
    if any(w in text for w in ("response time", "latency", "duration", "ms")):
        metric_cols.append(("response_time_ms", "Response Time (ms)"))
    if any(w in text for w in ("error", "failure", "fail")):
        metric_cols.append(("error_rate_percent", "Error Rate (%)"))

    if not metric_cols:
        metric_cols = [
            ("cpu_usage", "CPU Usage (%)"),
            ("memory_usage", "Memory Usage (%)"),
            ("disk_usage", "Disk Usage (%)"),
            ("active_users", "Active Users")
        ]

    select_fields = ", ".join([col[0] for col in metric_cols])
    query = f"SELECT date, {select_fields} FROM metrics ORDER BY date DESC LIMIT 15"

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

            headers = ["Date"] + [col[1] for col in metric_cols]
            table_lines = [
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join(["---"] * len(headers)) + " |"
            ]

            for row in reversed(rows):
                vals = [row["date"]]
                for col in metric_cols:
                    val = row[col[0]]
                    vals.append(f"{val:.2f}" if isinstance(val, float) else str(val))
                table_lines.append("| " + " | ".join(vals) + " |")

            return "\n".join(table_lines)
    except Exception as e:
        return f"Error retrieving metrics context: {e}"


def _extract_error_message(error_body: str) -> str:
    try:
        parsed = json.loads(error_body)
    except Exception:
        return ""
    error_obj = parsed.get("error", parsed)
    if isinstance(error_obj, dict):
        message = error_obj.get("message") or error_obj.get("code") or error_obj.get("status")
        return str(message or "")
    return str(error_obj or "")


def _provider_error(provider: str, status_code: Optional[int], detail: str = "") -> LLMError:
    detail_lower = (detail or "").lower()
    if status_code in (401, 403) or "api key not valid" in detail_lower or "invalid api key" in detail_lower:
        return LLMError(provider, f"{provider} API key is invalid, expired, or not authorized.", status_code)
    if status_code == 429 or "quota" in detail_lower or "rate" in detail_lower or "resource_exhausted" in detail_lower:
        return LLMError(provider, f"{provider} quota or rate limit exceeded. Wait for quota reset or use a key/project with available quota.", status_code, retryable=True)
    if status_code and 500 <= status_code <= 599:
        return LLMError(provider, f"{provider} service is temporarily unavailable. Try again later.", status_code, retryable=True)
    if status_code:
        return LLMError(provider, f"{provider} API request failed with HTTP {status_code}.", status_code)
    return LLMError(provider, f"{provider} network request failed. Check internet access and provider status.")


def _post_json(provider: str, url: str, payload: dict, headers: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_SECONDS) as response:
            response_text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        logger.warning("%s API returned HTTP %s: %s", provider, exc.code, _extract_error_message(body))
        raise _provider_error(provider, exc.code, _extract_error_message(body)) from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        logger.warning("%s API network/timeout failure: %s", provider, exc.__class__.__name__)
        raise LLMError(provider, f"{provider} request timed out or could not connect.", retryable=True) from exc

    try:
        return json.loads(response_text)
    except json.JSONDecodeError as exc:
        logger.warning("%s API returned non-JSON response", provider)
        raise LLMError(provider, f"{provider} returned an invalid response format.") from exc


def _query_openai(prompt: str, api_key: str) -> str:
    data = _post_json(
        "OpenAI",
        "https://api.openai.com/v1/chat/completions",
        {
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        },
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("OpenAI", "OpenAI returned an unexpected response format.") from exc
    if not content:
        raise LLMError("OpenAI", "OpenAI returned an empty response.")
    return content


def _query_openrouter(prompt: str, api_key: str) -> str:
    data = _post_json(
        "OpenRouter",
        "https://openrouter.ai/api/v1/chat/completions",
        {
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        },
        {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": os.getenv("OPENROUTER_SITE_URL", "http://localhost:5173"),
            "X-Title": os.getenv("OPENROUTER_APP_NAME", "CapForecast"),
        },
    )
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("OpenRouter", "OpenRouter returned an unexpected response format.") from exc
    if not content:
        raise LLMError("OpenRouter", "OpenRouter returned an empty response.")
    return content


def _query_gemini(prompt: str, api_key: str) -> str:
    data = _post_json(
        "Gemini",
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        },
        {
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )
    try:
        candidates = data.get("candidates") or []
        first = candidates[0]
        parts = first["content"]["parts"]
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("Gemini", "Gemini returned an unexpected response format.") from exc
    if not text:
        finish_reason = first.get("finishReason") if isinstance(first, dict) else None
        raise LLMError("Gemini", f"Gemini returned an empty response{f' ({finish_reason})' if finish_reason else ''}.")
    return text


def query_llm(prompt: str, api_key: str) -> str:
    """Query the configured LLM provider and return raw JSON text."""
    prompt = (prompt or "").strip()
    if not prompt:
        raise LLMError("LLM", "Prompt is empty.")
    if len(prompt) > MAX_LLM_PROMPT_CHARS:
        raise LLMError("LLM", "Prompt is too large for the configured safety limit.")

    valid, provider, message = validate_api_key_format(api_key)
    if not valid or not provider:
        raise LLMError("LLM", message)

    key = api_key.strip()
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            if provider == "openrouter":
                return _query_openrouter(prompt, key)
            if provider == "openai":
                return _query_openai(prompt, key)
            if provider == "gemini":
                return _query_gemini(prompt, key)
        except LLMError as exc:
            if exc.retryable and attempt < max_retries:
                delay = 2 * (2 ** attempt)
                logger.info("%s rate/availability issue, retrying once in %ss", exc.provider, delay)
                time.sleep(delay)
                continue
            raise

    raise LLMError("LLM", "LLM query failed after retry.")


def clean_and_parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        newline_idx = cleaned.find("\n")
        if newline_idx != -1:
            cleaned = cleaned[newline_idx:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
    return json.loads(cleaned)


def _validated_llm_json(raw_resp: str, provider_label: str = "LLM") -> tuple[str, list[str]]:
    try:
        parsed = clean_and_parse_json(raw_resp)
    except Exception as exc:
        raise LLMError(provider_label, f"{provider_label} returned JSON that could not be parsed.") from exc
    answer = parsed.get("answer")
    agent_steps = parsed.get("agent_steps", [])
    if not isinstance(answer, str) or not answer.strip():
        raise LLMError(provider_label, f"{provider_label} response did not include a usable answer.")
    if not isinstance(agent_steps, list):
        agent_steps = []
    return answer.strip(), [str(step) for step in agent_steps]


def _llm_failure_message(error: Exception) -> str:
    if isinstance(error, LLMError):
        return error.public_message
    return "AI recommendations are unavailable because the provider returned an unexpected error."


def rule_based_general_fallback(question: str, current_health: dict, averages: dict) -> tuple[str, list[str]]:
    text = question.lower()

    alerts = current_health.get("alerts", [])
    alert_text = ""
    if alerts:
        alert_text = "Active Alerts:\n" + "\n".join([f"- ⚠️ **{a['label']}** is at **{a['value']}%** (threshold is {a['threshold']}%) - Status: *{a['status']}*" for a in alerts])
    else:
        alert_text = "No active alerts. All metrics are within configured thresholds."

    score = current_health.get("score", 100)
    grade = current_health.get("grade", "Excellent")

    if "alert" in text or "warn" in text:
        answer = (
            f"Here is a summary of active alerts in the system:\n\n"
            f"{alert_text}\n\n"
            f"Overall system health score is **{score}/100** ({grade})."
        )
        steps = ["Checked alert thresholds", "Retrieved active resource alerts"]
    elif any(w in text for w in ("health", "status", "how is", "summary")):
        answer = (
            f"### System Health Summary\n"
            f"- **Overall Health Score**: {score}/100 ({grade})\n"
            f"- **Active Alerts**: {len(alerts)} active alerts\n\n"
            f"**Current Resource Levels:**\n"
            f"- CPU Usage: {current_health.get('latest', {}).get('cpu_usage') or 0}%\n"
            f"- Memory Usage: {current_health.get('latest', {}).get('memory_usage') or 0}%\n"
            f"- Disk Usage: {current_health.get('latest', {}).get('disk_usage') or 0}%\n\n"
            f"{alert_text}"
        )
        steps = ["Retrieved current health score", "Summarized metric levels", "Checked active alerts"]
    elif "cpu" in text:
        answer = (
            f"### CPU Usage Details\n"
            f"- Current CPU Usage: **{current_health.get('latest', {}).get('cpu_usage') or 0}%**\n"
            f"- 30-Day CPU Average: **{averages.get('cpu_usage') or 0}%**\n"
            f"- Warning threshold set: **{current_health.get('thresholds', {}).get('cpu_usage', 85)}%**"
        )
        steps = ["Retrieved CPU history", "Calculated averages and thresholds"]
    elif "mem" in text or "ram" in text:
        answer = (
            f"### Memory Usage Details\n"
            f"- Current Memory Usage: **{current_health.get('latest', {}).get('memory_usage') or 0}%**\n"
            f"- 30-Day Memory Average: **{averages.get('memory_usage') or 0}%**\n"
            f"- Warning threshold set: **{current_health.get('thresholds', {}).get('memory_usage', 80)}%**"
        )
        steps = ["Retrieved Memory history", "Calculated averages and thresholds"]
    elif "disk" in text or "storage" in text:
        answer = (
            f"### Disk Usage Details\n"
            f"- Current Disk Usage: **{current_health.get('latest', {}).get('disk_usage') or 0}%**\n"
            f"- 30-Day Disk Average: **{averages.get('disk_usage') or 0}%**\n"
            f"- Warning threshold set: **{current_health.get('thresholds', {}).get('disk_usage', 80)}%**"
        )
        steps = ["Retrieved Disk history", "Calculated averages and thresholds"]
    else:
        answer = (
            f"Hello! I am CapForecast, your capacity planning SRE assistant.\n\n"
            f"Your current system health score is **{score}/100** ({grade}).\n\n"
            f"I can help you forecast when your resources (CPU, Memory, Disk) will hit critical thresholds. "
            f"For example, ask me: **'When will disk hit 80%?'**.\n\n"
           # f"*(Configure a valid Google Gemini API Key in Settings to enable advanced conversational SRE insights and custom recommendations!)*"
        )
        steps = ["Initialized general conversation", "Loaded welcome interface"]

    return answer, steps


def ask_gemini_forecast(question: str, metric: str, threshold: float, crossing_date: Optional[str], engine: str, forecast_days: int, current_health: dict, averages: dict, rag_context: str, api_key: str) -> tuple[str, list[str]]:
    metric_label = metric.replace("_usage", "").upper()

    prompt = f"""
You are CapForecast, a senior Site Reliability Engineer and capacity planning AI assistant.
The user asked: "{question}"

We have executed a mathematical forecast on the historical metrics in our database. Here are the parameters and results of that forecast:
- Metric: {metric_label}
- Alert Threshold: {threshold}%
- Forecast Horizon: {forecast_days} days
- Mathematical Forecast Engine: {engine}
- Will it cross threshold? {"Yes, on " + crossing_date if crossing_date else "No, it is not forecasted to cross within the next " + str(forecast_days) + " days"}

Retrieved RAG Metrics Context (Latest 15 chronological records):
{rag_context}

Current System Profile (from SQLite database):
- Overall Health Score: {current_health.get('score')}/100 ({current_health.get('grade')})
- Active Alerts: {json.dumps(current_health.get('alerts', []))}
- 30-Day Averages: CPU={averages.get('cpu_usage') or 0}%, Memory={averages.get('memory_usage') or 0}%, Disk={averages.get('disk_usage') or 0}%

Based on this information, provide a professional, helpful, and concise capacity analysis response.
Include:
1. A clear direct answer to their question.
2. SRE-focused, practical mitigation or scaling recommendations if the threshold is crossed or if other metrics are at risk.

Your output format MUST be a single raw JSON object with exactly two fields. Do NOT include markdown wrappers like ```json:
{{
  "answer": "markdown text here",
  "agent_steps": ["step 1", "step 2", "step 3"]
}}
"""
    try:
        raw_resp = query_llm(prompt, api_key)
        return _validated_llm_json(raw_resp)
    except Exception as e:
        ai_message = _llm_failure_message(e)
        logger.warning("Forecast LLM response unavailable: %s", ai_message)
        metric_name = metric.replace("_usage", "").title()
        if crossing_date:
            fallback_answer = (
                f"{metric_name} usage is forecasted to reach {threshold:g}% "
                f"around {crossing_date} (using {engine.replace('_', ' ')}).\n\n"
                #f"*(AI recommendations unavailable: {ai_message})*"
            )
        else:
            fallback_answer = (
                f"{metric_name} usage is not expected to reach {threshold:g}% "
                f"within the next {forecast_days} days.\n\n"
               # f"*(AI recommendations unavailable: {ai_message})*"
            )
        return fallback_answer, [
            "Generated forecast and crossing date",
            f"AI recommendations unavailable: {ai_message}",
            "Prepared fallback answer"
        ]


def ask_gemini_general(question: str, current_health: dict, averages: dict, rag_context: str, api_key: str) -> tuple[str, list[str]]:
    prompt = f"""
You are CapForecast, a senior Site Reliability Engineer and capacity planning AI assistant.
The user asked: "{question}"

Retrieved RAG Metrics Context (Latest 15 chronological records):
{rag_context}

Current System Profile (from SQLite database):
- Overall Health Score: {current_health.get('score')}/100 ({current_health.get('grade')})
- Active Alerts: {json.dumps(current_health.get('alerts', []))}
- 30-Day Averages: CPU={averages.get('cpu_usage') or 0}%, Memory={averages.get('memory_usage') or 0}%, Disk={averages.get('disk_usage') or 0}%

Provide a professional, concise, SRE-focused response answering the user's question based on the system health context and metrics.
If they ask for general recommendations or status, guide them using their current alert and average status.

Your output format MUST be a single raw JSON object with exactly two fields. Do NOT include markdown wrappers like ```json:
{{
  "answer": "markdown text here",
  "agent_steps": ["step 1", "step 2", "step 3"]
}}
"""
    try:
        raw_resp = query_llm(prompt, api_key)
        return _validated_llm_json(raw_resp)
    except Exception as e:
        ai_message = _llm_failure_message(e)
        logger.warning("General LLM response unavailable: %s", ai_message)
        fallback_answer, fallback_steps = rule_based_general_fallback(question, current_health, averages)
        fallback_answer += f"\n\n*(AI response unavailable: {ai_message}. Showing rule-based summary.)*"
        return fallback_answer, fallback_steps + [f"AI response unavailable: {ai_message}"]


@app.post("/upload/csv")
async def upload_csv(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")

    content = await file.read()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    DATA_PATH.write_bytes(content)

    try:
        decoded = content.decode("utf-8").splitlines()
        reader = csv.DictReader(decoded)
        rows = list(reader)
        if len(rows) < 2:
            raise ValueError("CSV must contain at least 2 data rows.")
        normalize_row(rows[0])

        upload_conn = get_db_connection()
        try:
            cursor = upload_conn.cursor()
            cursor.execute("DELETE FROM metrics")
            for row in rows:
                cursor.execute("""
                    INSERT OR REPLACE INTO metrics (
                        date, server_id, environment, region, cpu_usage, memory_usage, disk_usage,
                        network_in_mb, network_out_mb, requests_per_min, active_users, response_time_ms, error_rate_percent
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row.get("date") or row.get("Date"),
                    row.get("server_id", "app-server-01"),
                    row.get("environment", "production"),
                    row.get("region", "ap-south-1"),
                    float(row.get("cpu_usage") or row.get("CPU") or 0),
                    float(row.get("memory_usage") or row.get("Memory") or 0),
                    float(row.get("disk_usage") or row.get("Disk") or 0),
                    float(row.get("network_in_mb") or 0),
                    float(row.get("network_out_mb") or 0),
                    float(row.get("requests_per_min") or 0),
                    float(row.get("active_users") or 0),
                    float(row.get("response_time_ms") or 0),
                    float(row.get("error_rate_percent") or 0),
                ))
            upload_conn.commit()
        finally:
            upload_conn.close()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {exc}") from exc

    return {"message": "CSV uploaded successfully", "rows": len(rows)}


@app.post("/forecast/predict")
def predict(
    payload: ForecastRequest,
    user: dict = Depends(get_current_user),
):
    user_settings = get_user_settings(user["id"])
    api_key = resolve_configured_api_key(user_settings)

    is_forecast_query = True
    try:
        metric, threshold = parse_question(payload.question)
    except ValueError:
        is_forecast_query = False

    rows = load_rows()
    health = compute_health(rows, user_settings["alert_thresholds"])

    def get_avg(met: str) -> float:
        values = [float(normalize_row(r)[met]) for r in rows if normalize_row(r)[met]]
        return round(sum(values) / len(values), 2) if values else 0

    averages = {
        "cpu_usage": get_avg("cpu_usage"),
        "memory_usage": get_avg("memory_usage"),
        "disk_usage": get_avg("disk_usage")
    }

    rag_context = retrieve_relevant_metrics(payload.question)

    if is_forecast_query:
        try:
            history, forecast, crossing_date, engine = run_forecast(
                rows,
                metric,
                threshold,
                payload.forecast_days,
                payload.method,
            )
        except Exception as error:
            raise HTTPException(status_code=500, detail=f"Forecast calculation error: {error}")

        if api_key:
            answer, agent_steps = ask_gemini_forecast(
                payload.question, metric, threshold, crossing_date, engine,
                payload.forecast_days, health, averages, rag_context, api_key
            )
        else:
            metric_name = metric.replace("_usage", "").title()
            if crossing_date:
                answer = (
                    f"{metric_name} usage is forecasted to reach {threshold:g}% "
                    f"around {crossing_date} (using {engine.replace('_', ' ')}).\n\n"
                    #f"⚠️ *Note: To unlock RAG-powered SRE capacity remediation suggestions, please configure your Gemini API Key in Settings!*"
                )
            else:
                answer = (
                    f"{metric_name} usage is not expected to reach {threshold:g}% "
                    f"within the next {payload.forecast_days} days.\n\n"
                    #f"💡 *Note: To unlock RAG-powered SRE capacity recommendations, please configure your Gemini API Key in Settings!*"
                )
            agent_steps = [
                "Received natural language question",
                f"Parsed metric column: {metric}",
                f"Parsed threshold: {threshold:g}%",
                f"Selected forecast engine: {engine.replace('_', ' ')}",
                "Generated forecast and crossing date",
                "Prepared chart data and rule-based fallback answer",
            ]

        response = {
            "metric": metric,
            "threshold": threshold,
            "answer": answer,
            "crossing_date": crossing_date,
            "forecast_engine": engine,
            "history": history[-30:],
            "forecast": forecast,
            "agent_steps": agent_steps,
        }
    else:
        if api_key:
            answer, agent_steps = ask_gemini_general(payload.question, health, averages, rag_context, api_key)
            response = {
                "metric": None,
                "threshold": 0,
                "answer": answer,
                "crossing_date": None,
                "forecast_engine": "gemini",
                "history": [],
                "forecast": [],
                "agent_steps": agent_steps,
            }
        else:
            answer = (
                #"I didn't recognize a forecast target in your question (e.g. 'When will disk hit 80%?'). "
                #"To ask general questions about system health and get recommendations, please configure your Gemini API Key in Settings!"
            )
            response = {
                "metric": None,
                "threshold": 0,
                "answer": answer,
                "crossing_date": None,
                "forecast_engine": "none",
                "history": [],
                "forecast": [],
                "agent_steps": [
                    "Received natural language question",
                    "Did not detect capacity forecast metric/threshold",
                    "LLM API Key not configured for general SRE chat"
                ],
            }

    try:
        saved = add_history_entry(user["id"], {
            "question": payload.question,
            "answer": response["answer"],
            "metric": response["metric"] or "none",
            "threshold": response["threshold"],
            "crossing_date": response["crossing_date"],
            "forecast_engine": response["forecast_engine"],
            "forecast_days": payload.forecast_days,
            "method": payload.method,
            "history": response["history"],
            "forecast": response["forecast"],
            "agent_steps": response["agent_steps"],
        })
        response["history_id"] = saved["id"]
    except Exception as e:
        print(f"Error saving history: {e}")
        response["history_id"] = None

    return response


@app.get("/history")
def get_history(user: dict = Depends(get_current_user)):
    items = load_user_history(user["id"])
    return {"items": items, "file": f"{user['email'].replace('@', '_at_').replace('.', '_')}.db"}


@app.get("/history/{item_id}")
def get_history_item(item_id: str, user: dict = Depends(get_current_user)):
    items = load_user_history(user["id"])
    item = next((entry for entry in items if entry.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="History item not found")
    return item


@app.delete("/history")
def clear_history(user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user["id"],))
        conn.commit()
    finally:
        conn.close()
    return {"message": "History cleared"}


@app.delete("/history/{item_id}")
def delete_history_item(item_id: str, user: dict = Depends(get_current_user)):
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="History item not found")
        conn.commit()
    finally:
        conn.close()
    return {"message": "History item removed"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
