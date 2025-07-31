import uvicorn
from fastapi import FastAPI
from app.routers import tasks

app = FastAPI()

app.include_router(tasks.router)

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
