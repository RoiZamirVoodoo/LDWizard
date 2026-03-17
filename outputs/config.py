import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "data")
ALLOWED_EXTENSIONS_LEVEL_DATA = {"xlsx", "xls", "csv"}
ALLOWED_EXTENSIONS_LEVEL_PARAMS = {"xlsx", "xls", "csv"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB max upload

SECRET_KEY = "ld-wizard-dev-key"
