from fastapi import FastAPI
from app.telegram_bot.runner import lifespan
from app.routers import tasks

app = FastAPI(lifespan=lifespan)
app.include_router(tasks.router)