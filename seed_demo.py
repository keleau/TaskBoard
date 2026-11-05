"""生成演示数据：python seed_demo.py [--reset]"""
import sys
from datetime import datetime, timedelta

from app import app, init_database
from models import BoardColumn, Subtask, Tag, Task, TaskComment, TaskLog, User, db

DEMO_TASKS = [
    {
        'owner': 'admin',
        'column': '待办',
        'title': '准备答辩演示脚本',
        'content': '按 5 分钟节奏梳理登录、拖拽、统计与番茄钟演示流程。',
        'priority': 2,
        'deadline_hours': 20,
        'create_hours': -6,
        'tags': ['答辩', '课程设计'],
        'subtasks': [('梳理演示流程', True), ('准备讲解稿', True), ('录制演示视频', False)],
    },
    {
        'owner': 'admin',
        'column': '待办',
        'title': '整理项目 README 与截图',
        'content': '补充功能截图、技术栈说明和本地运行步骤。',
        'priority': 1,
        'deadline_hours': 72,
        'create_hours': -2,
        'tags': ['文档'],
        'subtasks': [('补充功能截图', False), ('校对运行步骤', False)],
    },
    {
        'owner': 'demo',
        'column': '待办',
        'title': '注册登录与权限校验',
        'content': '验证普通用户只能看到自己的任务，管理员可以查看全局数据。',
        'priority': 0,
        'deadline_hours': None,
        'create_hours': -20,
        'tags': ['课程设计'],
        'subtasks': [('测试普通用户视图', True), ('测试管理员视图', False)],
    },
    {
        'owner': 'demo',
        'column': '待办',
        'title': '设计任务详情页交互',
        'content': '把子任务、评论和操作记录集中到详情页，减少看板卡片的信息密度。',
        'priority': 1,
        'deadline_hours': -24,
        'create_hours': -30,
        'tags': ['前端'],
        'subtasks': [('梳理页面结构', True), ('补充空状态', False)],
    },
    {
        'owner': 'admin',
        'column': '进行中',
        'title': '完成课程设计报告初稿',
        'content': '整理需求分析、系统设计与核心代码说明，输出 Markdown 初稿。',
        'priority': 2,
        'deadline_hours': 8,
        'create_hours': -26,
        'tags': ['文档', '课程设计'],
        'subtasks': [
            ('需求分析', True),
            ('系统设计', True),
            ('核心代码说明', False),
            ('全文校对', False),
        ],
    },
    {
        'owner': 'demo',
        'column': '进行中',
        'title': '看板拖拽交互联调',
        'content': '验证跨列拖动、同列排序和拖入垃圾桶删除的完整流程。',
        'priority': 1,
        'deadline_hours': 48,
        'create_hours': -12,
        'tags': ['前端'],
        'subtasks': [('跨列拖动', True), ('同列排序', False)],
    },
    {
        'owner': 'admin',
        'column': '已完成',
        'title': '项目初始化与数据库建模',
        'content': '完成 Flask 工程搭建、模型设计与数据库初始化脚本。',
        'priority': 1,
        'deadline_hours': -48,
        'finish_hours': -26,
        'create_hours': -96,
        'tags': ['课程设计'],
        'subtasks': [('创建数据表', True), ('初始化管理员', True)],
    },
    {
        'owner': 'demo',
        'column': '已完成',
        'title': '需求分析文档',
        'content': '梳理用户故事、功能边界与验收标准。',
        'priority': 0,
        'deadline_hours': None,
        'finish_hours': -50,
        'create_hours': -120,
        'tags': ['文档'],
        'subtasks': [('用户故事', True), ('验收标准', True)],
    },
]


def reset_database():
    db.drop_all()
    db.create_all()
    init_database()


def seed():
    now = datetime.now()
    if Task.query.count() > 0:
        print('数据库中已有任务，跳过生成。需要重置请执行：python seed_demo.py --reset')
        return

    demo_user = User.query.filter_by(username='demo').first()
    if demo_user is None:
        demo_user = User(username='demo', is_admin=False)
        demo_user.set_password('demo123')
        db.session.add(demo_user)
        db.session.flush()

    columns = {column.name: column for column in BoardColumn.query.all()}
    tags = {}
    for name in ('课程设计', '答辩', '前端', '文档'):
        tag = Tag.query.filter_by(name=name).first()
        if tag is None:
            tag = Tag(name=name)
            db.session.add(tag)
        tags[name] = tag
    db.session.flush()

    users = {'admin': User.query.filter_by(username='admin').first(), 'demo': demo_user}
    positions = {name: 1 for name in columns}

    for item in DEMO_TASKS:
        owner = users[item['owner']]
        column = columns[item['column']]
        deadline = None
        if item['deadline_hours'] is not None:
            deadline = now + timedelta(hours=item['deadline_hours'])
        finish_time = None
        if item.get('finish_hours') is not None:
            finish_time = now + timedelta(hours=item['finish_hours'])
        create_time = now + timedelta(hours=item.get('create_hours', -24))

        task = Task(
            title=item['title'],
            content=item['content'],
            column_id=column.id,
            owner_id=owner.id,
            priority=item['priority'],
            deadline=deadline,
            finish_time=finish_time,
            create_time=create_time,
            position=positions[column.name],
        )
        positions[column.name] += 1
        task.tags = [tags[name] for name in item['tags']]
        for index, (content, is_done) in enumerate(item.get('subtasks', [])):
            task.subtasks.append(Subtask(content=content, is_done=is_done, position=index))
        db.session.add(task)
        db.session.flush()
        db.session.add(
            TaskLog(
                task_id=task.id,
                username=owner.username,
                action=f'创建任务【{task.title}】',
                operate_time=create_time,
            )
        )
        if finish_time:
            db.session.add(
                TaskLog(
                    task_id=task.id,
                    username=owner.username,
                    action=f'把任务【{task.title}】从【进行中】移动到【已完成】',
                    operate_time=finish_time,
                )
            )

    report_task = Task.query.filter_by(title='完成课程设计报告初稿').first()
    if report_task:
        db.session.add(
            TaskComment(
                task_id=report_task.id,
                user_id=users['admin'].id,
                content='报告结构已经确认，今天把系统设计部分补完。',
            )
        )

    trashed = Task(
        title='旧版需求草稿',
        content='已经被新版需求文档替代，保留在垃圾桶中演示恢复功能。',
        column_id=columns['待办'].id,
        owner_id=demo_user.id,
        priority=0,
        is_deleted=True,
        deleted_at=now - timedelta(hours=5),
        deleted_by='demo',
        position=99,
        create_time=now - timedelta(days=3),
    )
    db.session.add(trashed)
    db.session.commit()

    print('演示数据生成完成：admin / admin123，demo / demo123')
    print(f'当前任务数：{Task.query.filter(Task.is_deleted.is_(False)).count()} 个')


if __name__ == '__main__':
    with app.app_context():
        if '--reset' in sys.argv:
            reset_database()
        seed()
