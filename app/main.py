from typing import cast

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import UJSONResponse

from app.api.routes.chat import chat_router
from app.api.routes.websocket import ws_router
from app.config.database import Base, engine
from app.config.settings import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(
    debug=cast(bool, settings.fastapi_kwargs["debug"]),
    docs_url=cast(str | None, settings.fastapi_kwargs["docs_url"]),
    openapi_prefix=cast(str, settings.fastapi_kwargs["openapi_prefix"]),
    openapi_url=cast(str | None, settings.fastapi_kwargs["openapi_url"]),
    redoc_url=cast(str | None, settings.fastapi_kwargs["redoc_url"]),
    title=cast(str, settings.fastapi_kwargs["title"]),
    version=cast(str, settings.fastapi_kwargs["version"]),
    default_response_class=UJSONResponse,
)

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

    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
