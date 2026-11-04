from fastapi import FastAPI

from router import api_router
from library.photo_http import install_photo_log_filter

install_photo_log_filter()
app = FastAPI(title="KAIFind API", version="0.1.0")
app.include_router(api_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}
