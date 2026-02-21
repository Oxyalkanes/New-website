import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, abort
from werkzeug.utils import secure_filename
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from sqlalchemy import inspect, or_
from PIL import Image
from models import db, User, Video, Category, Like, Comment
from forms import (VideoForm, EditVideoForm, LoginForm, RegistrationForm,
                   CommentForm, SearchForm, CategoryForm, EditProfileForm)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///videos.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['AVATAR_FOLDER'] = 'static/avatars'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB for videos
app.config['MAX_AVATAR_SIZE'] = 2 * 1024 * 1024      # 2MB for avatars

ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'wmv', 'flv', 'mkv'}
ALLOWED_AVATAR_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif'}

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = '请先登录才能访问该页面。'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def allowed_file(filename, allowed_set):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_set

# 创建上传文件夹
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['AVATAR_FOLDER'], exist_ok=True)

# 默认头像（确保 static/avatars/default.png 存在，可以从网上下载或创建一个空白图片）
DEFAULT_AVATAR = 'default.png'

# ---------- 数据库升级函数 ----------
def upgrade_database():
    inspector = inspect(db.engine)
    # 检查 user 表是否有 is_admin 列
    user_columns = [col['name'] for col in inspector.get_columns('user')]
    if 'is_admin' not in user_columns:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0'))
            conn.commit()
        print("数据库升级：已添加 is_admin 列到 user 表")

    if 'avatar' not in user_columns:
        with db.engine.connect() as conn:
            conn.execute(db.text("ALTER TABLE user ADD COLUMN avatar VARCHAR(200) DEFAULT 'default.png'"))
            conn.commit()
        print("数据库升级：已添加 avatar 列到 user 表")

    if 'bio' not in user_columns:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE user ADD COLUMN bio TEXT'))
            conn.commit()
        print("数据库升级：已添加 bio 列到 user 表")

    # 检查 video 表是否有 category_id 列
    video_columns = [col['name'] for col in inspector.get_columns('video')]
    if 'category_id' not in video_columns:
        with db.engine.connect() as conn:
            conn.execute(db.text('ALTER TABLE video ADD COLUMN category_id INTEGER REFERENCES category(id)'))
            conn.commit()
        print("数据库升级：已添加 category_id 列到 video 表")

# 创建默认管理员和默认头像
def create_default_admin():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            email='admin@example.com',
            is_admin=True,
            avatar=DEFAULT_AVATAR
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print('默认管理员已创建：用户名 admin，密码 admin123（请尽快修改）')

# ---------- 路由 ----------
@app.route('/')
def index():
    videos = Video.query.order_by(Video.upload_time.desc()).all()
    return render_template('index.html', videos=videos)

@app.route('/search', methods=['GET', 'POST'])
def search():
    form = SearchForm()
    results = []
    if form.validate_on_submit():
        query = form.query.data
        results = Video.query.filter(
            or_(Video.title.contains(query), Video.description.contains(query))
        ).order_by(Video.upload_time.desc()).all()
        return render_template('search.html', form=form, results=results, query=query)
    return render_template('search.html', form=form, results=results)

@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    form = VideoForm()
    form.category.choices = [(0, '无分类')] + [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        file = form.video.data
        if file and allowed_file(file.filename, ALLOWED_EXTENSIONS):
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(os.urandom(4).hex(), 16)}{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            video = Video(
                title=form.title.data,
                description=form.description.data,
                filename=filename,
                user_id=current_user.id,
                category_id=form.category.data if form.category.data != 0 else None
            )
            db.session.add(video)
            db.session.commit()
            flash('视频上传成功！', 'success')
            return redirect(url_for('index'))
        else:
            flash('不支持的文件格式！', 'danger')
    return render_template('upload.html', form=form)

@app.route('/video/<int:video_id>', methods=['GET', 'POST'])
def video_detail(video_id):
    video = Video.query.get_or_404(video_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('请先登录后再评论', 'info')
            return redirect(url_for('login', next=request.url))
        comment = Comment(
            content=comment_form.content.data,
            user_id=current_user.id,
            video_id=video.id
        )
        db.session.add(comment)
        db.session.commit()
        flash('评论发表成功', 'success')
        return redirect(url_for('video_detail', video_id=video.id))

    user_liked = False
    if current_user.is_authenticated:
        like = Like.query.filter_by(user_id=current_user.id, video_id=video.id).first()
        user_liked = like is not None

    return render_template('video.html', video=video, comment_form=comment_form, user_liked=user_liked)

@app.route('/video/<int:video_id>/like', methods=['POST'])
@login_required
def like_video(video_id):
    video = Video.query.get_or_404(video_id)
    like = Like.query.filter_by(user_id=current_user.id, video_id=video.id).first()
    if like:
        db.session.delete(like)
        flash('已取消点赞', 'info')
    else:
        like = Like(user_id=current_user.id, video_id=video.id)
        db.session.add(like)
        flash('点赞成功', 'success')
    db.session.commit()
    return redirect(url_for('video_detail', video_id=video.id))

@app.route('/comment/<int:comment_id>/delete', methods=['POST'])
@login_required
def delete_comment(comment_id):
    comment = Comment.query.get_or_404(comment_id)
    if not (current_user.id == comment.user_id or current_user.is_admin):
        abort(403)
    video_id = comment.video_id
    db.session.delete(comment)
    db.session.commit()
    flash('评论已删除', 'success')
    return redirect(url_for('video_detail', video_id=video_id))

@app.route('/video/<int:video_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_video(video_id):
    video = Video.query.get_or_404(video_id)
    if not (current_user.id == video.user_id or current_user.is_admin):
        abort(403)
    form = EditVideoForm(obj=video)
    form.category.choices = [(0, '无分类')] + [(c.id, c.name) for c in Category.query.all()]
    if form.validate_on_submit():
        video.title = form.title.data
        video.description = form.description.data
        video.category_id = form.category.data if form.category.data != 0 else None
        db.session.commit()
        flash('视频信息已更新！', 'success')
        return redirect(url_for('video_detail', video_id=video.id))
    if request.method == 'GET':
        form.category.data = video.category_id or 0
    return render_template('edit_video.html', form=form, video=video)

@app.route('/video/<int:video_id>/delete', methods=['POST'])
@login_required
def delete_video(video_id):
    video = Video.query.get_or_404(video_id)
    if not (current_user.id == video.user_id or current_user.is_admin):
        abort(403)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(video)
    db.session.commit()
    flash('视频已删除！', 'success')
    return redirect(url_for('index'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/avatars/<filename>')
def avatar_file(filename):
    return send_from_directory(app.config['AVATAR_FOLDER'], filename)

# ---------- 个人资料 ----------
@app.route('/user/<username>')
def user_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    videos = Video.query.filter_by(user_id=user.id).order_by(Video.upload_time.desc()).all()
    return render_template('profile.html', user=user, videos=videos)

@app.route('/profile')
@login_required
def my_profile():
    return redirect(url_for('user_profile', username=current_user.username))

@app.route('/profile/edit', methods=['GET', 'POST'])
@login_required
def edit_profile():
    form = EditProfileForm(
        original_username=current_user.username,
        original_email=current_user.email,
        obj=current_user
    )
    if form.validate_on_submit():
        # 检查用户名和邮箱是否已存在（已在表单验证中处理）
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.bio = form.bio.data

        # 处理头像上传
        if form.avatar.data:
            file = form.avatar.data
            if allowed_file(file.filename, ALLOWED_AVATAR_EXTENSIONS):
                # 生成安全的文件名
                filename = secure_filename(file.filename)
                ext = filename.rsplit('.', 1)[1].lower()
                # 使用用户ID和时间戳命名，避免冲突
                new_filename = f"user_{current_user.id}_{int(os.urandom(4).hex(), 16)}.{ext}"
                file_path = os.path.join(app.config['AVATAR_FOLDER'], new_filename)

                # 保存原图并压缩（可选）
                img = Image.open(file)
                # 调整大小，例如限制最大尺寸为200x200
                img.thumbnail((200, 200))
                img.save(file_path)

                # 删除旧头像（如果不是默认头像）
                if current_user.avatar != DEFAULT_AVATAR:
                    old_avatar_path = os.path.join(app.config['AVATAR_FOLDER'], current_user.avatar)
                    if os.path.exists(old_avatar_path):
                        os.remove(old_avatar_path)

                current_user.avatar = new_filename
            else:
                flash('不支持的头像格式，请上传 jpg、jpeg、png 或 gif 文件。', 'danger')
                return render_template('edit_profile.html', form=form)

        db.session.commit()
        flash('个人资料已更新！', 'success')
        return redirect(url_for('user_profile', username=current_user.username))

    return render_template('edit_profile.html', form=form)

# ---------- 分类管理 ----------
@app.route('/categories')
@login_required
@admin_required
def list_categories():
    categories = Category.query.all()
    return render_template('categories.html', categories=categories)

@app.route('/categories/new', methods=['GET', 'POST'])
@login_required
@admin_required
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(name=form.name.data, description=form.description.data)
        db.session.add(category)
        db.session.commit()
        flash('分类创建成功', 'success')
        return redirect(url_for('list_categories'))
    return render_template('edit_category.html', form=form, title='新建分类')

@app.route('/categories/<int:category_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_category(category_id):
    category = Category.query.get_or_404(category_id)
    form = CategoryForm(obj=category)
    if form.validate_on_submit():
        category.name = form.name.data
        category.description = form.description.data
        db.session.commit()
        flash('分类更新成功', 'success')
        return redirect(url_for('list_categories'))
    return render_template('edit_category.html', form=form, title='编辑分类')

@app.route('/categories/<int:category_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_category(category_id):
    category = Category.query.get_or_404(category_id)
    for video in category.videos:
        video.category_id = None
    db.session.delete(category)
    db.session.commit()
    flash('分类已删除', 'success')
    return redirect(url_for('list_categories'))

# ---------- 管理员面板 ----------
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    users = User.query.all()
    videos = Video.query.all()
    return render_template('admin.html', users=users, videos=videos)

@app.route('/admin/user/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
@admin_required
def toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('不能修改自己的管理员状态', 'warning')
    else:
        user.is_admin = not user.is_admin
        db.session.commit()
        flash(f'用户 {user.username} 的管理员状态已更新', 'success')
    return redirect(url_for('admin_panel'))

@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('不能删除自己', 'warning')
    else:
        # 删除该用户的所有视频文件
        for video in user.videos:
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
            if os.path.exists(file_path):
                os.remove(file_path)
        # 删除该用户的头像（如果不是默认头像）
        if user.avatar != DEFAULT_AVATAR:
            avatar_path = os.path.join(app.config['AVATAR_FOLDER'], user.avatar)
            if os.path.exists(avatar_path):
                os.remove(avatar_path)
        db.session.delete(user)
        db.session.commit()
        flash(f'用户 {user.username} 已删除', 'success')
    return redirect(url_for('admin_panel'))

# ---------- 认证路由 ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(
            username=form.username.data,
            email=form.email.data,
            avatar=DEFAULT_AVATAR
        )
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('注册成功，请登录！', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            next_page = request.args.get('next')
            flash('登录成功！', 'success')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('用户名或密码错误', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
def logout():
    logout_user()
    flash('您已退出登录。', 'info')
    return redirect(url_for('index'))

# 初始化数据库和默认数据
with app.app_context():
    db.create_all()
    upgrade_database()
    create_default_admin()

if __name__ == '__main__':
    app.run(debug=True)