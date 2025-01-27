from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine
from app.config.env import HOST, PORT
from app.api.routes.http_endpoints import router as http_router
from app.api.routes.chat_websocket import router as websocket_router

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Chat Application")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(http_router, prefix="/api", tags=["chat"])
app.include_router(websocket_router, tags=["websocket"])


@app.get("/")
async def root():
    return {"message": "Welcome to the Chat Application"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
