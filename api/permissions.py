from rest_framework.permissions import BasePermission


class IsOwnerOrAdmin(BasePermission):
    """Object-level check: the task's owner, or a user with the 'admin'
    role, may retrieve/update/delete it. Everyone else gets 403."""

    def has_object_permission(self, request, view, obj):
        profile = getattr(request.user, 'profile', None)
        role = getattr(profile, 'role', 'member')
        return role == 'admin' or obj.owner_id == request.user.id
