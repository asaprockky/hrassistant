from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from .routers import login

app = FastAPI()

app.include_router(login.routers, prefix= "/auth", tags= ["authentication"])


@app.get("/test/")
async def test():
    return {"Hello World"}