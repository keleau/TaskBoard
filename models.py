from datetime import datetime, timedelta

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

COLUMN_NAMES = ('待办', '进行中', '已完成')
DONE_COLUMN_NAME = '已完成'

PRIORITY_LABELS = {0: '低', 1: '中', 2: '高'}
PRIORITY_CLASSES = {0: 'low', 1: 'medium', 2: 'high'}


class User(UserMixin, db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

    tasks = db.relationship('Task', backref='owner', lazy=True)

    def set_password(self, raw_password):
        self.password = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password, raw_password)


class BoardColumn(db.Model):
    __tablename__ = 'column'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

    tasks = db.relationship('Task', backref='column', lazy=True)


class Tag(db.Model):
    __tablename__ = 'tag'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), unique=True, nullable=False)

    @property
    def color_index(self):
        return self.id % 6


task_tag = db.Table(
    'task_tag',
    db.Column('task_id', db.Integer, db.ForeignKey('task.id'), primary_key=True),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'), primary_key=True),
)


class Task(db.Model):
    __tablename__ = 'task'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, default='')
    column_id = db.Column(db.Integer, db.ForeignKey('column.id'), nullable=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    deadline = db.Column(db.DateTime)
    create_time = db.Column(db.DateTime, default=datetime.now)
    finish_time = db.Column(db.DateTime)
    priority = db.Column(db.Integer, default=1, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)
    is_deleted = db.Column(db.Boolean, default=False, nullable=False)
    deleted_at = db.Column(db.DateTime)
    deleted_by = db.Column(db.String(20))

    tags = db.relationship(
        'Tag',
        secondary=task_tag,
        lazy='selectin',
        order_by='Tag.id',
    )
    subtasks = db.relationship(
        'Subtask',
        backref='task',
        lazy='selectin',
        cascade='all, delete-orphan',
        order_by='Subtask.position',
    )
    comments = db.relationship(
        'TaskComment',
        backref='task',
        lazy='selectin',
        cascade='all, delete-orphan',
        order_by='TaskComment.create_time',
    )

    @property
    def is_done(self):
        return self.column is not None and self.column.name == DONE_COLUMN_NAME

    @property
    def is_urgent(self):
        if not self.deadline or self.is_done:
            return False
        return self.deadline <= datetime.now() + timedelta(hours=24)

    @property
    def deadline_label(self):
        if not self.deadline:
            return ''
        return '已逾期' if self.deadline < datetime.now() else '即将到期'

    @property
    def priority_label(self):
        return PRIORITY_LABELS.get(self.priority, '中')

    @property
    def priority_class(self):
        return PRIORITY_CLASSES.get(self.priority, 'medium')

    @property
    def subtask_total(self):
        return len(self.subtasks)

    @property
    def subtask_done_count(self):
        return sum(1 for subtask in self.subtasks if subtask.is_done)

    @property
    def subtask_percent(self):
        if not self.subtask_total:
            return 0
        return round(self.subtask_done_count * 100 / self.subtask_total)

    @property
    def tag_names(self):
        return ', '.join(tag.name for tag in self.tags)

    @property
    def subtasks_payload(self):
        return [
            {'content': subtask.content, 'is_done': subtask.is_done}
            for subtask in self.subtasks
        ]

    @property
    def comment_count(self):
        return len(self.comments)


class Subtask(db.Model):
    __tablename__ = 'subtask'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    content = db.Column(db.String(100), nullable=False)
    is_done = db.Column(db.Boolean, default=False, nullable=False)
    position = db.Column(db.Integer, default=0, nullable=False)


class TaskComment(db.Model):
    __tablename__ = 'task_comment'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    create_time = db.Column(db.DateTime, default=datetime.now)

    author = db.relationship('User', backref=db.backref('comments', lazy='dynamic'))


class TaskLog(db.Model):
    __tablename__ = 'task_log'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    operate_time = db.Column(db.DateTime, default=datetime.now)
