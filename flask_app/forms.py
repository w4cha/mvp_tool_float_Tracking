import sys
from pathlib import Path
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, SelectField, TextAreaField, TelField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError, Optional
sys.path.append(str(Path(__file__).resolve().parent.parent))
from models import db, User, Subject, VehicleState # Import db to use modern select syntax

# forms.py

class ChangePasswordForm(FlaskForm):
    new_password = PasswordField('Nueva Contraseña', 
                               validators=[
                                   DataRequired(message="Campo obligatorio."), 
                                   Length(min=6, message="Mínimo 6 caracteres.")
                               ])
    confirm_password = PasswordField('Confirmar Nueva Contraseña', 
                                   validators=[
                                       DataRequired(message="Confirma tu contraseña."), 
                                       EqualTo('new_password', message='Las contraseñas no coinciden.')
                                   ])
    submit = SubmitField('Actualizar Credenciales')

class EditVehicleForm(FlaskForm):
    driver_id = SelectField('Conductor Asignado', choices=[])
    new_driver_name = StringField('Nombre Completo', validators=[Optional()])
    new_driver_email = StringField('Email', validators=[Optional(), Email(message="Email inválido.")])
    new_driver_phone = TelField('Teléfono', validators=[Optional()])
    vehicle_state = SelectField('Estado del Vehículo', choices=[(s.name, s.value.capitalize()) for s in VehicleState])

class AnnotationForm(FlaskForm):
    subject = SelectField('Asunto', 
                        choices=[(s.name, s.value.capitalize()) for s in Subject], 
                        validators=[DataRequired(message="Selecciona un asunto.")])
    comment = TextAreaField('Comentario', validators=[DataRequired(message="El comentario es obligatorio.")])
    submit = SubmitField('Guardar Nota')

class RegistrationForm(FlaskForm):
    username = StringField('Nombre de Usuario', 
                           validators=[
                               DataRequired(message="Campo obligatorio."), 
                               Length(min=2, max=50, message="Entre 2 y 50 caracteres.")
                           ])
    email = StringField('Correo Electrónico', 
                        validators=[
                            DataRequired(message="Campo obligatorio."), 
                            Email(message="Email inválido."), 
                            Length(max=100)
                        ])
    password = PasswordField('Contraseña', 
                             validators=[
                                 DataRequired(message="Campo obligatorio."), 
                                 Length(min=6, message="Mínimo 6 caracteres.")
                             ])
    confirm_password = PasswordField('Confirmar Contraseña', 
                                     validators=[
                                         DataRequired(message="Confirma tu contraseña."), 
                                         EqualTo('password', message="Las contraseñas no coinciden.")
                                     ])
    submit = SubmitField('Registrarse')

    def validate_username(self, username):
        val = username.data.upper().strip()
        user = db.session.execute(db.select(User).filter_by(user_name=val)).scalar_one_or_none()
        if user:
            raise ValidationError('Usuario ya está en uso.')

    def validate_email(self, email):
        val = email.data.upper().strip()
        user = db.session.execute(db.select(User).filter_by(user_email=val)).scalar_one_or_none()
        if user:
            raise ValidationError('Correo ya registrado.')

class LoginForm(FlaskForm):
    # Mensajes genéricos para no dar pistas en caso de fuerza bruta
    email = StringField('Correo Electrónico', 
                        validators=[DataRequired(message="Ingresa tu correo."), Email(message="Email inválido.")])
    password = PasswordField('Contraseña', 
                             validators=[DataRequired(message="Ingresa tu contraseña.")])
    submit = SubmitField('Iniciar Sesión')