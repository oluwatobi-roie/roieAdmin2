"""Run Flask locally through an existing SSH tunnel without editing .env.

From backend: python run_local.py
Connection check only: python run_local.py --check
"""
import argparse
import os
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parent


def local_database_url(value, tunnel_port=13306):
    """Keep credentials/database/options, but always use the laptop's tunnel."""
    url = make_url(value)
    if url.drivername != "mysql+pymysql":
        raise ValueError("Local startup requires a mysql+pymysql DATABASE_URL.")
    if not url.username or not url.database:
        raise ValueError("DATABASE_URL must include a database username and database name.")
    if set(url.query) & {"host", "port", "unix_socket"}:
        raise ValueError("Remove host, port or unix_socket query options for tunnel testing.")
    return url.set(host="127.0.0.1", port=tunnel_port)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check MySQL connectivity, then exit")
    parser.add_argument("--tunnel-port", type=int, default=13306)
    parser.add_argument("--port", type=int, default=5000, help="Local Flask port")
    args = parser.parse_args()
    if not 1 <= args.tunnel_port <= 65535 or not 1 <= args.port <= 65535:
        parser.error("Ports must be between 1 and 65535.")

    # Keep normal environment precedence. Never print or rewrite credential values.
    for key, value in dotenv_values(BACKEND_DIR / ".env").items():
        if value is not None:
            os.environ.setdefault(key, value)
    value = os.environ.get("DATABASE_URL")
    if not value:
        print("DATABASE_URL is missing. Add it to backend/.env or this terminal's environment.")
        return 1
    try:
        url = local_database_url(value, args.tunnel_port)
    except Exception:
        print("DATABASE_URL is invalid for local testing. Use a mysql+pymysql URL with a username and database name.")
        print("Keep connection host/port in the URL authority, not in query options.")
        return 1

    os.environ["DATABASE_URL"] = url.render_as_string(hide_password=False)
    os.environ["FLASK_ENV"] = "development"
    os.environ["FINANCE_DATA_DIR"] = str(BACKEND_DIR / "data" / "finance-laptop")
    print(f"Checking MySQL through 127.0.0.1:{args.tunnel_port} (credentials hidden)...", flush=True)
    engine = create_engine(url, poolclass=NullPool, connect_args={
        "connect_timeout": 5, "read_timeout": 5, "write_timeout": 5})
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        original = getattr(exc, "orig", None)
        arguments = getattr(original, "args", ())
        code = arguments[0] if arguments and isinstance(arguments[0], int) else None
        if code in (1044, 1045, 1130):
            print(f"MySQL rejected the database login or permissions (error {code}).")
            print("Check the database credentials and MySQL grants. Your SSH passphrase is separate.")
        elif code == 1049:
            print("MySQL reports that the database name in DATABASE_URL does not exist (error 1049).")
        else:
            print(f"MySQL connection failed{f' (error {code})' if code else ''}.")
            print("Keep the SSH tunnel open and check that it forwards to the server's 127.0.0.1:3306.")
        return 1
    finally:
        engine.dispose()

    print("MySQL connection succeeded. The check only ran SELECT 1; no records were changed.")
    if args.check:
        return 0
    print(f"Test invoices: {os.environ['FINANCE_DATA_DIR']}")
    print("Traccar API calls still use your configured server; phone updates affect that server.")
    from app import app
    app.run(host="127.0.0.1", port=args.port, debug=False, use_reloader=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
