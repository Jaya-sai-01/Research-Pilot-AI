import secrets
import smtplib
from email.message import EmailMessage
from hashlib import sha256
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Any
from jose import jwt, JWTError

from app.core.database import get_db
from app.core.config import settings
from app.core.security import verify_password, get_password_hash, create_access_token
from app.models.password_reset import PasswordResetOTP
from app.models.security_log import SecurityLog
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    Token,
    TokenData,
    UserLogin,
    UserOut,
    UserRegister,
    VerifyOTPRequest,
    VerifyOTPResponse,
)

router = APIRouter(prefix="/auth", tags=["auth"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/login-oauth")

OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_MAX_RESENDS = 3
OTP_EMAIL_LIMIT_PER_HOUR = 5
OTP_IP_LIMIT_PER_HOUR = 10
REMEMBER_ME_DAYS = 30
GENERIC_OTP_MESSAGE = "If an account exists for this email, a verification code has been sent."


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_secret(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def ensure_auth_schema(db: Session) -> None:
    try:
        db.execute(text("CREATE TABLE IF NOT EXISTS security_logs (id INTEGER PRIMARY KEY, event_type VARCHAR NOT NULL, email VARCHAR NOT NULL, ip_address VARCHAR NOT NULL, created_at DATETIME NOT NULL)"))
        columns = {row[1] for row in db.execute(text("PRAGMA table_info(users)")).fetchall()}
        if "session_version" not in columns:
            db.execute(text("ALTER TABLE users ADD COLUMN session_version INTEGER NOT NULL DEFAULT 0"))
        otp_columns = {row[1] for row in db.execute(text("PRAGMA table_info(password_reset_otps)")).fetchall()}
        if "generated_at" not in otp_columns:
            db.execute(text("ALTER TABLE password_reset_otps ADD COLUMN generated_at DATETIME"))
            db.execute(text("UPDATE password_reset_otps SET generated_at = created_at WHERE generated_at IS NULL"))
        if "attempt_count" not in otp_columns:
            db.execute(text("ALTER TABLE password_reset_otps ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0"))
        if "resend_count" not in otp_columns:
            db.execute(text("ALTER TABLE password_reset_otps ADD COLUMN resend_count INTEGER NOT NULL DEFAULT 0"))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"Auth schema compatibility check failed: {exc}")


def log_security_event(db: Session, event_type: str, email: str, ip_address: str) -> None:
    try:
        db.add(SecurityLog(event_type=event_type, email=normalize_email(email), ip_address=ip_address))
        db.commit()
    except Exception as exc:
        db.rollback()
        print(f"Security log write failed: {exc}")


def enforce_otp_rate_limit(db: Session, email: str, ip_address: str) -> None:
    since = datetime.utcnow() - timedelta(hours=1)
    email_count = db.query(SecurityLog).filter(
        SecurityLog.event_type == "otp_request",
        SecurityLog.email == email,
        SecurityLog.created_at >= since,
    ).count()
    ip_count = db.query(SecurityLog).filter(
        SecurityLog.event_type == "otp_request",
        SecurityLog.ip_address == ip_address,
        SecurityLog.created_at >= since,
    ).count()
    if email_count >= OTP_EMAIL_LIMIT_PER_HOUR or ip_count >= OTP_IP_LIMIT_PER_HOUR:
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")


def invalidate_open_otps(db: Session, user_id: int) -> None:
    db.query(PasswordResetOTP).filter(
        PasswordResetOTP.user_id == user_id,
        PasswordResetOTP.used_at.is_(None),
    ).update({"used_at": datetime.utcnow()})


def create_otp_record(db: Session, user_id: int, otp: str, resend_count: int = 0) -> PasswordResetOTP:
    now = datetime.utcnow()
    db_obj = PasswordResetOTP(
        user_id=user_id,
        otp_hash=hash_secret(otp),
        generated_at=now,
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempt_count=0,
        resend_count=resend_count,
    )
    db.add(db_obj)
    return db_obj


def send_password_reset_otp(email: str, otp: str) -> None:
    subject = "ResearchPilot AI password reset OTP"
    body = (
        "Your ResearchPilot AI password reset OTP is:\n\n"
        f"{otp}\n\n"
        "This code expires in 5 minutes. If you did not request this, you can ignore this email."
    )
    if not settings.SMTP_HOST:
        print(f"[ResearchPilot Password Reset] OTP for {email}: {otp}")
        log_path = Path(settings.UPLOAD_DIR).parent / "password_reset_otps.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{datetime.utcnow().isoformat()}Z {email} OTP={otp}\n")
        return

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM or settings.SMTP_FROM_EMAIL
    message["To"] = email
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
        if settings.SMTP_USE_TLS:
            server.starttls()
        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        server.send_message(message)

def get_current_user(db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)) -> User:
    ensure_auth_schema(db)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        email: str = payload.get("sub")
        token_version = int(payload.get("ver") or 0)
        if email is None:
            raise credentials_exception
        token_data = TokenData(email=normalize_email(email))
    except JWTError:
        raise credentials_exception
        
    user = db.query(User).filter(User.email == token_data.email).first()
    if user is None:
        raise credentials_exception
    if int(user.session_version or 0) != token_version:
        raise credentials_exception
    return user

@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(user_in: UserRegister, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    # Check if user already exists
    email = normalize_email(user_in.email)
    existing_user = db.query(User).filter(User.email == email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account already exists with this email. Please sign in instead.",
        )
        
    db_obj = User(
        email=email,
        hashed_password=get_password_hash(user_in.password),
        session_version=0,
    )
    db.add(db_obj)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account already exists with this email. Please sign in instead.",
        )
    db.refresh(db_obj)
    return db_obj

@router.post("/login", response_model=Token)
def login_json(user_in: UserLogin, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(user_in.email)
    ip_address = client_ip(request)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(user_in.password, user.hashed_password):
        log_security_event(db, "login_failure", email, ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password. Please check your credentials and try again."
        )

    expiry = timedelta(days=REMEMBER_ME_DAYS) if user_in.remember_me else None
    access_token = create_access_token(subject=user.email, expires_delta=expiry, session_version=user.session_version or 0)
    log_security_event(db, "login_success", email, ip_address)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user
    }

@router.post("/login-oauth")
def login_oauth(request: Request, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(form_data.username)
    ip_address = client_ip(request)
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        log_security_event(db, "login_failure", email, ip_address)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password. Please check your credentials and try again."
        )
        
    access_token = create_access_token(subject=user.email, session_version=user.session_version or 0)
    log_security_event(db, "login_success", email, ip_address)
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "created_at": user.created_at
        }
    }

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)) -> Any:
    return current_user


@router.post("/forgot-password", response_model=MessageResponse)
def forgot_password(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(req.email)
    ip_address = client_ip(request)
    enforce_otp_rate_limit(db, email, ip_address)
    log_security_event(db, "otp_request", email, ip_address)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"message": GENERIC_OTP_MESSAGE}

    otp = f"{secrets.randbelow(1000000):06d}"
    invalidate_open_otps(db, user.id)
    create_otp_record(db, user.id, otp, resend_count=0)
    db.commit()

    try:
        send_password_reset_otp(email, otp)
    except Exception as exc:
        print(f"Failed to send password reset OTP to {email}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not send reset OTP. Please try again later.",
        )
    log_security_event(db, "otp_sent", email, ip_address)

    return {"message": GENERIC_OTP_MESSAGE}


@router.post("/resend-otp", response_model=MessageResponse)
def resend_otp(req: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(req.email)
    ip_address = client_ip(request)
    enforce_otp_rate_limit(db, email, ip_address)
    log_security_event(db, "otp_request", email, ip_address)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"message": GENERIC_OTP_MESSAGE}

    latest = db.query(PasswordResetOTP).filter(
        PasswordResetOTP.user_id == user.id,
    ).order_by(PasswordResetOTP.created_at.desc()).first()
    resend_count = int(latest.resend_count or 0) + 1 if latest else 1
    if resend_count > OTP_MAX_RESENDS:
        raise HTTPException(status_code=429, detail="Maximum resend attempts exceeded. Request a new OTP.")

    otp = f"{secrets.randbelow(1000000):06d}"
    invalidate_open_otps(db, user.id)
    create_otp_record(db, user.id, otp, resend_count=resend_count)
    db.commit()
    try:
        send_password_reset_otp(email, otp)
    except Exception as exc:
        print(f"Failed to resend password reset OTP to {email}: {exc}")
        raise HTTPException(status_code=500, detail="Could not send reset OTP. Please try again later.")
    log_security_event(db, "otp_sent", email, ip_address)
    return {"message": GENERIC_OTP_MESSAGE}


@router.post("/verify-otp", response_model=VerifyOTPResponse)
def verify_otp(req: VerifyOTPRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(req.email)
    ip_address = client_ip(request)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        log_security_event(db, "otp_verification_failure", email, ip_address)
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    otp_record = db.query(PasswordResetOTP).filter(
        PasswordResetOTP.user_id == user.id,
        PasswordResetOTP.used_at.is_(None),
        PasswordResetOTP.verified_at.is_(None),
    ).order_by(PasswordResetOTP.created_at.desc()).first()

    if not otp_record:
        log_security_event(db, "otp_verification_failure", email, ip_address)
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    if otp_record.expires_at < datetime.utcnow():
        otp_record.used_at = datetime.utcnow()
        db.commit()
        log_security_event(db, "otp_verification_failure", email, ip_address)
        raise HTTPException(status_code=400, detail="OTP expired. Please request a new OTP.")

    if otp_record.otp_hash != hash_secret(req.otp):
        otp_record.attempt_count = int(otp_record.attempt_count or 0) + 1
        if otp_record.attempt_count >= OTP_MAX_ATTEMPTS:
            otp_record.used_at = datetime.utcnow()
            db.commit()
            log_security_event(db, "otp_verification_failure", email, ip_address)
            raise HTTPException(status_code=400, detail="Maximum verification attempts exceeded. Request a new OTP.")
        db.commit()
        log_security_event(db, "otp_verification_failure", email, ip_address)
        raise HTTPException(status_code=400, detail="Invalid or expired OTP.")

    reset_token = secrets.token_urlsafe(32)
    otp_record.verified_at = datetime.utcnow()
    otp_record.reset_token_hash = hash_secret(reset_token)
    db.commit()
    log_security_event(db, "otp_verification_success", email, ip_address)

    return {
        "reset_token": reset_token,
        "message": "OTP verified. You can now create a new password.",
    }


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(req: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)) -> Any:
    ensure_auth_schema(db)
    email = normalize_email(req.email)
    ip_address = client_ip(request)
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail="Invalid password reset request.")

    token_hash = hash_secret(req.reset_token)
    otp_record = db.query(PasswordResetOTP).filter(
        PasswordResetOTP.user_id == user.id,
        PasswordResetOTP.reset_token_hash == token_hash,
        PasswordResetOTP.used_at.is_(None),
    ).order_by(PasswordResetOTP.created_at.desc()).first()

    if (
        not otp_record
        or not otp_record.verified_at
        or otp_record.expires_at < datetime.utcnow()
    ):
        raise HTTPException(status_code=400, detail="Invalid or expired password reset request.")

    user.hashed_password = get_password_hash(req.new_password)
    user.session_version = int(user.session_version or 0) + 1
    otp_record.used_at = datetime.utcnow()
    db.commit()
    log_security_event(db, "password_reset", email, ip_address)

    return {"message": "Password reset successful. You can now sign in."}
