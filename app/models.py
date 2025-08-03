from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.sql import func  # для CURRENT_TIMESTAMP
from .config import Base


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    done = Column(Boolean, default=False)

    user_id = Column(Integer, index=True)  # Telegram user ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
