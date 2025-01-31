from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat_websocket import router as websocket_router
from app.api.routes.http_endpoints import router as http_router
from app.config.env import HOST, PORT
from app.db.database import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Websocket Chat")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(http_router, prefix="/api", tags=["chat"])
app.include_router(websocket_router, prefix="/api", tags=["websocket"])


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
