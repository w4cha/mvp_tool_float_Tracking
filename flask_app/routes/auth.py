from flask import Blueprint, redirect, render_template, flash, url_for, request, make_response
from flask_login import login_user, logout_user, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import select
from models import db, User, RegistrationToken
from forms import RegistrationForm, LoginForm

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('fleet.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email_val = str(form.email.data).upper().strip()
        stmt = select(User).filter_by(user_email=email_val)
        user = db.session.execute(stmt).scalar_one_or_none()
        
        if user and check_password_hash(user.user_password, form.password.data):
            login_user(user)
            flash("Sesión iniciada exitosamente", "success")
            return redirect(url_for('fleet.dashboard'))
        
        flash("Email o contraseña incorrectos", "error")
    return render_template("login.html", form=form)

@auth_bp.route("/logout", methods=["POST"])
def logout():
    if current_user.is_authenticated:
        logout_user()
        flash("Has cerrado sesión correctamente.", "success")
    
    response = make_response("", 200)
    response.headers['HX-Redirect'] = url_for('auth.login')
    return response

@auth_bp.route("/regist", methods=["GET", "POST"])
def regist():
    if current_user.is_authenticated:
        return redirect(url_for('fleet.dashboard'))

    token_val = request.args.get('token')
    if token_val is None:
        flash("Se requiere un token de invitación para registrarse.", "error")
        return redirect(url_for('auth.login'))

    token_record = db.session.execute(
        select(RegistrationToken).filter_by(token=token_val, is_used=False)
    ).scalar_one_or_none()

    if not token_record or token_record.is_expired:
        flash("El token es inválido, ya fue usado o ha expirado.", "error")
        return redirect(url_for('auth.login'))

    form = RegistrationForm()
    if form.validate_on_submit():
        new_user = User(
            user_name=str(form.username.data).upper().strip(),
            user_email=str(form.email.data).upper().strip(),
            user_password=generate_password_hash(form.password.data),
        )
        db.session.add(new_user)
        db.session.commit()
        flash('Tu cuenta ha sido creada. ¡Ya puedes iniciar sesión!', 'success')
        return redirect(url_for('auth.login'))
        
    return render_template("regist.html", form=form, token=token_val)