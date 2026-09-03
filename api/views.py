from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework import generics, permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from .cache_utils import build_cache_key, bump_cache_version
from .models import Profile, Task
from .permissions import IsOwnerOrAdmin
from .serializers import ProfileSerializer, RegisterSerializer, TaskSerializer

CACHE_NAMESPACE = 'tasks'


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ - open to anyone, creates a User + Profile.
    Everything else in the API requires a valid JWT (see settings.REST_FRAMEWORK)."""

    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class MeView(APIView):
    """GET /api/auth/me/ - the authenticated user's own profile/role."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile, _ = Profile.objects.get_or_create(user=request.user)
        return Response(ProfileSerializer(profile).data)


class TaskViewSet(viewsets.ModelViewSet):
    """
    Full CRUD for tasks. Only authenticated users may access it at all
    (enforced globally by DEFAULT_PERMISSION_CLASSES, reinforced here).

    - Regular users only ever see/modify their own tasks.
    - Users with the 'admin' role can see/modify everyone's tasks.
    - `list` responses are cached in Redis; the cache key and its
      invalidation are handled by api/cache_utils.py (dynamic
      cache-busting based on URL params, user role, and time; see that
      module's docstring for details). Pass `?nocache=1` to always bypass
      the cache for a given request.
    """

    serializer_class = TaskSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]

    def get_queryset(self):
        user = self.request.user
        profile, _ = Profile.objects.get_or_create(user=user)
        qs = Task.objects.all() if profile.role == Profile.ROLE_ADMIN else Task.objects.filter(owner=user)

        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)

        return qs

    def list(self, request, *args, **kwargs):
        skip_cache = request.query_params.get('nocache') == '1'
        cache_key = build_cache_key(request, namespace=CACHE_NAMESPACE)

        if not skip_cache:
            cached_data = cache.get(cache_key)
            if cached_data is not None:
                return Response(cached_data)

        response = super().list(request, *args, **kwargs)
        cache.set(cache_key, response.data, timeout=300)
        return response

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
        bump_cache_version(CACHE_NAMESPACE, self.request.user.id)

    def perform_update(self, serializer):
        task = serializer.save()
        bump_cache_version(CACHE_NAMESPACE, task.owner_id)

    def perform_destroy(self, instance):
        owner_id = instance.owner_id
        instance.delete()
        bump_cache_version(CACHE_NAMESPACE, owner_id)
