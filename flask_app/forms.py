from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length, EqualTo, ValidationError
from flask_app.models import User

class RegistrationForm(FlaskForm):
    username = StringField('Nombre de Usuario', 
                           validators=[DataRequired(), Length(min=2, max=50)])
    email = StringField('Correo Electrónico', 
                        validators=[DataRequired(), Email(), Length(max=100)])
    password = PasswordField('Contraseña', 
                             validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('Confirmar Contraseña', 
                                     validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrarse')

    # Custom validation to check if email is already taken
    def validate_email(self, email):
        user = User.query.filter_by(user_email=email.data.upper().strip()).first()
        if user:
            raise ValidationError('Este correo ya está registrado.')

class LoginForm(FlaskForm):
    email = StringField('Correo Electrónico', 
                        validators=[DataRequired(), Email(), Length(max=100)])
    password = PasswordField('Contraseña', 
                             validators=[DataRequired(), Length(min=6)])
    submit = SubmitField('Iniciar Sesión')