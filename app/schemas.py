from pydantic import BaseModel
from typing import Optional


class TaskBase(BaseModel):
    title: str


class TaskCreate(TaskBase):
    pass


class TaskUpdate(BaseModel):
    title: Optional[str] = None


class TaskInDB(TaskBase):
    id: int
    done: bool

    class Config:
        from_attributes = True
