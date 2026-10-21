"""Standalone desktop launcher for KiranaPro (Windows / Linux / macOS).

Starts Flask on a local-only port, then opens a native window (if pywebview is
installed) or the default browser. PyInstaller uses this file as its entry
point; see kirana.spec and the "Desktop app" section of README.md.

Data (SQLite DB, uploaded logo, secret key) is stored in a writable per-user
directory, never inside the one-file bundle. Override with KIRANA_DATA_DIR.
"""
import argparse
import os
import secrets
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _exe_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _load_env():
    from dotenv import load_dotenv
    if getattr(sys, "frozen", False):
        env_file = _exe_dir() / ".env"
        if env_file.is_file():
            load_dotenv(env_file)
    else:
        load_dotenv()


def _pick_port(preferred):
    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return port
    raise RuntimeError("No free local port found")


def _ensure_secret(data_dir):
    if os.getenv("SECRET_KEY"):
        return
    key_path = Path(data_dir) / ".secret_key"
    try:
        if key_path.is_file():
            key = key_path.read_text(encoding="utf-8").strip()
        else:
            key = secrets.token_hex(32)
            key_path.write_text(key, encoding="utf-8")
            try:
                key_path.chmod(0o600)
            except OSError:
                pass
        if key:
            os.environ["SECRET_KEY"] = key
    except OSError:
        os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))


def _run_window(url, title):
    try:
        import webview
    except Exception:
        return False
    try:
        webview.create_window(title, url, width=1360, height=900,
                              min_size=(1024, 700))
        webview.start()
        return True
    except Exception as exc:
        print(f"Native window unavailable ({exc}); using the browser.")
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run KiranaPro as a desktop app")
    parser.add_argument("--port", type=int, default=0,
                        help="local port (default: PORT env or 5000)")
    parser.add_argument("--no-browser", action="store_true",
                        help="start the server without opening a window/browser")
    args = parser.parse_args(argv)

    _load_env()
    os.environ.setdefault("FLASK_DEBUG", "0")

    from kirana.db import DATA_DIR
    _ensure_secret(DATA_DIR)

    from kirana import create_app
    from kirana.config import app_version
    from werkzeug.serving import make_server

    app = create_app()
    preferred = args.port or int(os.getenv("KIRANA_PORT") or os.getenv("PORT") or 5000)
    port = _pick_port(preferred)
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    window_title = f"KiranaPro v{app_version()}"

    print(f"KiranaPro is running at {url}")
    print(f"Data directory: {DATA_DIR}")
    print("Close the KiranaPro window (or press Ctrl+C) to quit.")

    try:
        if args.no_browser or _run_window(url, window_title):
            if args.no_browser:
                while True:
                    time.sleep(1)
        else:
            webbrowser.open(url)
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
