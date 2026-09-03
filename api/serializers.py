from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from rest_framework import serializers

from .models import Profile, Task


class TaskSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = Task
        fields = ['id', 'title', 'description', 'status', 'owner', 'created_at', 'updated_at']
        read_only_fields = ['id', 'owner', 'created_at', 'updated_at']


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8, validators=[validate_password])
    role = serializers.ChoiceField(
        choices=Profile.ROLE_CHOICES, required=False, default=Profile.ROLE_MEMBER
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'role']

    def create(self, validated_data):
        role = validated_data.pop('role', Profile.ROLE_MEMBER)
        password = validated_data.pop('password')
        validated_data['is_superuser'] = role == Profile.ROLE_ADMIN
        validated_data['is_staff'] = role in {Profile.ROLE_ADMIN, Profile.ROLE_MANAGER}
        user = User(**validated_data)
        user.set_password(password)

        with transaction.atomic():
            user.save()
            Profile.objects.update_or_create(user=user, defaults={'role': role})
        return user


class ProfileSerializer(serializers.ModelSerializer):
    username = serializers.ReadOnlyField(source='user.username')
    email = serializers.ReadOnlyField(source='user.email')

    class Meta:
        model = Profile
        fields = ['username', 'email', 'role']
