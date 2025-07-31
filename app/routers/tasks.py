from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app import crud, schemas
from app.config import SessionLocal

router = APIRouter(
    prefix="/tasks",
    tags=["tasks"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post(
    "/",
    response_model=schemas.TaskInDB,
    status_code=status.HTTP_201_CREATED,
    summary="Создать задачу"
)
def create_task(task: schemas.TaskCreate, db: Session = Depends(get_db)):
    return crud.create_task(db, task)


@router.get(
    "/",
    response_model=list[schemas.TaskInDB],
    summary="Получить список всех задач"
)
def get_all_tasks(db: Session = Depends(get_db)):
    return crud.get_tasks(db)


@router.get(
    "/{task_id}",
    response_model=schemas.TaskInDB,
    summary="Получить задачу по ID"
)
def get_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.patch(
    "/{task_id}",
    response_model=schemas.TaskInDB,
    summary="Переименовать задачу"
)
def update_task(task_id: int, update: schemas.TaskUpdate, db: Session = Depends(get_db)):
    task = crud.update_task(db, task_id, update)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить задачу"
)
def delete_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.delete_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return None


@router.put(
    "/{task_id}/done",
    response_model=schemas.TaskInDB,
    summary="Отметить задачу: выполнено",
    status_code=status.HTTP_200_OK
)
def complete_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.mark_task_done(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task


@router.put(
    "/{task_id}/undone",
    response_model=schemas.TaskInDB,
    summary="Отметить задачу: не выполнено",
    status_code=status.HTTP_200_OK
)
def undo_task(task_id: int, db: Session = Depends(get_db)):
    task = crud.mark_task_undone(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return task
