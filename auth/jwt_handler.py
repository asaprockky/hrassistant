from datetime import datetime, timedelta
from jose import JWTError, jwt

# Secret key for signing the token
SECRET_KEY = "supersecretkey123"  # ⚠️ keep this hidden (use env file)
ALGORITHM = "HS256"               # standard algorithm
ACCESS_TOKEN_EXPIRE_MINUTES = 60  # token lasts 1 hour


def create_access_token(data: dict):
    """Generates a new JWT access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})  # add expiry time
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_access_token(token: str):
    """Verifies token validity and decodes it."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # contains user info
    except JWTError:
        return None
