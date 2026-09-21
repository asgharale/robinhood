import phonenumbers
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ─────────────────────────────────────────────────────────────────────────────
# Phone helpers
# ─────────────────────────────────────────────────────────────────────────────

def parse_phone(raw: str | None) -> tuple[str, str]:
    """
    Validate a phone number from any country.
    Returns (E.164 string, ISO country code), e.g. ("+989123456789", "IR").
    Numbers typed without a "+country" prefix are parsed using
    settings.DEFAULT_PHONE_REGION (e.g. "IR" so 0912... works).
    Raises ValueError if invalid.
    """
    if not raw or not raw.strip():
        raise ValueError(_("Phone number is required."))
    try:
        number = phonenumbers.parse(raw.strip(), getattr(settings, "DEFAULT_PHONE_REGION", None))
    except phonenumbers.NumberParseException:
        raise ValueError(_("Enter a valid phone number, e.g. +14155552671."))
    if not phonenumbers.is_valid_number(number):
        raise ValueError(_("Enter a valid phone number, e.g. +14155552671."))
    e164 = phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
    return e164, phonenumbers.region_code_for_number(number) or ""


def validate_phone(value: str) -> None:
    """Field validator (used by forms and createsuperuser)."""
    try:
        parse_phone(value)
    except ValueError as e:
        raise ValidationError(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# UserManager
# ─────────────────────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email: str, phone: str, password: str | None, **extra_fields):
        if not email:
            raise ValueError(_("Email is required."))
        user = self.model(email=self.normalize_email(email).lower(), phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)  # save() normalizes + validates the phone
        return user

    def create_user(self, email: str, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, phone, password, **extra_fields)

    def create_superuser(self, email: str, phone: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError(_("Superuser must have is_staff=True and is_superuser=True."))
        return self._create_user(email, phone, password, **extra_fields)


# ─────────────────────────────────────────────────────────────────────────────
# User model
# ─────────────────────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):
    # ── Identity (required) ──────────────────────────────────────────────────
    email = models.EmailField(_("email"), max_length=255, unique=True)
    phone = models.CharField(
        _("phone"),
        max_length=16,                      # E.164: "+" + up to 15 digits
        unique=True,
        validators=[validate_phone],
        help_text=_("Any country. Use the +country format, e.g. +14155552671."),
    )
    first_name = models.CharField(_("first name"), max_length=150)
    last_name = models.CharField(_("last name"), max_length=150)

    # ── Optional profile ─────────────────────────────────────────────────────
    age = models.PositiveSmallIntegerField(
        _("age"), null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(120)],
    )
    organization = models.CharField(_("organization"), max_length=150, blank=True)
    country = models.CharField(
        _("country"), max_length=2, blank=True, editable=False,
        help_text=_("ISO country code, filled automatically from the phone number."),
    )

    # ── Verification ─────────────────────────────────────────────────────────
    email_verified = models.BooleanField(_("email verified"), default=False)
    phone_verified = models.BooleanField(_("phone verified"), default=False)

    # ── Status ───────────────────────────────────────────────────────────────
    # is_active doubles as the "approved by admin" flag: the API rejects inactive users.
    # Users created from the admin panel are active immediately. For future self-signup,
    # create them with is_active=False and flip it when you approve.
    is_active = models.BooleanField(_("active"), default=True)
    is_staff = models.BooleanField(_("staff status"), default=False)
    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    # ── Admin-only ───────────────────────────────────────────────────────────
    notes = models.TextField(_("admin notes"), blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["phone", "first_name", "last_name"]  # asked by createsuperuser

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-date_joined"]

    # ── Normalization ────────────────────────────────────────────────────────

    def _normalize(self):
        self.email = (self.email or "").strip().lower()
        self.phone, self.country = parse_phone(self.phone)

    def clean(self):
        super().clean()
        if self.phone:
            try:
                self._normalize()  # runs before the unique check, so duplicates are caught in forms
            except ValueError as e:
                raise ValidationError({"phone": str(e)})

    def save(self, *args, **kwargs):
        self._normalize()
        super().save(*args, **kwargs)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def get_full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self) -> str:
        return self.first_name or self.email.split("@")[0]

    def __str__(self) -> str:
        name = self.get_full_name()
        return f"{name} <{self.email}>" if name else self.email