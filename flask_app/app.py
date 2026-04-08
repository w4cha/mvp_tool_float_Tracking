import os
import sys
from pathlib import Path
from flask import Flask, redirect, url_for, flash
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, logout_user, current_user
from werkzeug.middleware.proxy_fix import ProxyFix

# Establish Paths
current_dir = Path(__file__).resolve().parent
sys.path.append(str(current_dir.parent)) # Root
sys.path.append(str(current_dir))        # flask_app

from config import config_dict
from filters import init_app
from models import db, User

# Initialize extensions
login_manager = LoginManager()
login_manager.login_message = "Debes iniciar sesión para acceder al contenido"
login_manager.login_message_category = "info"
login_manager.login_view = "auth.login"
csrf = CSRFProtect()
migrate = Migrate()

def create_app():
    app = Flask(__name__)
    env = os.environ.get('FLASK_ENV', 'production')
    app.config.from_object(config_dict[env])
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
    
    # Init extensions
    init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)

    # Register Blueprints
    from routes.auth import auth_bp
    from routes.admin import admin_bp
    from routes.fleet import fleet_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(fleet_bp)

    @app.route("/")
    def main():
        return redirect(url_for("fleet.dashboard"))

    @app.after_request
    def add_header(response):
        from flask import request
        if not request.path.startswith('/static'):
            response.cache_control.no_store = True
        return response

    @app.before_request
    def check_user_status():
        if current_user.is_authenticated:
            if not current_user.active_user:
                logout_user()
                flash("Tu cuenta ha sido desactivada. Contacta al administrador.", "error")
                return redirect(url_for('auth.login'))

    return app

@login_manager.user_loader
def load_user(user_id):
    user = db.session.get(User, int(user_id))
    if user and user.active_user:
        return user
    return None

if __name__ == "__main__":
    app = create_app()
    app.run(host='0.0.0.0', port=5000)