from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, SelectField
from wtforms.validators import DataRequired, Email, EqualTo, Length


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


class UpdateForm(FlaskForm):
    title = StringField('title', validators=[DataRequired(), Length(max=100,
                                                                    message="Title too long max 100 characters")],
                        render_kw={'class': 'form-control',
                                   'id': 'exampleInputEmail1',
                                   'aria-describedby': 'emailHelp'})

    location = StringField('title', validators=[DataRequired(), Length(max=1000,
                                                                       message="Location too long max 100 characters")],
                           render_kw={'class': 'form-control',
                                      'id': 'exampleInputEmail1',
                                      'aria-describedby': 'emailHelp'})

    creation_date = DateField('creation date', validators=[DataRequired()],
                              render_kw={'class': 'form-control',
                                         'id': 'exampleInputEmail1',
                                         'aria-describedby': 'emailHelp'})

    submit = SubmitField('Phorever', render_kw={'class': 'btn',
                                                'style': 'text-algin: center'})


class UpdateLocationForm(FlaskForm):
    location = StringField('title', validators=[DataRequired(), Length(max=1000,
                                                                       message="Location too long max 100 characters")],
                           render_kw={'class': 'form-control',
                                      'id': 'exampleInputEmail1',
                                      'aria-describedby': 'emailHelp'})

    submit = SubmitField('Phorever', render_kw={'class': 'btn', 'style': ''})


class UpdateCreationDateForm(FlaskForm):
    creation_date = DateField('creation date', validators=[DataRequired()],
                              render_kw={'class': 'form-control',
                                         'id': 'exampleInputEmail1',
                                         'aria-describedby': 'emailHelp'})

    submit = SubmitField('Phorever', render_kw={'class': 'btn', 'style': ''})


class IcloudLoginForm(FlaskForm):
    apple_id = StringField('apple_id', validators=[DataRequired(), Email()],
                           render_kw={'class': 'form-control', 'id': 'exampleInputEmail1',
                                      'aria-describedby': 'emailHelp',
                                      'placeholder': 'Enter email'})
    password = PasswordField('Password', validators=[DataRequired()],
                             render_kw={'class': 'form-control', 'id': 'exampleInputPassword1',
                                        'aria-describedby': 'passwordHelp', 'placeholder': 'Password'})

    submit = SubmitField('Log In', render_kw={'class': 'btn', 'style': ''})


class VerifyVerificationCodeForm(FlaskForm):
    code = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)],
                       render_kw={'class': 'form-control', 'id': 'exampleInputEmail1',
                                  'aria-describedby': 'emailHelp',
                                  'placeholder': 'Enter verification code'})
    submit = SubmitField('Submit', render_kw={'class': 'btn', 'style': ''})


class ICloudVerifyForm(FlaskForm):
    device = SelectField('Which device would you like to use?', validators=[DataRequired()],
                         render_kw={'class': 'form-control'})
    code = StringField('Verification Code', validators=[DataRequired(), Length(min=6, max=6)],
                       render_kw={'class': 'form-control', 'id': 'exampleInputEmail1',
                                  'aria-describedby': 'emailHelp',
                                  'placeholder': 'Enter verification code'})
    submit = SubmitField('Submit', render_kw={'class': 'btn', 'style': ''})


class AddFaceName(FlaskForm):
    face_name = StringField('title', validators=[DataRequired(), Length(max=50,
                                                                        message="Name too long max 50 characters")],
                            render_kw={'class': 'form-control',
                                       'id': 'exampleInputEmail1',
                                       'aria-label': 'Small',
                                       'aria-describedby': 'inputGroup-sizing-sm', 'placeholder': 'Enter name'})

    submit = SubmitField('Submit', render_kw={'class': 'btn', 'style': ''})


class AddFamilyMemberForm(FlaskForm):
    name = StringField('Имя', validators=[DataRequired(), Length(min=1, max=50)],
                       render_kw={'class': 'form-control',
                                  'id': 'exampleInputEmail1',
                                  'aria-label': 'Small',
                                  'aria-describedby': 'inputGroup-sizing-sm',
                                  'placeholder': 'Enter name'})
    relationship = SelectField('Родственная связь', validators=[DataRequired()], choices=[
        ('', 'Relationship'),
        ('Parent', 'Parent'),
        ('Child', 'Child'),
        ('Spouse', 'Spouse'),
        ('Sibling', 'Sibling')

    ], render_kw={'class': 'form-select'})
    submit = SubmitField('Submit', render_kw={'class': 'btn', 'style': ''})


class AddCommentForm(FlaskForm):
    add_content = StringField('Add comment', validators=[DataRequired(), Length(min=1, max=50)],
                          render_kw={'class': 'form-control',
                                     'id': 'exampleInputEmail1',
                                     'aria-label': 'Small',
                                     'aria-describedby': 'inputGroup-sizing-sm',
                                     'placeholder': 'Enter name'})

    submit = SubmitField('Submit', render_kw={'class': 'btn', 'style': ''})

