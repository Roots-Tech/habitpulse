import logging
import os
import re
import socket
import subprocess
import sys
from typing import Dict, List
import psycopg2
from psycopg2 import sql
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from django.conf import settings

logger = logging.getLogger(__name__)

# Databases that must NEVER be dropped or wiped under any circumstances
PROTECTED_DATABASES = {
    "habit_tracker",
    "postgres",
    "gsp16_live_1626",
    "fintensor",
}

# System databases hidden from the normal manager list
SYSTEM_DATABASES = {
    "postgres",
    "gsp16_live_1626",
    "fintensor",
}


def get_master_password() -> str:
    """Returns the configured master password for database operations."""
    return getattr(settings, "DB_MASTER_PASSWORD", os.getenv("DB_MASTER_PASSWORD", "admin"))


def verify_master_password(password: str) -> bool:
    """Verifies that the provided password matches the master password."""
    if not password:
        return False
    return password == get_master_password()


def get_pg_connection(dbname: str = "postgres"):
    """Creates a psycopg2 connection to the PostgreSQL server."""
    db_config = settings.DATABASES["default"]
    conn = psycopg2.connect(
        dbname=dbname,
        user=db_config.get("USER", "postgres"),
        password=db_config.get("PASSWORD", ""),
        host=db_config.get("HOST", "127.0.0.1"),
        port=db_config.get("PORT", "5432"),
    )
    return conn


def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Checks whether a local TCP port is currently open and listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex((host, port)) == 0


def list_databases() -> List[Dict]:
    """
    Lists all available HabitPulse databases on the PostgreSQL server,
    their protection status, active status, and table count.
    """
    conn = get_pg_connection("postgres")
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT datname
                FROM pg_database
                WHERE datistemplate = false
                ORDER BY datname;
            """)
            rows = cur.fetchall()
    finally:
        conn.close()

    current_db = settings.DATABASES["default"]["NAME"]
    databases = []

    for (name,) in rows:
        if name in SYSTEM_DATABASES:
            continue

        is_protected = name.lower() in PROTECTED_DATABASES
        is_active = (name == current_db)

        # Get table count for this database
        table_count = 0
        try:
            db_conn = get_pg_connection(name)
            with db_conn.cursor() as cur:
                cur.execute("""
                    SELECT count(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public';
                """)
                res = cur.fetchone()
                if res:
                    table_count = res[0]
            db_conn.close()
        except Exception:
            table_count = "N/A"

        databases.append({
            "name": name,
            "is_protected": is_protected,
            "is_active": is_active,
            "table_count": table_count,
        })

    return databases


def create_database(name: str, seed_bootstrap: bool = True) -> Dict:
    """
    Creates a new PostgreSQL database, runs all Django migrations,
    and optionally seeds the initial temporary bootstrap admin ('admin' / 'admin').
    """
    name = name.strip().lower()
    if not re.match(r"^[a-z][a-z0-9_]{2,39}$", name):
        raise ValueError(
            "Database name must begin with a letter, contain only lowercase letters, "
            "numbers, and underscores, and be between 3 and 40 characters long."
        )

    # 1. Connect to postgres cluster and create database
    conn = get_pg_connection("postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s;", (name,))
            if cur.fetchone():
                raise ValueError(f"Database '{name}' already exists.")
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
            logger.info("Created PostgreSQL database '%s'", name)
    finally:
        conn.close()

    # 2. Run Django migrations on the new database via subprocess
    env = os.environ.copy()
    env["DB_NAME"] = name

    migrate_cmd = [sys.executable, "manage.py", "migrate", "--noinput"]
    proc = subprocess.run(
        migrate_cmd,
        env=env,
        capture_output=True,
        text=True,
        cwd=str(settings.BASE_DIR),
    )

    if proc.returncode != 0:
        logger.error("Migration failed for database '%s': %s", name, proc.stderr)
        raise RuntimeError(f"Database migration failed: {proc.stderr}")

    # 3. Seed bootstrap admin if requested
    bootstrap_created = False
    if seed_bootstrap:
        seed_code = (
            "import os, django; "
            "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings'); "
            "django.setup(); "
            "from accounts.services import create_bootstrap_admin; "
            "create_bootstrap_admin()"
        )
        proc_seed = subprocess.run(
            [sys.executable, "-c", seed_code],
            env=env,
            capture_output=True,
            text=True,
            cwd=str(settings.BASE_DIR),
        )
        if proc_seed.returncode != 0:
            logger.warning("Bootstrap admin seeding warning on '%s': %s", name, proc_seed.stderr)
        else:
            bootstrap_created = True

    return {
        "name": name,
        "bootstrap_created": bootstrap_created,
        "message": f"Database '{name}' created and migrated successfully.",
    }


def kill_process_on_port(port: int):
    """Terminates any process listening on the specified local TCP port."""
    try:
        proc = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
        )
        for line in proc.stdout.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pid = parts[-1]
                if pid and pid.isdigit() and int(pid) > 0 and int(pid) != os.getpid():
                    logger.info("Terminating process PID %s on port %s", pid, port)
                    subprocess.run(["taskkill", "/PID", pid, "/F", "/T"], capture_output=True)
    except Exception as e:
        logger.warning("Could not terminate process on port %s: %s", port, str(e))


def drop_database(name: str) -> bool:
    """
    Terminates active connections and drops the specified database.
    Also terminates any running dev server instance that was serving this database.
    Strictly prohibits dropping protected databases (habit_tracker, postgres).
    """
    name = name.strip().lower()
    if name in PROTECTED_DATABASES:
        raise ValueError(f"Protected database '{name}' cannot be dropped.")

    current_db = settings.DATABASES["default"]["NAME"].lower()
    if name == current_db:
        raise ValueError(
            f"Cannot drop database '{name}' because this running server instance is currently connected to it. "
            f"Please open the primary Database Manager on Port 8000 (http://127.0.0.1:8000/db-manager/) "
            f"to manage or drop this database."
        )

    # Stop any running server instance serving this database
    active = get_active_instances()
    if name in active:
        kill_process_on_port(active[name]["port"])

    conn = get_pg_connection("postgres")
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            # Terminate existing connections to that DB
            cur.execute("""
                SELECT pg_terminate_backend(pid)
                FROM pg_stat_activity
                WHERE datname = %s AND pid <> pg_backend_pid();
            """, (name,))
            # Drop the database
            cur.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(name)))
            logger.info("Successfully dropped database '%s'", name)
            return True
    finally:
        conn.close()


def get_active_instances(valid_db_names=None) -> Dict[str, Dict]:
    """
    Scans local TCP ports (8000-8006) and identifies which database is served on each port.
    If valid_db_names is supplied, automatically kills zombie instances whose DB no longer exists
    and omits them from the active list.
    """
    import urllib.request
    import json

    active_instances = {}
    for port in range(8000, 8007):
        if is_port_in_use(port):
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/db-manager/instance-info/",
                    headers={"User-Agent": "HabitPulse-Manager"},
                )
                with urllib.request.urlopen(req, timeout=0.35) as res:
                    if res.getcode() == 200:
                        data = json.loads(res.read().decode("utf-8"))
                        db_name = data.get("database")
                        if db_name:
                            db_key = db_name.lower()
                            # If database was dropped, clean up zombie process!
                            if valid_db_names is not None and db_key not in valid_db_names:
                                logger.info("Killing zombie process on port %s for dropped database '%s'", port, db_name)
                                kill_process_on_port(port)
                                continue

                            active_instances[db_key] = {
                                "port": port,
                                "url": f"http://127.0.0.1:{port}/",
                                "login_url": f"http://127.0.0.1:{port}/accounts/login/",
                                "db_name": db_name,
                            }
            except Exception:
                pass
    return active_instances
