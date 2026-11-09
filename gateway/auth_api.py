from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import authenticate
from django.http import HttpResponse
from ninja import Field, Router, Schema
from ninja.errors import HttpError

from .auth import ACCESS, REFRESH, key_from_token, make_token
from .counters import incr
from .models import ApiKey

router = Router(auth=None, tags=["auth"])       # public: no token needed


class LoginIn(Schema):
    email: str = Field(..., max_length=255)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(Schema):
    id: int
    email: str
    first_name: str
    last_name: str
    phone: str
    organization: str
    age: int | None = None
    country: str
    email_verified: bool
    phone_verified: bool


class SessionOut(Schema):
    access: str
    expires_in: int
    user: UserOut


class OkOut(Schema):
    detail: str


def _session(user) -> dict:
    return {"access": make_token(user, ACCESS), "expires_in": settings.JWT_ACCESS_SECONDS, "user": user}


def _set_refresh_cookie(response: HttpResponse, user) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE, make_token(user, REFRESH),
        max_age=settings.JWT_REFRESH_SECONDS, path=settings.REFRESH_COOKIE_PATH,
        httponly=True, secure=not settings.DEBUG, samesite="Lax",
    )


async def _throttle(request, email: str) -> None:
    ip = request.META.get("REMOTE_ADDR", "")
    if await incr(f"login:ip:{ip}", 600) > 30 or await incr(f"login:email:{email}", 600) > 10:
        raise HttpError(429, "Too many attempts, try again in a few minutes")


@router.post("/login/", response=SessionOut)
async def login(request, response: HttpResponse, payload: LoginIn):
    email = payload.email.strip().lower()
    await _throttle(request, email)
    user = await sync_to_async(authenticate)(request, email=email, password=payload.password)
    if user is None or not await ApiKey.objects.filter(user=user, is_active=True).aexists():
        raise HttpError(401, "Invalid email or password")
    _set_refresh_cookie(response, user)
    return _session(user)


@router.post("/refresh/", response=SessionOut)
async def refresh(request, response: HttpResponse):
    token = request.COOKIES.get(settings.REFRESH_COOKIE)
    key = await key_from_token(token, REFRESH) if token else None
    if key is None:
        raise HttpError(401, "Session expired, please sign in again")
    _set_refresh_cookie(response, key.user)      # sliding session: each refresh extends it
    return _session(key.user)


@router.post("/logout/", response=OkOut)
async def logout(request, response: HttpResponse):
    response.delete_cookie(settings.REFRESH_COOKIE, path=settings.REFRESH_COOKIE_PATH, samesite="Lax")
    return {"detail": "ok"}