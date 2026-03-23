import os
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash

# Local imports
from models import db, User, UserRole, SystemConfig
from app import create_app # Import the factory, not the 'app' instance

load_dotenv()

def init():
    # Create the app instance using the factory
    app = create_app()
    
    with app.app_context():
        print("🛠️ Initializing database tables...")
        db.create_all()

        # 1. ADMIN USER INITIALIZATION
        admin_email = os.environ.get("USER_EMAIL")
        user_name = os.environ.get("USER_NAME")
        temp_pass = os.environ.get("USER_PASSWORD")

        if not all([admin_email, user_name, temp_pass]):
            print("⚠️ Missing admin credentials in environment variables.")
        else:
            # The event listener in models.py will handle the .upper() automatically
            exists = User.query.filter_by(user_email=str(admin_email).upper()).first()

            if not exists:
                print(f"👤 Creating admin user: {admin_email}")
                new_admin = User(
                    user_name=user_name,
                    user_email=admin_email,
                    active_user=True,
                    user_role=UserRole.ADMIN,
                    user_password=generate_password_hash(temp_pass)
                )
                db.session.add(new_admin)
            else:
                print("ℹ️ Admin already exists.")

        # 2. WORKER CONFIG INITIALIZATION
        if not SystemConfig.query.first():
            print("⚙️ Initializing SystemConfig: Worker ENABLED")
            db.session.add(SystemConfig(worker_enabled=True))

        try:
            db.session.commit()
            print("🚀 Initialization successful.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error: {repr(e)}")

if __name__ == "__main__":
    init()