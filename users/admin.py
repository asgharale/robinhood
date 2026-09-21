from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import UserChangeForm as DjangoUserChangeForm
from django.contrib.auth.forms import UserCreationForm as DjangoUserCreationForm

from .models import User


class UserCreationForm(DjangoUserCreationForm):
    class Meta:
        model = User
        fields = ("email", "phone", "first_name", "last_name", "age")


class UserChangeForm(DjangoUserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("-date_joined",)
    list_display = ("email", "phone", "first_name", "last_name", "country", "is_active", "date_joined")
    list_filter = ("is_active", "is_staff", "email_verified", "phone_verified", "country")
    search_fields = ("email", "phone", "first_name", "last_name")
    readonly_fields = ("country", "last_login", "date_joined", "updated_at")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "age", "organization", "phone", "country")}),
        ("Verification", {"fields": ("email_verified", "phone_verified")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Admin notes", {"fields": ("notes",)}),
        ("Dates", {"fields": ("last_login", "date_joined", "updated_at")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "phone", "first_name", "last_name", "age", "password1", "password2"),
        }),
    )