import json
import os
import re
from datetime import datetime, timedelta

from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from sqlalchemy import func, inspect as sa_inspect, or_, text

from config import INSTANCE_DIR, Config
from models import (
    COLUMN_NAMES,
    DONE_COLUMN_NAME,
    PRIORITY_LABELS,
    BoardColumn,
    Subtask,
    Tag,
    Task,
    TaskComment,
    TaskLog,
    User,
    db,
    task_tag,
)

MAX_TITLE_LENGTH = 100
MAX_TAG_LENGTH = 20
MAX_TAGS = 5
MAX_SUBTASKS = 20
MAX_SUBTASK_LENGTH = 100
MAX_COMMENT_LENGTH = 500
MAX_LOG_LENGTH = 100

app = Flask(__name__)
app.config.from_object(Config)
app.json.ensure_ascii = False
os.makedirs(INSTANCE_DIR, exist_ok=True)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    if request.endpoint in ('move_task', 'trash_task'):
        return jsonify(code=401, msg='登录状态已失效，请重新登录'), 401
    flash('请先登录后再访问', 'warning')
    return redirect(url_for('login'))


# =========================================================
# 数据查询
# =========================================================

def visible_task_query():
    query = Task.query.filter(Task.is_deleted.is_(False))
    if not current_user.is_admin:
        query = query.filter(Task.owner_id == current_user.id)
    return query


def trash_task_query():
    query = Task.query.filter(Task.is_deleted.is_(True))
    if not current_user.is_admin:
        query = query.filter(Task.owner_id == current_user.id)
    return query


def column_counts():
    query = db.session.query(Task.column_id, func.count(Task.id)).filter(Task.is_deleted.is_(False))
    if not current_user.is_admin:
        query = query.filter(Task.owner_id == current_user.id)
    counts = {str(column.id): 0 for column in BoardColumn.query.all()}
    for column_id, count in query.group_by(Task.column_id).all():
        counts[str(column_id)] = count
    return counts


def count_urgent_tasks(tasks=None):
    if tasks is None:
        tasks = visible_task_query().all()
    return sum(1 for task in tasks if task.is_urgent)


# =========================================================
# 通用写入辅助
# =========================================================

def add_log(task_id, action):
    db.session.add(
        TaskLog(task_id=task_id, username=current_user.username, action=action[:MAX_LOG_LENGTH])
    )


def soft_delete_task(task):
    task.is_deleted = True
    task.deleted_at = datetime.now()
    task.deleted_by = current_user.username
    add_log(task.id, f'把任务移入垃圾桶【{task.title}】')


# =========================================================
# 表单解析与校验
# =========================================================

def read_deadline():
    raw = request.form.get('deadline', '').strip()
    if not raw:
        return None, None
    try:
        return datetime.strptime(raw, '%Y-%m-%dT%H:%M'), None
    except ValueError:
        return None, '截止时间格式不正确'


def read_priority():
    raw = request.form.get('priority', '1')
    return int(raw) if raw in ('0', '1', '2') else 1


def parse_tags(raw):
    names = []
    seen = set()
    for part in re.split(r'[,，]', raw or ''):
        name = part.strip()
        if not name:
            continue
        if len(name) > MAX_TAG_LENGTH:
            return None, f'每个标签不能超过 {MAX_TAG_LENGTH} 个字符'
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)
    if len(names) > MAX_TAGS:
        return None, f'每个任务最多设置 {MAX_TAGS} 个标签'
    return names, None


def resolve_tags(names):
    tags = []
    for name in names:
        tag = Tag.query.filter(func.lower(Tag.name) == name.lower()).first()
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
            db.session.flush()
        tags.append(tag)
    return tags


def read_subtasks():
    raw = request.form.get('subtasks')
    if raw is None:
        return None, None
    try:
        items = json.loads(raw)
    except (TypeError, ValueError):
        return None, '子任务数据格式不正确'
    if not isinstance(items, list):
        return None, '子任务数据格式不正确'
    if len(items) > MAX_SUBTASKS:
        return None, f'每个任务最多 {MAX_SUBTASKS} 个子任务'
    cleaned = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content = str(item.get('content', '')).strip()
        if not content:
            continue
        if len(content) > MAX_SUBTASK_LENGTH:
            return None, f'子任务内容不能超过 {MAX_SUBTASK_LENGTH} 个字符'
        cleaned.append({'content': content, 'is_done': item.get('is_done') is True})
    return cleaned, None


def read_task_form():
    title = request.form.get('title', '').strip()
    content = request.form.get('content', '').strip()
    deadline, deadline_error = read_deadline()
    tag_names, tag_error = parse_tags(request.form.get('tags', ''))
    subtasks, subtask_error = read_subtasks()
    error = deadline_error or tag_error or subtask_error

    if not title:
        error = '任务标题不能为空'
    elif len(title) > MAX_TITLE_LENGTH:
        error = f'任务标题不能超过 {MAX_TITLE_LENGTH} 个字符'

    return {
        'title': title,
        'content': content,
        'priority': read_priority(),
        'deadline': deadline,
        'tag_names': tag_names or [],
        'subtasks': subtasks,
    }, error


# =========================================================
# 任务写入
# =========================================================

def replace_subtasks(task, items):
    task.subtasks.clear()
    for index, item in enumerate(items):
        task.subtasks.append(
            Subtask(content=item['content'], is_done=item['is_done'], position=index)
        )


def get_task_or_none(task_id, allow_deleted=False):
    task = db.session.get(Task, task_id)
    if task is None:
        flash('任务不存在或已被彻底删除', 'warning')
        return None
    if task.is_deleted and not allow_deleted:
        flash('任务已在垃圾桶中，请先从垃圾桶恢复', 'warning')
        return None
    if not current_user.is_admin and task.owner_id != current_user.id:
        flash('你没有权限操作该任务', 'danger')
        return None
    return task


def done_column_id():
    column = BoardColumn.query.filter_by(name=DONE_COLUMN_NAME).first()
    return column.id if column else None


def read_board_filters():
    priority = request.args.get('priority', '')
    if priority not in ('0', '1', '2'):
        priority = ''
    deadline = request.args.get('deadline', '')
    if deadline not in ('urgent', 'overdue'):
        deadline = ''
    owner = request.args.get('owner', type=int) if current_user.is_admin else None
    return {
        'q': request.args.get('q', '').strip()[:MAX_TITLE_LENGTH],
        'priority': priority,
        'tag': request.args.get('tag', '').strip()[:MAX_TAG_LENGTH],
        'deadline': deadline,
        'owner': owner,
    }


def apply_task_filters(query, filters):
    if filters['q']:
        keyword = f"%{filters['q']}%"
        query = query.filter(
            or_(
                Task.title.ilike(keyword),
                Task.content.ilike(keyword),
                Task.tags.any(Tag.name.ilike(keyword)),
            )
        )
    if filters['priority']:
        query = query.filter(Task.priority == int(filters['priority']))
    if filters['tag']:
        query = query.filter(Task.tags.any(Tag.name == filters['tag']))
    done_id = done_column_id()
    if filters['deadline'] == 'urgent' and done_id:
        query = query.filter(
            Task.column_id != done_id,
            Task.deadline.isnot(None),
            Task.deadline >= datetime.now(),
            Task.deadline <= datetime.now() + timedelta(hours=24),
        )
    elif filters['deadline'] == 'overdue' and done_id:
        query = query.filter(
            Task.column_id != done_id,
            Task.deadline.isnot(None),
            Task.deadline < datetime.now(),
        )
    if filters['owner']:
        query = query.filter(Task.owner_id == filters['owner'])
    return query


def available_tags():
    query = (
        db.session.query(Tag)
        .join(task_tag, task_tag.c.tag_id == Tag.id)
        .join(Task, Task.id == task_tag.c.task_id)
        .filter(Task.is_deleted.is_(False))
    )
    if not current_user.is_admin:
        query = query.filter(Task.owner_id == current_user.id)
    return query.distinct().order_by(Tag.name).all()


def apply_task_order(column_id, order_ids):
    allowed = [
        task for task in Task.query.filter_by(column_id=column_id)
        .filter(Task.is_deleted.is_(False)).all()
        if current_user.is_admin or task.owner_id == current_user.id
    ]
    by_id = {task.id: task for task in allowed}
    used = set()
    next_position = 1
    for task_id in order_ids:
        if task_id in by_id and task_id not in used:
            by_id[task_id].position = next_position
            next_position += 1
            used.add(task_id)
    for task in sorted(allowed, key=lambda item: (item.position, item.id)):
        if task.id not in used:
            task.position = next_position
            next_position += 1


def create_task_from_form(form_data):
    todo_column = BoardColumn.query.filter_by(name=COLUMN_NAMES[0]).first()
    max_position = db.session.query(func.max(Task.position)).filter(
        Task.column_id == todo_column.id
    ).scalar()
    task = Task(
        title=form_data['title'],
        content=form_data['content'],
        column_id=todo_column.id,
        owner_id=current_user.id,
        deadline=form_data['deadline'],
        priority=form_data['priority'],
        position=(max_position or 0) + 1,
    )
    task.tags = resolve_tags(form_data['tag_names'])
    if form_data['subtasks']:
        replace_subtasks(task, form_data['subtasks'])
    db.session.add(task)
    db.session.flush()
    add_log(task.id, f'创建任务【{task.title}】')
    db.session.commit()


# =========================================================
# 页面路由
# =========================================================

@app.route('/')
def index():
    return redirect(url_for('board') if current_user.is_authenticated else url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('board'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash(f'欢迎回来，{user.username}！', 'success')
            return redirect(url_for('board'))
        flash('用户名或密码错误，请重试', 'danger')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('board'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        if not username or not password or not confirm_password:
            flash('用户名和密码不能为空', 'danger')
        elif not 3 <= len(username) <= 20:
            flash('用户名长度需要在 3 到 20 个字符之间', 'danger')
        elif not 5 <= len(password) <= 64:
            flash('密码长度需要在 5 到 64 个字符之间', 'danger')
        elif password != confirm_password:
            flash('两次输入的密码不一致', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('该用户名已被注册', 'danger')
        else:
            user = User(username=username, is_admin=False)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            flash('注册成功，请登录', 'success')
            return redirect(url_for('login'))
    return render_template('register.html')


@app.post('/logout')
@login_required
def logout():
    logout_user()
    flash('你已退出登录', 'info')
    return redirect(url_for('login'))


@app.route('/board')
@login_required
def board():
    filters = read_board_filters()
    query = apply_task_filters(visible_task_query(), filters)
    tasks = query.order_by(Task.position.asc(), Task.id.asc()).all()

    columns = BoardColumn.query.order_by(BoardColumn.id).all()
    tasks_by_column = {column.id: [] for column in columns}
    for task in tasks:
        tasks_by_column.setdefault(task.column_id, []).append(task)

    has_filters = any(
        [filters['q'], filters['priority'], filters['tag'], filters['deadline'], filters['owner']]
    )
    return render_template(
        'board.html',
        columns=columns,
        tasks_by_column=tasks_by_column,
        total_tasks=len(tasks),
        all_total=visible_task_query().count(),
        urgent_count=count_urgent_tasks(tasks),
        filters=filters,
        has_filters=has_filters,
        available_tags=available_tags(),
        owners=User.query.order_by(User.username).all() if current_user.is_admin else [],
        priorities=PRIORITY_LABELS,
        trash_count=trash_task_query().count(),
    )


# =========================================================
# 任务接口
# =========================================================

@app.post('/task/create')
@login_required
def create_task():
    form_data, error = read_task_form()
    if error:
        flash(error, 'danger')
    else:
        create_task_from_form(form_data)
        flash('任务创建成功', 'success')
    return redirect(url_for('board'))


@app.post('/task/<int:task_id>/edit')
@login_required
def edit_task(task_id):
    task = get_task_or_none(task_id)
    if task is None:
        return redirect(url_for('board'))

    form_data, error = read_task_form()
    if error:
        flash(error, 'danger')
        return redirect(url_for('board'))

    old_title = task.title
    task.title = form_data['title']
    task.content = form_data['content']
    task.priority = form_data['priority']
    task.deadline = form_data['deadline']
    task.tags = resolve_tags(form_data['tag_names'])
    if form_data['subtasks'] is not None:
        replace_subtasks(task, form_data['subtasks'])

    if old_title == task.title:
        action = f'编辑任务【{task.title}】'
    else:
        action = f'编辑任务【{old_title}】→【{task.title}】'
    add_log(task.id, action)
    db.session.commit()
    flash('任务已更新', 'success')
    return redirect(url_for('board'))


@app.post('/task/<int:task_id>/delete')
@login_required
def delete_task(task_id):
    task = get_task_or_none(task_id)
    if task is None:
        return redirect(url_for('board'))
    soft_delete_task(task)
    db.session.commit()
    flash('任务已移入垃圾桶，可在垃圾桶中恢复', 'info')
    return redirect(url_for('board'))


# =========================================================
# 垃圾桶
# =========================================================

@app.post('/task/<int:task_id>/trash')
@login_required
def trash_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None or task.is_deleted:
        return jsonify(code=404, msg='任务不存在或已在垃圾桶中'), 404
    if not current_user.is_admin and task.owner_id != current_user.id:
        return jsonify(code=403, msg='你没有权限操作该任务'), 403
    soft_delete_task(task)
    db.session.commit()
    return jsonify(
        code=200,
        msg='任务已移入垃圾桶',
        counts=column_counts(),
        urgent_count=count_urgent_tasks(),
        total_count=visible_task_query().count(),
        trash_count=trash_task_query().count(),
    )


@app.route('/trash')
@login_required
def trash():
    keyword = request.args.get('q', '').strip()[:MAX_TITLE_LENGTH]
    query = trash_task_query()
    if keyword:
        like = f'%{keyword}%'
        query = query.filter(or_(Task.title.ilike(like), Task.content.ilike(like)))
    tasks = query.order_by(Task.deleted_at.desc(), Task.id.desc()).all()
    return render_template('trash.html', tasks=tasks, keyword=keyword)


@app.post('/task/<int:task_id>/restore')
@login_required
def restore_task(task_id):
    task = get_task_or_none(task_id, allow_deleted=True)
    if task is None:
        return redirect(url_for('trash'))
    if not task.is_deleted:
        flash('该任务不在垃圾桶中', 'warning')
        return redirect(url_for('trash'))
    task.is_deleted = False
    task.deleted_at = None
    task.deleted_by = None
    max_position = db.session.query(func.max(Task.position)).filter(
        Task.column_id == task.column_id,
        Task.id != task.id,
    ).scalar()
    task.position = (max_position or 0) + 1
    add_log(task.id, f'从垃圾桶恢复任务【{task.title}】')
    db.session.commit()
    flash('任务已恢复到原栏目末尾', 'success')
    return redirect(url_for('trash'))


@app.post('/task/<int:task_id>/purge')
@login_required
def purge_task(task_id):
    task = get_task_or_none(task_id, allow_deleted=True)
    if task is None:
        return redirect(url_for('trash'))
    if not task.is_deleted:
        flash('只能彻底删除垃圾桶中的任务', 'warning')
        return redirect(url_for('trash'))
    title = task.title
    db.session.delete(task)
    add_log(task_id, f'彻底删除任务【{title}】')
    db.session.commit()
    flash('任务已彻底删除，无法恢复', 'info')
    return redirect(url_for('trash'))


@app.post('/task/move')
@login_required
def move_task():
    task_id = request.form.get('task_id', type=int)
    target_column_id = request.form.get('column_id', type=int)
    task = db.session.get(Task, task_id) if task_id else None
    target_column = db.session.get(BoardColumn, target_column_id) if target_column_id else None
    if task is None:
        return jsonify(code=404, msg='任务不存在'), 404
    if task.is_deleted:
        return jsonify(code=404, msg='任务已在垃圾桶中，请先恢复'), 404
    if target_column is None:
        return jsonify(code=400, msg='目标列不存在'), 400
    if not current_user.is_admin and task.owner_id != current_user.id:
        return jsonify(code=403, msg='你没有权限操作该任务'), 403

    order_ids = []
    for value in request.form.get('order', '').split(','):
        value = value.strip()
        if value.isdigit():
            order_ids.append(int(value))

    if task.column_id == target_column.id:
        if order_ids:
            apply_task_order(target_column.id, order_ids)
            db.session.commit()
            message = '顺序已保存'
        else:
            message = '任务已在当前列'
        return jsonify(
            code=200,
            msg=message,
            urgent=task.is_urgent,
            deadline_label=task.deadline_label,
            finish_time=task.finish_time.strftime('%m-%d %H:%M') if task.finish_time else None,
            counts=column_counts(),
            urgent_count=count_urgent_tasks(),
        )

    old_column_name = task.column.name
    if order_ids:
        task.column = target_column
        apply_task_order(target_column.id, order_ids)
    else:
        max_position = db.session.query(func.max(Task.position)).filter(
            Task.column_id == target_column.id, Task.id != task.id
        ).scalar()
        task.column = target_column
        task.position = (max_position or 0) + 1
    task.finish_time = datetime.now() if target_column.name == DONE_COLUMN_NAME else None
    add_log(task.id, f'把任务【{task.title}】从【{old_column_name}】移动到【{target_column.name}】')
    db.session.commit()
    return jsonify(
        code=200,
        msg='状态更新成功',
        urgent=task.is_urgent,
        deadline_label=task.deadline_label,
        finish_time=task.finish_time.strftime('%m-%d %H:%M') if task.finish_time else None,
        counts=column_counts(),
        urgent_count=count_urgent_tasks(),
        is_done=task.is_done,
    )


@app.route('/task/<int:task_id>')
@login_required
def task_detail(task_id):
    task = get_task_or_none(task_id)
    if task is None:
        return redirect(url_for('board'))
    task_logs = (
        TaskLog.query
        .filter_by(task_id=task.id)
        .order_by(TaskLog.operate_time.desc(), TaskLog.id.desc())
        .limit(20)
        .all()
    )
    return render_template('task_detail.html', task=task, task_logs=task_logs)


@app.post('/task/<int:task_id>/comment')
@login_required
def add_comment(task_id):
    task = get_task_or_none(task_id)
    if task is None:
        return redirect(url_for('board'))
    content = request.form.get('content', '').strip()
    if not content:
        flash('评论内容不能为空', 'danger')
    elif len(content) > MAX_COMMENT_LENGTH:
        flash(f'评论内容不能超过 {MAX_COMMENT_LENGTH} 个字符', 'danger')
    else:
        db.session.add(TaskComment(task_id=task.id, user_id=current_user.id, content=content))
        add_log(task.id, f'评论了任务【{task.title}】')
        db.session.commit()
        flash('评论已发布', 'success')
    return redirect(url_for('task_detail', task_id=task.id) + '#comments')


@app.post('/subtask/<int:subtask_id>/toggle')
@login_required
def toggle_subtask(subtask_id):
    subtask = db.session.get(Subtask, subtask_id)
    if subtask is None:
        flash('子任务不存在', 'warning')
        return redirect(url_for('board'))
    task = subtask.task
    if task.is_deleted:
        flash('任务已在垃圾桶中，请先恢复', 'warning')
        return redirect(url_for('board'))
    if not current_user.is_admin and task.owner_id != current_user.id:
        flash('你没有权限操作该任务', 'danger')
        return redirect(url_for('board'))
    subtask.is_done = not subtask.is_done
    action = f'{"完成" if subtask.is_done else "重新打开"}子任务【{subtask.content}】'
    add_log(task.id, action)
    db.session.commit()
    return redirect(url_for('task_detail', task_id=task.id) + '#subtasks')


@app.route('/logs')
@login_required
def logs():
    query = TaskLog.query
    if not current_user.is_admin:
        query = query.filter(TaskLog.username == current_user.username)
    entries = query.order_by(TaskLog.operate_time.desc(), TaskLog.id.desc()).all()
    return render_template('log.html', logs=entries)


@app.route('/report')
@login_required
def report():
    if not current_user.is_admin:
        flash('数据统计仅管理员可访问', 'danger')
        return redirect(url_for('board'))

    columns = BoardColumn.query.order_by(BoardColumn.id).all()
    column_names = {column.id: column.name for column in columns}
    counts = {name: 0 for name in COLUMN_NAMES}
    rows = (
        db.session.query(Task.column_id, func.count(Task.id))
        .filter(Task.is_deleted.is_(False))
        .group_by(Task.column_id)
        .all()
    )
    for column_id, count in rows:
        if column_id in column_names:
            counts[column_names[column_id]] = count

    total = sum(counts.values())
    done = counts.get(DONE_COLUMN_NAME, 0)
    rate = round(done * 100 / total) if total else 0
    done_id = done_column_id()
    overdue = 0
    if done_id:
        overdue = Task.query.filter(
            Task.is_deleted.is_(False),
            Task.column_id != done_id,
            Task.deadline.isnot(None),
            Task.deadline < datetime.now(),
        ).count()

    stats = [{'name': name, 'value': counts.get(name, 0)} for name in COLUMN_NAMES]
    return render_template(
        'report.html',
        total=total,
        done=done,
        rate=rate,
        overdue=overdue,
        stats=stats,
    )


# =========================================================
# 初始化与错误页
# =========================================================

@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response


@app.context_processor
def inject_globals():
    return {'current_year': datetime.now().year}


@app.errorhandler(404)
def page_not_found(error):
    return render_template('errors/404.html'), 404


@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500


def migrate_schema():
    inspector = sa_inspect(db.engine)
    task_columns = {column['name'] for column in inspector.get_columns('task')}
    if 'priority' not in task_columns:
        db.session.execute(text('ALTER TABLE task ADD COLUMN priority INTEGER NOT NULL DEFAULT 1'))
    if 'position' not in task_columns:
        db.session.execute(text('ALTER TABLE task ADD COLUMN position INTEGER NOT NULL DEFAULT 0'))
    if 'is_deleted' not in task_columns:
        db.session.execute(text('ALTER TABLE task ADD COLUMN is_deleted BOOLEAN NOT NULL DEFAULT 0'))
    if 'deleted_at' not in task_columns:
        db.session.execute(text('ALTER TABLE task ADD COLUMN deleted_at DATETIME'))
    if 'deleted_by' not in task_columns:
        db.session.execute(text('ALTER TABLE task ADD COLUMN deleted_by VARCHAR(20)'))
    db.session.commit()


def normalize_positions():
    for column in BoardColumn.query.all():
        tasks = (
            Task.query.filter_by(column_id=column.id)
            .filter(Task.is_deleted.is_(False))
            .order_by(Task.position, Task.id)
            .all()
        )
        for index, task in enumerate(tasks):
            task.position = index + 1
    db.session.commit()


def init_database():
    db.create_all()
    migrate_schema()

    existing_names = {column.name for column in BoardColumn.query.all()}
    for name in COLUMN_NAMES:
        if name not in existing_names:
            db.session.add(BoardColumn(name=name))
    db.session.commit()

    if User.query.filter_by(username='admin').first() is None:
        admin = User(username='admin', is_admin=True)
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()

    normalize_positions()


with app.app_context():
    init_database()


if __name__ == '__main__':
    app.run(debug=True, port=int(os.environ.get('PORT', '5000')))
