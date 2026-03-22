class ProductionConfig(Config):
    DEBUG = False
    
    # 1. Grab the full connection string from Render
    uri = os.environ.get('DATABASE_URL')
    
    # 2. Fix the 'postgres://' compatibility issue for SQLAlchemy 1.4+
    if uri and uri.startswith("postgres://"):
        uri = uri.replace("postgres://", "postgresql://", 1)
    
    SQLALCHEMY_DATABASE_URI = uri