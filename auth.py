import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Optional

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from database import get_db
from models import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-in-production-make-it-long-and-random")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# SMTP configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "")

# Encryption key for API keys
ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY", "")
if not ENCRYPTION_KEY:
    # Auto-generate and warn (in production, set this in .env)
    ENCRYPTION_KEY = Fernet.generate_key().decode()
    print(f"WARNING: ENCRYPTION_KEY not set. Generated temporary key. Set ENCRYPTION_KEY in .env for persistence.")

_fernet = Fernet(ENCRYPTION_KEY.encode() if isinstance(ENCRYPTION_KEY, str) else ENCRYPTION_KEY)


def encrypt_api_key(plain: str) -> str:
    return _fernet.encrypt(plain.encode()).decode()


def decrypt_api_key(encrypted: str) -> str:
    return _fernet.decrypt(encrypted.encode()).decode()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def create_verification_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=24)
    data = {"sub": email, "type": "email_verify", "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_email_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "email_verify":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def create_password_reset_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=1)
    data = {"sub": email, "type": "password_reset", "exp": expire}
    return jwt.encode(data, SECRET_KEY, algorithm=ALGORITHM)


def verify_password_reset_token(token: str) -> Optional[str]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        return payload.get("sub")
    except JWTError:
        return None


def send_email(to_email: str, subject: str, html_body: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        print(f"SMTP not configured. Email to {to_email}: {subject}")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = SMTP_FROM or SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        if SMTP_PORT == 465:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        return True
    except Exception as e:
        print(f"Email send failed: {e}")
        return False


def send_verification_email(email: str, token: str, base_url: str) -> bool:
    verify_url = f"{base_url}/verify-email?token={token}"
    html = f"""
    <html>
    <body style="font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 2rem;">
        <h2 style="color: #4f46e5;">Glossarium - E-Mail bestätigen</h2>
        <p>Bitte klicke auf den folgenden Link, um deine E-Mail-Adresse zu bestätigen:</p>
        <p><a href="{verify_url}" style="display: inline-block; padding: 0.75rem 1.5rem; background: #4f46e5; color: white; text-decoration: none; border-radius: 0.5rem; font-weight: 600;">E-Mail bestätigen</a></p>
        <p style="color: #64748b; font-size: 0.875rem;">Dieser Link ist 24 Stunden gültig.</p>
        <p style="color: #64748b; font-size: 0.75rem;">Falls du dich nicht registriert hast, ignoriere diese E-Mail.</p>
    </body>
    </html>
    """
    return send_email(email, "Glossarium - E-Mail bestätigen", html)


def send_password_reset_email(email: str, token: str, base_url: str) -> bool:
    reset_url = f"{base_url}/reset-password?token={token}"
    html = f"""
    <html>
    <body style="font-family: -apple-system, sans-serif; max-width: 500px; margin: 0 auto; padding: 2rem;">
        <h2 style="color: #4f46e5;">Glossarium - Passwort zurücksetzen</h2>
        <p>Klicke auf den folgenden Link, um ein neues Passwort zu setzen:</p>
        <p><a href="{reset_url}" style="display: inline-block; padding: 0.75rem 1.5rem; background: #4f46e5; color: white; text-decoration: none; border-radius: 0.5rem; font-weight: 600;">Passwort zurücksetzen</a></p>
        <p style="color: #64748b; font-size: 0.875rem;">Dieser Link ist 1 Stunde gültig.</p>
        <p style="color: #64748b; font-size: 0.75rem;">Falls du kein neues Passwort angefordert hast, ignoriere diese E-Mail.</p>
    </body>
    </html>
    """
    return send_email(email, "Glossarium - Passwort zurücksetzen", html)


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, username: str, password: str, email: str = None) -> User:
    hashed_password = get_password_hash(password)
    user = User(
        username=username,
        password_hash=hashed_password,
        email=email,
        email_verified=False,
        created_at=datetime.utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_current_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get("access_token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            return None
    except JWTError:
        return None
    user = get_user_by_username(db, username)
    return user


async def require_auth(request: Request, db: Session = Depends(get_db)) -> User:
    user = await get_current_user(request, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"}
        )
    return user
