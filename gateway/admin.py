from django.contrib import admin
from .models import ApiKey, Conversation, Message


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("user", "masked", "is_active", "daily_limit", "per_minute_limit", "last_used_at")
    readonly_fields = ("key", "created_at", "last_used_at")
    actions = ["rotate_keys"]

    @admin.display(description="key")
    def masked(self, obj):
        return obj.key[:7] + "…"

    @admin.action(description="Rotate selected keys")
    def rotate_keys(self, request, queryset):
        for k in queryset:
            k.rotate()


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ("role", "content", "provider", "created_at")
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "api_key", "title", "status", "created_at")
    list_filter = ("status",)
    inlines = [MessageInline]