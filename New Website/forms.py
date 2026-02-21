from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed, FileRequired
from wtforms import StringField, TextAreaField, FileField, SubmitField, PasswordField, SelectField
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional
from models import User, Category

class VideoForm(FlaskForm):
    title = StringField('标题', validators=[DataRequired()])
    description = TextAreaField('描述')
    category = SelectField('分类', coerce=int, validators=[Optional()])
    video = FileField('视频文件', validators=[DataRequired()])
    submit = SubmitField('上传')

    def __init__(self, *args, **kwargs):
        super(VideoForm, self).__init__(*args, **kwargs)
        self.category.choices = [(0, '无分类')] + [(c.id, c.name) for c in Category.query.all()]

class EditVideoForm(FlaskForm):
    title = StringField('标题', validators=[DataRequired()])
    description = TextAreaField('描述')
    category = SelectField('分类', coerce=int, validators=[Optional()])
    submit = SubmitField('更新')

    def __init__(self, *args, **kwargs):
        super(EditVideoForm, self).__init__(*args, **kwargs)
        self.category.choices = [(0, '无分类')] + [(c.id, c.name) for c in Category.query.all()]

class CommentForm(FlaskForm):
    content = TextAreaField('评论', validators=[DataRequired(), Length(max=500)])
    submit = SubmitField('发表评论')

class SearchForm(FlaskForm):
    query = StringField('搜索视频', validators=[DataRequired()])
    submit = SubmitField('搜索')

class CategoryForm(FlaskForm):
    name = StringField('分类名称', validators=[DataRequired(), Length(max=50)])
    description = StringField('描述', validators=[Optional(), Length(max=200)])
    submit = SubmitField('保存')

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    submit = SubmitField('登录')

class RegistrationForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    password = PasswordField('密码', validators=[DataRequired(), Length(min=6)])
    confirm_password = PasswordField('确认密码', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('注册')

    def validate_username(self, username):
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError('用户名已存在，请选择其他用户名。')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('邮箱已被注册，请使用其他邮箱。')

# 新增：编辑个人资料表单
class EditProfileForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired(), Length(min=2, max=20)])
    email = StringField('邮箱', validators=[DataRequired(), Email()])
    bio = TextAreaField('个人简介', validators=[Optional(), Length(max=500)])
    avatar = FileField('头像', validators=[FileAllowed(['jpg', 'jpeg', 'png', 'gif'], '只允许上传图片文件！')])
    submit = SubmitField('保存修改')

    def __init__(self, original_username, original_email, *args, **kwargs):
        super(EditProfileForm, self).__init__(*args, **kwargs)
        self.original_username = original_username
        self.original_email = original_email

    def validate_username(self, username):
        if username.data != self.original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError('用户名已存在，请选择其他用户名。')

    def validate_email(self, email):
        if email.data != self.original_email:
            user = User.query.filter_by(email=email.data).first()
            if user:
                raise ValidationError('邮箱已被注册，请使用其他邮箱。')