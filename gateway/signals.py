# signals.py
from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import ApiKey, Document
from django.db.models.signals import post_delete


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_api_key(sender, instance, created, **kwargs):
    if created:
        ApiKey.objects.get_or_create(user=instance)


@receiver(post_delete, sender=Document)
def delete_document_file(sender, instance, **kwargs):
    if instance.file:
        instance.file.delete(save=False)