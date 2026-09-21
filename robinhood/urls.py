from django.contrib import admin
from django.urls import path
from gateway.api import api

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", api.urls),
]