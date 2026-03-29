import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file for local development
load_dotenv()

# Define the base directory (from flask_app/config.py to flask_app/)
BASE_DIR = Path(__file__).resolve().parent

class Config:
    """Base config."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'default-secret-key')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WIALON_TOKEN = os.environ.get('WIALON_TOKEN')
    WIALON_BASE_URL = "https://hst-api.wialon.com/wialon/ajax.html"

class DevelopmentConfig(Config):
    DEBUG = True
    # Creates local_dev.db inside the flask_app folder
    sqlite_path = BASE_DIR.parent / "local_dev.db"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{sqlite_path}"

class ProductionConfig(Config):
    DEBUG = False
    
    # Render provides the full connection string as DATABASE_URL
    uri = os.environ.get('DATABASE_URL')
    
    # Fix: SQLAlchemy 1.4+ requires 'postgresql://' instead of 'postgres://'
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = uri

config_dict = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}