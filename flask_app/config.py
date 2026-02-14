import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Define the base directory of the project
# This goes up from 'flask_app/src' to 'flask_app'
BASE_DIR = Path(__file__).resolve().parent.parent

class Config:
    """Base config."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WIALON_TOKEN = os.environ.get('WIALON_TOKEN')
    WIALON_BASE_URL = "https://hst-api.wialon.com/wialon/ajax.html"

class DevelopmentConfig(Config):
    DEBUG = True
    # SQLite file will be created in /flask_app/local_dev.db
    # This keeps it out of your /src/ folder and away from Docker build context
    sqlite_path = BASE_DIR / "local_dev.db"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{sqlite_path}"

class ProductionConfig(Config):
    DEBUG = False
    
    # Database Setup for Docker/Postgres
    DB_USER = os.environ.get('DB_USER')
    DB_PASSWORD = os.environ.get('DB_PASSWORD')
    DB_HOST = os.environ.get('DB_HOST', 'db')
    DB_PORT = os.environ.get('DB_PORT', '5432')
    DB_NAME = os.environ.get('DB_NAME')

    SQLALCHEMY_DATABASE_URI = f"postgresql+psycopg2://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}