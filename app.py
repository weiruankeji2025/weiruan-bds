import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'weiruan_tech_secret_key'  # 用于加密Session，可以修改

# --- 核心修复：使用绝对路径配置数据库 ---
# 获取当前 app.py 文件所在的绝对目录
basedir = os.path.abspath(os.path.dirname(__file__))

# 将数据库文件强制指定在当前目录下，文件名为 nav.db
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'nav.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 初始化数据库插件
db = SQLAlchemy(app)

# --- 管理员账号配置 ---
ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'password'  # ⚠️ 记得修改这个密码

# --- 数据库模型 (表结构) ---

# 1. 分类表
class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    links = db.relationship('Link', backref='category', lazy=True)

# 2. 链接表
class Link(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    desc = db.Column(db.String(200))
    icon = db.Column(db.String(500)) # 自定义图标URL
    clicks = db.Column(db.Integer, default=0) # 点击统计
    status = db.Column(db.String(20), default='pending') # pending(待审核), approved(已通过)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'), nullable=False)

# --- 初始化数据库函数 ---
def init_db():
    with app.app_context():
        # 尝试创建所有表
        db.create_all()
        # 如果分类表为空，则创建默认分类
        if not Category.query.first():
            db.session.add(Category(name='常用推荐', sort_order=1))
            db.session.add(Category(name='AI 工具', sort_order=2))
            db.session.add(Category(name='设计灵感', sort_order=3))
            db.session.commit()
            print("初始化默认分类完成")

# --- 页面路由 ---

# 1. 首页
@app.route('/')
def index():
    categories = Category.query.order_by(Category.sort_order).all()
    data = []
    for cat in categories:
        # 只显示审核通过(approved)的链接
        links = Link.query.filter_by(category_id=cat.id, status='approved').order_by(Link.clicks.desc()).all()
        if links: 
            data.append({'category': cat, 'links': links})
    # 为了申请弹窗的下拉菜单，也传所有分类
    return render_template('index.html', categories=data, all_cats=categories)

# 2. 跳转页 (带统计功能)
@app.route('/go/<int:link_id>')
def go_jump(link_id):
    link = Link.query.get_or_404(link_id)
    # 点击数 +1
    link.clicks += 1
    db.session.commit()
    return render_template('jump.html', link=link)

# 3. 提交收录 API
@app.route('/api/submit', methods=['POST'])
def submit_link():
    data = request.json
    if not data.get('url') or not data.get('title'):
        return jsonify({'success': False, 'message': '参数不完整'})
    
    try:
        new_link = Link(
            title=data['title'],
            url=data['url'],
            desc=data.get('desc', ''),
            icon=data.get('icon', ''),
            category_id=int(data.get('category_id', 1)),
            status='pending'  # 默认为待审核
        )
        db.session.add(new_link)
        db.session.commit()
        return jsonify({'success': True, 'message': '已提交，管理员审核后显示'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# --- 后台管理路由 ---

# 登录页
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('账号或密码错误')
    return render_template('login.html')

# 后台主页
@app.route('/admin')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    pending_links = Link.query.filter_by(status='pending').order_by(Link.created_at.desc()).all()
    approved_links = Link.query.filter_by(status='approved').order_by(Link.category_id).all()
    categories = Category.query.order_by(Category.sort_order).all()
    
    return render_template('admin.html', pending=pending_links, approved=approved_links, categories=categories)

# 后台操作 API (审核、删除、更新)
@app.route('/api/admin/link/<action>', methods=['POST'])
def admin_link_action(action):
    if not session.get('logged_in'): 
        return jsonify({'success': False}), 403
    
    try:
        data = request.json
        link_id = data.get('id')
        link = Link.query.get(link_id)
        
        if not link:
            return jsonify({'success': False, 'message': '链接不存在'})

        if action == 'approve':
            link.status = 'approved'
            if data.get('category_id'): link.category_id = int(data['category_id'])
            if data.get('icon'): link.icon = data['icon']
        elif action == 'delete':
            db.session.delete(link)
        elif action == 'update':
            # 简单的更新逻辑预留
            pass

        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)})

# 后台添加分类 API
@app.route('/api/admin/category/add', methods=['POST'])
def add_category():
    if not session.get('logged_in'): 
        return jsonify({'success': False}), 403
    
    name = request.json.get('name')
    if name:
        db.session.add(Category(name=name))
        db.session.commit()
    return jsonify({'success': True})

# -----------------------------------------------------------------
# 关键修复：直接在此处调用 init_db()
# 确保 Gunicorn 启动时（即使不走 __main__）也能创建表
# -----------------------------------------------------------------
init_db()

if __name__ == '__main__':
    # 监听所有IP，端口5001
    app.run(host='0.0.0.0', port=5001)