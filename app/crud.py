from typing import Optional
from sqlalchemy.orm import Session
from .models import Task
from . import schemas


def get_task(db: Session, task_id: int) -> Optional[Task]:
    return db.query(Task).filter(Task.id == task_id).first()


def get_tasks(db: Session, user_id: int) -> list[Task]:
    return db.query(Task).filter(Task.user_id == user_id).all()


def create_task(db: Session, task: schemas.TaskCreate) -> Task:
    db_task = Task(title=task.title, user_id=task.user_id)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_task(db: Session, task_id: int, data: schemas.TaskUpdate) -> Optional[Task]:
    task = get_task(db, task_id)
    if task and data.title is not None:
        task.title = data.title
        db.commit()
        db.refresh(task)
    return task


def delete_task(db: Session, task_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if task:
        db.delete(task)
        db.commit()
    return task


def mark_done(db: Session, task_id: int, done: bool) -> Optional[Task]:
    task = get_task(db, task_id)
    if task:
        task.done = done
        db.commit()
        db.refresh(task)
    return task


def mark_task_done(db: Session, task_id: int, done_by: str) -> Optional[Task]:
    task = get_task(db, task_id)
    if task:
        task.done = True
        task.done_by = done_by
        db.commit()
        db.refresh(task)
    return task


def mark_task_undone(db: Session, task_id: int) -> Optional[Task]:
    task = get_task(db, task_id)
    if task:
        task.done = False
        task.done_by = None
        db.commit()
        db.refresh(task)
    return task
