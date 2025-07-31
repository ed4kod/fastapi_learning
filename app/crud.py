from sqlalchemy.orm import Session
from . import models, schemas
from .models import Task


def get_task(db: Session, task_id: int):
    return db.query(models.Task).filter(models.Task.id == task_id).first()


def get_tasks(db: Session):
    return db.query(models.Task).all()


def create_task(db: Session, task: schemas.TaskCreate):
    db_task = models.Task(title=task.title)
    db.add(db_task)
    db.commit()
    db.refresh(db_task)
    return db_task


def update_task(db: Session, task_id: int, data: schemas.TaskUpdate):
    task = get_task(db, task_id)
    if task:
        if data.title is not None:
            task.title = data.title
        db.commit()
        db.refresh(task)
    return task


def delete_task(db: Session, task_id: int):
    task = get_task(db, task_id)
    if task:
        db.delete(task)
        db.commit()
    return task


def mark_done(db: Session, task_id: int, done: bool):
    task = get_task(db, task_id)
    if task:
        task.done = done
        db.commit()
        db.refresh(task)
    return task


def mark_task_done(db: Session, task_id: int):
    task = db.query(Task).get(task_id)
    if not task:
        return None
    task.done = True
    db.commit()
    db.refresh(task)
    return task


def mark_task_undone(db: Session, task_id: int):
    task = db.query(Task).get(task_id)
    if not task:
        return None
    task.done = False
    db.commit()
    db.refresh(task)
    return task
