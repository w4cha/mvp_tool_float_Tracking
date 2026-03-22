import os
from models import db, User, UserRole, SystemConfig
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv

load_dotenv()

from app import app

def init():
    with app.app_context():
        print("Initializing database...")
        db.create_all()

        # 1. ADMIN USER INITIALIZATION
        admin_email = os.environ.get("USER_EMAIL")
        user_name = os.environ.get("USER_NAME")
        temp_pass = os.environ.get("USER_PASSWORD")
        if not any([admin_email, user_name, temp_pass]):
            print("No fue posible crear el usuario, uno o más atributos necesarios faltan")
            return
        print(admin_email)
        exists = User.query.filter_by(user_email=admin_email.upper()).first()

        if not exists:
            print(f"Creating admin user: {admin_email}")
            new_admin = User(
                user_name=user_name,
                user_email=admin_email.upper(),
                active_user=True,
                user_role=UserRole.ADMIN,
                user_password=generate_password_hash(temp_pass)
            )
            db.session.add(new_admin)
            # We can commit both at the end or separately
            print("Admin created.")
        else:
            print("Admin already exists.")

        # 2. WORKER CONFIG INITIALIZATION
        # Check if any config exists
        config = SystemConfig.query.first()
        if not config:
            print("Initializing SystemConfig: Worker set to ENABLED")
            toggle_state = SystemConfig(worker_enabled=True)
            db.session.add(toggle_state)
        else:
            print(f"SystemConfig exists. Worker is currently: {'ENABLED' if config.worker_enabled else 'DISABLED'}")

        # Final commit for all changes
        try:
            db.session.commit()
            print("Database initialization complete.")
        except Exception as e:
            db.session.rollback()
            print(f"Error during initialization: {e.__repr__()}")

if __name__ == "__main__":
    init()