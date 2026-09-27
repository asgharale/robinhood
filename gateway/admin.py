from django.contrib import admin

from .models import ApiKey, Conversation, Document, Message


@admin.register(ApiKey)
class ApiKeyAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "masked", "is_active", "daily_limit", "per_minute_limit", "last_used_at")
    list_filter = ("is_active",)
    search_fields = ("user__email", "user__phone")
    readonly_fields = ("key", "created_at", "last_used_at")
    actions = ["rotate_keys"]

    @admin.display(description="key")
    def masked(self, obj):
        return obj.key[:7] + "…"

    @admin.action(description="Rotate selected keys (shows the new token)")
    def rotate_keys(self, request, queryset):
        for k in queryset:
            k.rotate()
            self.message_user(request, f"{k.user}: {k.key}")


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


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "filename", "api_key", "status", "chunk_count", "size_bytes", "created_at")
    list_filter = ("status",)
    search_fields = ("filename",)
    readonly_fields = ("filename", "size_bytes", "chunk_count", "status", "error",
                       "embedding_model", "created_at")