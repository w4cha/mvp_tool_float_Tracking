import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
from sqlalchemy import text
from werkzeug.security import generate_password_hash
from zoneinfo import ZoneInfo

# Local imports
sys.path.append(str(Path(__file__).resolve().parent.parent))
from models import db, User, UserRole, SystemConfig
from app import create_app

load_dotenv()

def init():
    app = create_app()
    
    with app.app_context():
        print("🛠️  Initializing database tables...")
        db.create_all()

        # --- 1. ADMIN USER INITIALIZATION ---
        # (Sin cambios, esto ya es seguro por el filtro .first())
        admin_email = os.environ.get("USER_EMAIL")
        user_name = os.environ.get("USER_NAME")
        temp_pass = os.environ.get("USER_PASSWORD")

        if all([admin_email, user_name, temp_pass]):
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
                db.session.flush()
            else:
                print("ℹ️ Admin already exists.")

        # --- 2. WORKER CONFIG INITIALIZATION ---
        if not SystemConfig.query.first():
            print("⚙️  Initializing SystemConfig: Worker ENABLED")
            db.session.add(SystemConfig(worker_enabled=True))

        # --- 3. INITIAL PARTITION CREATION (Postgres Only) ---
        if os.getenv("FLASK_ENV") != "development":
            print("📅 Verifying partitions...")
            tz = ZoneInfo("America/Santiago")
            now = datetime.now(tz)
            
            for i in range(3):
                target_dt = (now.replace(day=1) + timedelta(days=i*31)).replace(day=1)
                suffix = target_dt.strftime("%Y_%m")
                start_str = target_dt.strftime("%Y-%m-%d")
                end_dt = (target_dt + timedelta(days=32)).replace(day=1)
                end_str = end_dt.strftime("%Y-%m-%d")
                
                table_name = f"telemetria_historial_{suffix}"
                
                # VERIFICACIÓN: Consultamos si la tabla ya existe en el esquema
                check_stmt = text("SELECT 1 FROM information_schema.tables WHERE table_name = :tname")
                exists = db.session.execute(check_stmt, {"tname": table_name}).fetchone()

                if not exists:
                    # Solo intentamos crear si no existe, evitando el error de solapamiento de rangos
                    stmt = text(f"""
                        CREATE TABLE {table_name} 
                        PARTITION OF telemetria_historial
                        FOR VALUES FROM (:start) TO (:end);
                    """)
                    try:
                        db.session.execute(stmt, {"start": start_str, "end": end_str})
                        print(f"✅ Partition created: {table_name}")
                    except Exception as e:
                        print(f"⚠️  Could not create partition {table_name}: {e}")
                else:
                    print(f"ℹ️  Partition {table_name} already exists. Skipping.")

        try:
            db.session.commit()
            print("🚀 Initialization successful.")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error during commit: {repr(e)}")

if __name__ == "__main__":
    init()