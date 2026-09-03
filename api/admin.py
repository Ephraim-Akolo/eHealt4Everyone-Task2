from django.contrib import admin
from .models import Profile, Task


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role')
    list_filter = ('role',)
    search_fields = ('user__username',)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'owner', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('title', 'owner__username')
