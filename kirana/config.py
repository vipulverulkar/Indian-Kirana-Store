"""Application metadata. Override the version with APP_VERSION in .env."""
import os

APP_NAME = "KiranaPro"
DEFAULT_VERSION = "1.0.0"
DEFAULT_LICENSE = "GPL-3.0"
DEVELOPER_NAME = os.getenv("DEVELOPER_NAME", "Vipul Verulkar")
DEVELOPER_CONTACT = os.getenv("DEVELOPER_CONTACT", "vipulverulkar@gmail.com")
DEVELOPER_LOCATION = os.getenv("DEVELOPER_LOCATION", "India")
APP_LICENSE = os.getenv("APP_LICENSE", DEFAULT_LICENSE)


def app_version():
    return (os.getenv("APP_VERSION") or DEFAULT_VERSION).strip() or DEFAULT_VERSION
