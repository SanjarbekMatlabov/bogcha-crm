from datetime import datetime, timedelta, timezone
from typing import Optional, Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import ExpiredSignatureError, JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

import crud, schemas, database
from database import get_db, UserRole

# --- Konfiguratsiya ---
SECRET_KEY = "YOUR_VERY_SECRET_KEY"  # Buni .env faylidan olish yaxshiroq
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 kun

# --- Parol hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- OAuth2 sxemasi ---
# tokenUrl FastAPI ilovangizdagi token olish endpointiga ishora qilishi kerak
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Session = Depends(get_db)
) -> database.User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except JWTError:
        raise credentials_exception
    
    user = crud.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

async def get_current_active_user(
    current_user: Annotated[database.User, Depends(get_current_user)]
) -> database.User:
    if not current_user.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Inactive user")
    return current_user

# --- Rolga asoslangan kirish uchun Dependencies ---
async def get_current_admin_user(
    current_user: Annotated[database.User, Depends(get_current_active_user)]
) -> database.User:
    if current_user.role != UserRole.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges (admin required)"
        )
    return current_user

async def get_current_manager_user(
    current_user: Annotated[database.User, Depends(get_current_active_user)]
) -> database.User:
    if current_user.role not in [UserRole.admin, UserRole.manager]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges (manager or admin required)"
        )
    return current_user

async def get_current_chef_user(
    current_user: Annotated[database.User, Depends(get_current_active_user)]
) -> database.User:
    if current_user.role not in [UserRole.admin, UserRole.chef]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges (chef or admin required)"
        )
    return current_user

# Umumiy autentifikatsiyadan o'tgan foydalanuvchi (har qanday rol)
async def get_authenticated_user(
    current_user: Annotated[database.User, Depends(get_current_active_user)]
) -> database.User:
    return current_user
def decode_username_from_token(token: str) -> Optional[str]:
    """
    Berilgan JWT tokendan foydalanuvchi nomini (sub claim) ajratib oladi.
    Agar token yaroqsiz yoki muddati o'tgan bo'lsa, None qaytaradi.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: Optional[str] = payload.get("sub")
        return username
    except ExpiredSignatureError:
        print("Token muddati o'tgan (log uchun)") # Buni loglash mumkin
        return "expired_token" # Maxsus qiymat qaytarish mumkin
    except JWTError:
        print("Token validatsiya xatosi (log uchun)") # Buni loglash mumkin
        return "invalid_token" # Maxsus qiymat qaytarish mumkin
    return None