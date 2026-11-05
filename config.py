import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'task-board-course-design-secret')
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(INSTANCE_DIR, 'task_board.db'),
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
