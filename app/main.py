from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.chat import chat_router
from app.api.routes.websocket import ws_router
from app.config.database import Base, engine
from app.config.settings import HOST, PORT

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Websocket Chat")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(ws_router, prefix="/api", tags=["websocket"])


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
