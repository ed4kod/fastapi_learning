from pydantic import BaseModel
from typing import Optional


class TaskBase(BaseModel):
    title: str
    done: bool = False
    done_by: Optional[str] = None


class TaskCreate(TaskBase):
    user_id: int


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    done: Optional[bool] = None


class TaskInDB(TaskBase):
    id: int

    class Config:
        from_attributes = True
