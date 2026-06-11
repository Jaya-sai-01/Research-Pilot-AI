import re

from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime
from typing import Optional

PASSWORD_MESSAGE = (
    "Password must be 8-64 characters and include uppercase, lowercase, number, and special character."
)


def validate_password_strength(value: str) -> str:
    if not 8 <= len(value) <= 64:
        raise ValueError(PASSWORD_MESSAGE)
    checks = (
        re.search(r"[A-Z]", value),
        re.search(r"[a-z]", value),
        re.search(r"\d", value),
        re.search(r"[^A-Za-z0-9]", value),
    )
    if not all(checks):
        raise ValueError(PASSWORD_MESSAGE)
    return value


class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=64)

    @field_validator("password")
    @classmethod
    def password_strength(cls, value: str) -> str:
        return validate_password_strength(value)

class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False

class UserOut(BaseModel):
    id: int
    email: EmailStr
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserOut

class TokenData(BaseModel):
    email: Optional[str] = None

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6)

class VerifyOTPResponse(BaseModel):
    reset_token: str
    message: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    reset_token: str
    new_password: str = Field(min_length=8, max_length=64)

    @field_validator("new_password")
    @classmethod
    def new_password_strength(cls, value: str) -> str:
        return validate_password_strength(value)

class MessageResponse(BaseModel):
    message: str
