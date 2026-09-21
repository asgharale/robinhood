import secrets
import uuid
from django.conf import settings
from django.db import models
from pgvector.django import HnswIndex, VectorField


def generate_key() -> str:
    return "rh_" + secrets.token_urlsafe(32)


class ApiKey(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="api_key")
    key = models.CharField(max_length=64, unique=True, editable=False, default=generate_key)
    is_active = models.BooleanField(default=True)
    daily_limit = models.PositiveIntegerField(default=100)       # LLM requests / day
    per_minute_limit = models.PositiveIntegerField(default=10)   # LLM requests / minute
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    def rotate(self):
        self.key = generate_key()
        self.save(update_fields=["key"])

    def __str__(self):
        return f"{self.user_id}:{self.key[:7]}…"


class Conversation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        ENDED = "ended"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="conversations")
    title = models.CharField(max_length=100, blank=True)
    system_prompt = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["api_key", "-created_at"])]


class Message(models.Model):
    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    provider = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["conversation", "id"])]


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        READY = "ready"
        FAILED = "failed"

    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField(upload_to="documents/%Y/%m/")
    filename = models.CharField(max_length=255)
    size_bytes = models.PositiveBigIntegerField()
    chunk_count = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    error = models.CharField(max_length=500, blank=True)
    embedding_model = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    api_key = models.ForeignKey(ApiKey, on_delete=models.CASCADE, related_name="+")  # denormalized: filter without a join
    position = models.PositiveIntegerField()
    page = models.PositiveIntegerField(null=True, blank=True)
    text = models.TextField()
    embedding = VectorField(dimensions=384)   # must match EMBEDDING_MODEL's output size

    class Meta:
        indexes = [
            HnswIndex(name="chunk_embedding_hnsw", fields=["embedding"], m=16, ef_construction=64,
                      opclasses=["vector_cosine_ops"]),
        ]