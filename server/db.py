import hashlib
import hmac
import os
import secrets
import sqlite3
import contextlib
from pathlib import Path

DB_PATH = Path(os.environ.get("PATCHPILOT_DB_PATH", str(Path(__file__).parent / "patchpilot.db")))


# PERFORMANCE: Per-connection PRAGMAs applied to every new connection.
# - synchronous=NORMAL: safe with WAL, cuts fsync overhead vs FULL
# - cache_size=-2000: 2 MB page cache per connection (negative = kibibytes)
# - temp_store=MEMORY: keep temp tables in RAM, avoids disk I/O
# - mmap_size: memory-mapped I/O up to 64 MB — reduces syscall overhead
_CONNECTION_PRAGMAS = (
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA synchronous=NORMAL",
    "PRAGMA cache_size=-2000",
    "PRAGMA temp_store=MEMORY",
    "PRAGMA mmap_size=67108864",
)


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    for pragma in _CONNECTION_PRAGMAS:
        conn.execute(pragma)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextlib.contextmanager
def db():
    conn = get_db()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id          TEXT PRIMARY KEY,
                hostname    TEXT NOT NULL,
                ip          TEXT,
                os_pretty   TEXT,
                kernel      TEXT,
                arch        TEXT,
                package_manager TEXT,
                agent_version TEXT DEFAULT '',
                agent_type  TEXT DEFAULT 'linux',
                capabilities TEXT DEFAULT '',
                reboot_required INTEGER DEFAULT 0,
                pending_count   INTEGER DEFAULT 0,
                last_seen   TEXT,
                registered  TEXT DEFAULT (datetime('now','localtime')),
                token       TEXT NOT NULL,
                tags        TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS packages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                name        TEXT NOT NULL,
                current_ver TEXT,
                source_kind TEXT,
                source_id   TEXT,
                new_ver     TEXT,
                UNIQUE(agent_id, name)
            );

            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id    TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                type        TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                created     TEXT DEFAULT (datetime('now','localtime')),
                started     TEXT,
                finished    TEXT,
                output      TEXT,
                params      TEXT
            );

            CREATE TABLE IF NOT EXISTS schedules (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                cron        TEXT NOT NULL,
                action      TEXT NOT NULL,
                target      TEXT NOT NULL,
                enabled     INTEGER DEFAULT 1,
                last_run    TEXT,
                next_run    TEXT
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            -- PERFORMANCE: Indexes for the most frequent query patterns.
            -- agent_id lookups in packages/jobs (heartbeat, job polling).
            -- last_seen on agents (dashboard online-status filter).
            -- status on jobs (pending job polling by agents).
            CREATE INDEX IF NOT EXISTS idx_packages_agent_id
                ON packages(agent_id);

            CREATE INDEX IF NOT EXISTS idx_jobs_agent_id_status
                ON jobs(agent_id, status);

            CREATE INDEX IF NOT EXISTS idx_agents_last_seen
                ON agents(last_seen);

            CREATE TABLE IF NOT EXISTS users (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                username      TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role          TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('admin','user','readonly')),
                created       TEXT DEFAULT (datetime('now','localtime'))
            );

            -- Rename aliases: old agent IDs map to new ones so heartbeats
            -- from agents that haven't updated yet still get routed correctly.
            CREATE TABLE IF NOT EXISTS rename_aliases (
                old_id   TEXT PRIMARY KEY,
                new_id   TEXT NOT NULL,
                created  TEXT DEFAULT (datetime('now','localtime'))
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                username   TEXT NOT NULL,
                role       TEXT NOT NULL,
                created_ts REAL NOT NULL
            );
        """)
        # Migrate existing databases: add tags column if absent.
        # SQLite does not support IF NOT EXISTS on ALTER TABLE, so we catch
        # the OperationalError that fires when the column already exists.
        try:
            conn.execute("ALTER TABLE agents ADD COLUMN tags TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN uptime_seconds INTEGER")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN protocol TEXT DEFAULT 'http'")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN config_review_required INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN config_review_note TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN updates_notified INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN reboot_notified INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN package_manager TEXT")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN agent_version TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN agent_type TEXT DEFAULT 'linux'")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE agents ADD COLUMN capabilities TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass  # column already present — nothing to do

        try:
            conn.execute("ALTER TABLE packages ADD COLUMN source_kind TEXT")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE packages ADD COLUMN source_id TEXT")
        except sqlite3.OperationalError:
            pass

        # Insert default settings rows (skip if key already exists)
        _defaults = [
            ("telegram_token",   ""),
            ("telegram_chat_id", ""),
            ("smtp_host",        ""),
            ("smtp_port",        "587"),
            ("smtp_security",    "starttls"),
            ("smtp_user",        ""),
            ("smtp_password",    ""),
            ("smtp_to",          ""),
            ("telegram_enabled",       "1"),
            ("notify_offline",         "1"),
            ("notify_offline_minutes", "2"),
            ("notify_patches",         "1"),
            ("notify_failures",        "1"),
            ("server_port",            "8443"),
            ("agent_port",             "8050"),
            ("agent_ssl",              "1"),
            ("ui_audio_enabled",       "1"),
            ("ui_audio_volume",        "70"),
            ("ui_login_animation_enabled", "1"),
            ("ui_login_background_animation_enabled", "1"),
            ("ui_login_background_opacity", "20"),
            ("ssl_certfile",           ""),
            ("ssl_keyfile",            ""),
            ("webhook_url",            "https://push.jacques-hien.com"),
            ("webhook_secret",         ""),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
            _defaults,
        )

        # Create default admin user if users table is empty
        if not conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            admin_pw = os.environ.get("PATCHPILOT_ADMIN_PASSWORD", "")
            if not admin_pw:
                admin_pw = secrets.token_urlsafe(16)
                bootstrap_file = os.environ.get("PATCHPILOT_BOOTSTRAP_PASSWORD_FILE", "").strip()
                if bootstrap_file:
                    bootstrap_path = Path(bootstrap_file)
                    bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
                    bootstrap_path.write_text(
                        "PatchPilot bootstrap credentials\n"
                        "username: admin\n"
                        f"password: {admin_pw}\n"
                        "Remove this file after the first successful login.\n"
                    )
                    bootstrap_path.chmod(0o600)
                else:
                    raise RuntimeError(
                        "PATCHPILOT_ADMIN_PASSWORD or PATCHPILOT_BOOTSTRAP_PASSWORD_FILE "
                        "must be set for the first startup"
                    )
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, 'admin')",
                ("admin", hash_password(admin_pw)),
            )

        # PERFORMANCE: PRAGMA optimize lets SQLite update its internal query
        # planner statistics based on actual data — runs in microseconds and
        # improves query plans for all subsequent connections this session.
        conn.execute("PRAGMA optimize")

    # MEDIUM-10: Set restrictive permissions on the database file
    try:
        DB_PATH.chmod(0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Password hashing (stdlib PBKDF2)
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 + random salt. Returns 'salt$hash'."""
    salt = os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return salt.hex() + "$" + h.hex()


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a 'salt$hash' string."""
    try:
        salt_hex, hash_hex = stored.split("$", 1)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
        return hmac_compare(h, expected)
    except (ValueError, AttributeError):
        return False


def hmac_compare(a: bytes, b: bytes) -> bool:
    """Constant-time comparison."""
    return hmac.compare_digest(a, b)
