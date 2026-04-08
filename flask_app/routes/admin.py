from flask import Blueprint, redirect, render_template, request, flash, abort, url_for
from flask_login import login_required, current_user
from sqlalchemy import select
from werkzeug.security import generate_password_hash
from models import db, User, SystemConfig, RegistrationToken
from forms import ChangePasswordForm

admin_bp = Blueprint('admin', __name__)

@admin_bp.route("/user/<username>", methods=["GET"])
@login_required
def user_profile(username):
    stmt = select(User).filter_by(user_name=username.upper())
    user_to_view = db.session.execute(stmt).scalar_one_or_none()
    password_form = ChangePasswordForm()
    
    if not user_to_view:
        abort(404)
    
    if current_user.user_role.name != 'ADMIN' and current_user.user_name != username.upper():
        abort(403)

    found_users = []
    if current_user.user_role.name == 'ADMIN':
        search_query = request.args.get('q', '').upper()
        if search_query:
            stmt_search = select(User).filter(User.user_name.ilike(f"%{search_query}%"))
            found_users = db.session.execute(stmt_search).scalars().all()
        if request.headers.get('HX-Request'):
            return render_template("partials/user_table_row.html", found_users=found_users)

    config_stmt = select(SystemConfig)
    config = db.session.execute(config_stmt).scalar_one_or_none()
    worker_status = config.worker_enabled if config else True

    active_tokens = []
    if current_user.user_role.name == 'ADMIN':
        # Fetch only non-used tokens to keep the list clean
        active_tokens = RegistrationToken.query.filter_by(is_used=False).order_by(RegistrationToken.created_at.desc()).all()

    return render_template("user.html", 
                         user=user_to_view, 
                         found_users=found_users, 
                         worker_status=worker_status,
                         tokens=active_tokens,
                         password_form=password_form)

@admin_bp.route("/delete_user", methods=["POST"])
@login_required
def delete_user():
    if current_user.user_role.name != 'ADMIN': 
        abort(403)
    
    u_id = request.form.get('user_id')
    target_user = db.session.get(User, u_id)
    
    if target_user:
        target_user.active_user = not getattr(target_user, 'active_user', True)
        db.session.commit()
        status = 'activada' if target_user.active_user else 'desactivada'
        flash(f"Cuenta usuario {target_user.user_name} {status}", "success")
        
    return redirect(request.referrer or url_for('admin.user_profile', username=current_user.user_name))

@admin_bp.route("/change_password", methods=["POST"])
@login_required
def change_password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        current_user.user_password = generate_password_hash(form.new_password.data)
        db.session.commit()
        flash("Tu contraseña ha sido actualizada correctamente.", "success")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f"Error en {getattr(form, field).label.text}: {error}", "error")
                
    return redirect(url_for('admin.user_profile', username=current_user.user_name))

@admin_bp.route("/toggle_worker", methods=["POST"])
@login_required
def toggle_worker():
    if current_user.user_role.name != 'ADMIN':
        abort(403)
    
    stmt = select(SystemConfig)
    config = db.session.execute(stmt).scalar_one_or_none()
    
    if not config:
        config = SystemConfig(worker_enabled=True)
        db.session.add(config)
    
    config.worker_enabled = not config.worker_enabled
    db.session.commit()
    
    status = "iniciado" if config.worker_enabled else "detenido"
    flash(f"El consumidor de telemetría ha sido {status}.", "info")
    return redirect(request.referrer or url_for('admin.user_profile', username=current_user.user_name))

@admin_bp.route("/generate_invite", methods=["POST"])
@login_required
def generate_invite():
    if current_user.user_role.name != 'ADMIN':
        abort(403)
    
    # Generate a token valid for 48 hours
    new_token = RegistrationToken.generate(hours_valid=48)
    db.session.add(new_token)
    db.session.commit()
    
    # Create the full absolute URL
    active_tokens = RegistrationToken.query.filter_by(is_used=False).order_by(RegistrationToken.created_at.desc()).all()    
    
    return render_template("partials/token_rows.html", tokens=active_tokens)

@admin_bp.route("/delete_token/<int:token_id>", methods=["DELETE"])
@login_required
def delete_token(token_id):
    if current_user.user_role.name != 'ADMIN':
        abort(403)
    
    token = RegistrationToken.query.get_or_404(token_id)
    db.session.delete(token)
    db.session.commit()
    
    # Return empty string with 200 OK so HTMX removes the row
    return "", 200