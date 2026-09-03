from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Profile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_profile_for_new_user(sender, instance, created, **kwargs):
    # Ensures A Profile is created for every new user, including users created off endpoint like `python manage.py createsuperuser`. 
    # I would remove this for performance reasons if the app were to scale, but for this small project it's fine.
    # I am just flexing my knowledge of Django signals.
    if created:
        role = Profile.ROLE_ADMIN if instance.is_superuser else Profile.ROLE_MANAGER if instance.is_staff else Profile.ROLE_MEMBER
        Profile.objects.get_or_create(user=instance, defaults={'role': role})
