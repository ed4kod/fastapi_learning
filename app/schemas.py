from pydantic import BaseModel
from typing import Optional


class TaskBase(BaseModel):
    title: str
    user_id: int


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


class TaskInDB(TaskBase):
    id: int
    done: bool

    class Config:
        from_attributes = True
