#!/usr/bin/env python3
import hmac
import json
import os
import secrets
import sqlite3
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "equipment.db"
STATIC_DIR = BASE_DIR / "static"

# This title is shown in the page header and in the browser tab.
PAGE_TITLE = "Equipment Booking"

# Change this to "protocol" to open rdp:// links through an installed handler.
# Keep "download" to generate a standard .rdp file in the browser.
RDP_LINK_MODE = "download"

if RDP_LINK_MODE not in {"download", "protocol"}:
    raise RuntimeError('RDP_LINK_MODE must be either "download" or "protocol"')

INITIAL_EQUIPMENT = [
    ("Oscilloscope", "4-channel digital oscilloscope for laboratory measurements", None, 0, 0),
    ("Logic analyzer", "Digital interface and bus analysis", None, 0, 0),
    ("JTAG debugger", "Embedded system debugging and programming", "lab-jtag-01", 0, 1),
    ("Laboratory power supply", "Adjustable bench power supply", None, 0, 0),
    ("Multimeter", "Precision bench multimeter", None, 0, 0),
    ("Thermal camera", "Component and circuit board overheating diagnostics", "192.168.10.42", 1, 0),
]


def connect():
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


def initialize_database():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as database:
        database.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                token TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                booked_by_user_id INTEGER REFERENCES users(id),
                booked_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_equipment_booked_by
                ON equipment(booked_by_user_id);
            CREATE TABLE IF NOT EXISTS app_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        columns = {row["name"] for row in database.execute("PRAGMA table_info(equipment)")}
        if "booked_at" not in columns:
            database.execute("ALTER TABLE equipment ADD COLUMN booked_at TEXT")
        if "ip_or_hostname" not in columns:
            database.execute("ALTER TABLE equipment ADD COLUMN ip_or_hostname TEXT")
        if "rdp_enabled" not in columns:
            database.execute("ALTER TABLE equipment ADD COLUMN rdp_enabled INTEGER NOT NULL DEFAULT 0")
        if "ssh_enabled" not in columns:
            database.execute("ALTER TABLE equipment ADD COLUMN ssh_enabled INTEGER NOT NULL DEFAULT 0")
        seeded = database.execute("SELECT 1 FROM app_meta WHERE key = 'initial_seed'").fetchone()
        if not seeded:
            database.executemany(
                "INSERT OR IGNORE INTO equipment(name, description, ip_or_hostname, rdp_enabled, ssh_enabled) VALUES (?, ?, ?, ?, ?)",
                INITIAL_EQUIPMENT,
            )
            database.execute("INSERT INTO app_meta(key, value) VALUES ('initial_seed', '1')")


def load_admin_code():
    configured = os.environ.get("ADMIN_CODE", "").strip()
    if configured:
        return configured
    secret_file = DATA_DIR / "admin_code.txt"
    if secret_file.exists():
        return secret_file.read_text(encoding="utf-8").strip()
    generated = "admin-" + secrets.token_urlsafe(9)
    secret_file.write_text(generated + "\n", encoding="utf-8")
    os.chmod(secret_file, 0o600)
    print(f"Generated admin code: {generated}", flush=True)
    return generated


class Handler(SimpleHTTPRequestHandler):
    server_version = "EquipmentBooking/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def send_json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > 16_384:
            raise ValueError("Invalid request size")
        return json.loads(self.rfile.read(length))

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            return self.send_json({"status": "ok"})
        if path == "/api/equipment":
            current_name = self.headers.get("X-User-Name", "").strip()
            with connect() as database:
                rows = database.execute("""
                    SELECT e.id, e.name, e.description, e.ip_or_hostname,
                           e.rdp_enabled, e.ssh_enabled, e.booked_at,
                           u.name AS booked_by_name
                    FROM equipment e
                    LEFT JOIN users u ON u.id = e.booked_by_user_id
                    ORDER BY e.name COLLATE NOCASE
                """).fetchall()
            return self.send_json({"pageTitle": PAGE_TITLE, "rdpLinkMode": RDP_LINK_MODE, "equipment": [{
                "id": row["id"],
                "name": row["name"],
                "description": row["description"],
                "ipOrHostname": row["ip_or_hostname"],
                "rdpEnabled": bool(row["rdp_enabled"]),
                "sshEnabled": bool(row["ssh_enabled"]),
                "bookedAt": row["booked_at"],
                "bookedByName": row["booked_by_name"],
                "isMine": bool(current_name and row["booked_by_name"] == current_name),
            } for row in rows]})
        return super().do_GET()

    def do_POST(self):
        if urlparse(self.path).path != "/api/equipment":
            return self.send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)
        try:
            body = self.read_json()
            action = str(body.get("action", ""))
            equipment_id = int(body.get("equipmentId", 0))
            token = str(body.get("userToken", "")).strip()
            name = str(body.get("userName", "")).strip()
            admin_code = str(body.get("adminCode", ""))
            if equipment_id < 1 or not token or not name or len(token) > 200 or len(name) > 60:
                return self.send_json({"error": "User and equipment are required"}, HTTPStatus.BAD_REQUEST)

            database = connect()
            try:
                database.execute("BEGIN IMMEDIATE")
                database.execute("""
                    INSERT INTO users(token, name) VALUES (?, ?)
                    ON CONFLICT(token) DO UPDATE SET name = excluded.name
                """, (token, name))
                user_id = database.execute("SELECT id FROM users WHERE token = ?", (token,)).fetchone()["id"]
                if action == "book":
                    cursor = database.execute("""
                        UPDATE equipment
                        SET booked_by_user_id = ?, booked_at = CURRENT_TIMESTAMP
                        WHERE id = ? AND booked_by_user_id IS NULL
                    """, (user_id, equipment_id))
                    if cursor.rowcount != 1:
                        database.rollback()
                        return self.send_json({"error": "This equipment has already been booked"}, HTTPStatus.CONFLICT)
                elif action == "release":
                    is_admin = bool(ADMIN_CODE and hmac.compare_digest(admin_code, ADMIN_CODE))
                    if is_admin:
                        cursor = database.execute("UPDATE equipment SET booked_by_user_id = NULL, booked_at = NULL WHERE id = ? AND booked_by_user_id IS NOT NULL", (equipment_id,))
                    else:
                        cursor = database.execute("""
                            UPDATE equipment
                            SET booked_by_user_id = NULL, booked_at = NULL
                            WHERE id = ? AND booked_by_user_id IN (
                                SELECT id FROM users WHERE name = ?
                            )
                        """, (equipment_id, name))
                    if cursor.rowcount != 1:
                        current = database.execute(
                            "SELECT booked_by_user_id FROM equipment WHERE id = ?",
                            (equipment_id,),
                        ).fetchone()
                        if current is not None and current["booked_by_user_id"] is None:
                            database.commit()
                            return self.send_json({"ok": True, "alreadyAvailable": True})
                        database.rollback()
                        return self.send_json({"error": "Only the person who booked this equipment or an administrator can release it"}, HTTPStatus.FORBIDDEN)
                else:
                    database.rollback()
                    return self.send_json({"error": "Unknown action"}, HTTPStatus.BAD_REQUEST)
                database.commit()
            finally:
                database.close()
            return self.send_json({"ok": True})
        except (ValueError, TypeError, json.JSONDecodeError):
            return self.send_json({"error": "Invalid request"}, HTTPStatus.BAD_REQUEST)
        except Exception as error:
            print(f"Request failed: {error}", flush=True)
            return self.send_json({"error": "Server error"}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format_string, *args):
        print(f"{self.address_string()} - {format_string % args}", flush=True)


initialize_database()
ADMIN_CODE = load_admin_code()

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    print(f"Equipment Booking is listening on http://{host}:{port}", flush=True)
    ThreadingHTTPServer((host, port), Handler).serve_forever()
