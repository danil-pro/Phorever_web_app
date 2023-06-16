from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo


class RegisterForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()], render_kw={'class': 'form-control',
                                                                                  'id': 'exampleInputEmail1',
                                                                                  'aria-describedby': 'emailHelp',
                                                                                  'placeholder': 'Enter email'})
    password = PasswordField('Password', validators=[DataRequired()], render_kw={'class': 'form-control',
                                                                                 'id': 'exampleInputPassword1',
                                                                                 'aria-describedby': 'passwordHelp',
                                                                                 'placeholder': 'Password'})
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')],
                                     render_kw={'class': 'form-control', 'id': 'exampleInputPassword2',
                                                'aria-describedby': 'passwordHelp', 'placeholder': 'Confirm Password'})
    submit = SubmitField('Sign Up', render_kw={'class': 'btn', 'style': ''})


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()],
                        render_kw={'class': 'form-control', 'id': 'exampleInputEmail1', 'aria-describedby': 'emailHelp',
                                   'placeholder': 'Enter email'})
    password = PasswordField('Password', validators=[DataRequired()],
                             render_kw={'class': 'form-control', 'id': 'exampleInputPassword1',
                                        'aria-describedby': 'passwordHelp', 'placeholder': 'Password'})
    submit = SubmitField('Log In', render_kw={'class': 'btn', 'style': ''})
