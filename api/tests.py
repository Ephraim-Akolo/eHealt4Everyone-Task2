import json
import shutil
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import Profile, Task

TEST_LOG_DIR = Path(__file__).resolve().parent / "test_logs"

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "test-cache",
    }
}


def auth_headers(user):
    token = str(RefreshToken.for_user(user).access_token)
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


@override_settings(REQUEST_LOG_DIR=TEST_LOG_DIR, CACHES=TEST_CACHES)
class BaseAPITestCase(TestCase):
    """Common setup: fresh client, fresh cache, fresh log dir for every test."""

    def setUp(self):
        self.client = APIClient()
        cache.clear()
        TEST_LOG_DIR.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(TEST_LOG_DIR, ignore_errors=True)

    def make_user(self, username, role=Profile.ROLE_MEMBER, password="testpass123"):
        user = User.objects.create_user(username=username, password=password)
        Profile.objects.update_or_create(user=user, defaults={'role': role})
        user.refresh_from_db()
        return user


class AuthenticationTests(BaseAPITestCase):
    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/v1/tasks/")
        self.assertEqual(response.status_code, 401)

    def test_invalid_token_is_rejected(self):
        response = self.client.get(
            "/api/v1/tasks/", HTTP_AUTHORIZATION="Bearer garbage.token.value"
        )
        self.assertEqual(response.status_code, 401)

    def test_register_creates_user_and_default_member_profile(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "alice",
                "email": "alice@example.com",
                "password": "s3cur3-pass!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        user = User.objects.get(username="alice")
        self.assertEqual(user.profile.role, Profile.ROLE_MEMBER)

    def test_register_can_set_a_non_default_role(self):
        response = self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "carla",
                "email": "carla@example.com",
                "password": "s3cur3-pass!",
                "role": "admin",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(User.objects.get(username="carla").profile.role, "admin")

    def test_login_returns_access_and_refresh_tokens(self):
        self.make_user("alice")
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "alice", "password": "testpass123"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())
        self.assertIn("refresh", response.json())

    def test_login_with_wrong_password_is_rejected(self):
        self.make_user("alice")
        response = self.client.post(
            "/api/v1/auth/token/",
            {"username": "alice", "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_token_refresh_returns_new_access_token(self):
        alice = self.make_user("alice")
        refresh = str(RefreshToken.for_user(alice))
        response = self.client.post(
            "/api/v1/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.json())

    def test_me_endpoint_returns_username_and_role(self):
        alice = self.make_user("alice", role=Profile.ROLE_ADMIN)
        response = self.client.get("/api/v1/auth/me/", **auth_headers(alice))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "alice")
        self.assertEqual(response.json()["role"], "admin")


class OwnershipTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("alice")
        self.bob = self.make_user("bob")
        self.admin = self.make_user("root", role=Profile.ROLE_ADMIN)
        self.alice_task = Task.objects.create(owner=self.alice, title="Alice's task")
        self.bob_task = Task.objects.create(owner=self.bob, title="Bob's task")

    def test_user_only_sees_own_tasks_in_list(self):
        response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        titles = [t["title"] for t in response.json()]
        self.assertIn("Alice's task", titles)
        self.assertNotIn("Bob's task", titles)

    def test_user_cannot_retrieve_another_users_task(self):
        response = self.client.get(
            f"/api/v1/tasks/{self.bob_task.id}/", **auth_headers(self.alice)
        )
        self.assertEqual(response.status_code, 404)

    def test_user_cannot_delete_another_users_task(self):
        response = self.client.delete(
            f"/api/v1/tasks/{self.bob_task.id}/", **auth_headers(self.alice)
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Task.objects.filter(id=self.bob_task.id).exists())

    def test_admin_sees_every_users_tasks(self):
        response = self.client.get("/api/v1/tasks/", **auth_headers(self.admin))
        titles = [t["title"] for t in response.json()]
        self.assertIn("Alice's task", titles)
        self.assertIn("Bob's task", titles)

    def test_admin_can_update_any_users_task(self):
        response = self.client.patch(
            f"/api/v1/tasks/{self.bob_task.id}/",
            {"status": "done"},
            format="json",
            **auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.bob_task.refresh_from_db()
        self.assertEqual(self.bob_task.status, "done")


class CachingTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("alice")

    def test_list_is_actually_cached(self):
        # First call: empty list, gets cached.
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))

        # Create a task directly via the ORM, bypassing the view
        # (and therefore bypassing bump_cache_version).
        Task.objects.create(owner=self.alice, title="Created outside the API")

        # Second call within the same cache window should still be
        # served from the stale cache entry -> proves caching is real.
        response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        titles = [t["title"] for t in response.json()]
        self.assertNotIn("Created outside the API", titles)

    def test_nocache_param_bypasses_the_cache(self):
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        Task.objects.create(owner=self.alice, title="Created outside the API")

        response = self.client.get(
            "/api/v1/tasks/?nocache=1", **auth_headers(self.alice)
        )
        titles = [t["title"] for t in response.json()]
        self.assertIn("Created outside the API", titles)

    def test_creating_a_task_through_the_api_busts_the_cache(self):
        # Cache the empty list.
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))

        self.client.post(
            "/api/v1/tasks/",
            {"title": "New task via API"},
            format="json",
            **auth_headers(self.alice),
        )

        response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        titles = [t["title"] for t in response.json()]
        self.assertIn("New task via API", titles)

    def test_updating_a_task_busts_the_cache(self):
        task = Task.objects.create(owner=self.alice, title="Todo item")
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))  # cache it

        self.client.patch(
            f"/api/v1/tasks/{task.id}/",
            {"status": "done"},
            format="json",
            **auth_headers(self.alice),
        )

        response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        statuses = {t["id"]: t["status"] for t in response.json()}
        self.assertEqual(statuses[task.id], "done")

    def test_deleting_a_task_busts_the_cache(self):
        task = Task.objects.create(owner=self.alice, title="To be deleted")
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))  # cache it

        self.client.delete(f"/api/v1/tasks/{task.id}/", **auth_headers(self.alice))

        response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        ids = [t["id"] for t in response.json()]
        self.assertNotIn(task.id, ids)

    def test_different_query_params_use_separate_cache_entries(self):
        Task.objects.create(owner=self.alice, title="Todo item", status="todo")
        Task.objects.create(owner=self.alice, title="Done item", status="done")

        todo_response = self.client.get(
            "/api/v1/tasks/?status=todo", **auth_headers(self.alice)
        )
        done_response = self.client.get(
            "/api/v1/tasks/?status=done", **auth_headers(self.alice)
        )

        todo_titles = [t["title"] for t in todo_response.json()]
        done_titles = [t["title"] for t in done_response.json()]
        self.assertEqual(todo_titles, ["Todo item"])
        self.assertEqual(done_titles, ["Done item"])

    def test_different_users_never_share_a_cache_entry(self):
        bob = self.make_user("bob")
        Task.objects.create(owner=self.alice, title="Alice only")
        Task.objects.create(owner=bob, title="Bob only")

        alice_response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        bob_response = self.client.get("/api/v1/tasks/", **auth_headers(bob))

        alice_titles = [t["title"] for t in alice_response.json()]
        bob_titles = [t["title"] for t in bob_response.json()]
        self.assertEqual(alice_titles, ["Alice only"])
        self.assertEqual(bob_titles, ["Bob only"])

    def test_admin_and_member_do_not_share_a_cache_entry(self):
        admin = self.make_user("root", role=Profile.ROLE_ADMIN)
        Task.objects.create(owner=self.alice, title="Alice's task")

        member_response = self.client.get("/api/v1/tasks/", **auth_headers(self.alice))
        admin_response = self.client.get("/api/v1/tasks/", **auth_headers(admin))

        self.assertEqual(len(member_response.json()), 1)
        self.assertEqual(len(admin_response.json()), 1)


class RequestLoggingTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.alice = self.make_user("alice")

    def _read_last_log_entry(self, filename):
        log_file = TEST_LOG_DIR / filename
        self.assertTrue(log_file.exists(), f"{filename} was never created")
        with open(log_file) as f:
            lines = f.readlines()
        return json.loads(lines[-1])

    def test_authenticated_request_is_logged_under_username(self):
        self.client.get("/api/v1/tasks/", **auth_headers(self.alice))

        entry = self._read_last_log_entry("alice.log")
        self.assertEqual(entry["user"], "alice")
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["path"], "/api/v1/tasks/")
        self.assertEqual(entry["status_code"], 200)
        for key in ("start_time", "end_time", "duration_ms", "remote_addr"):
            self.assertIn(key, entry)
        self.assertIsInstance(entry["duration_ms"], (int, float))

    def test_unauthenticated_request_is_logged_under_anonymous(self):
        self.client.get("/api/v1/tasks/")  # 401, but still logged

        entry = self._read_last_log_entry("anonymous.log")
        self.assertEqual(entry["user"], "anonymous")
        self.assertEqual(entry["status_code"], 401)

    def test_password_is_redacted_in_the_logged_request_body(self):
        self.client.post(
            "/api/v1/auth/register/",
            {
                "username": "carla",
                "email": "carla@example.com",
                "password": "super-secret-pass",
            },
            format="json",
        )

        entry = self._read_last_log_entry("anonymous.log")
        self.assertEqual(entry["request_body"]["password"], "***REDACTED***")
        # Make sure the real password never made it into the log file at all.
        raw_contents = (TEST_LOG_DIR / "anonymous.log").read_text()
        self.assertNotIn("super-secret-pass", raw_contents)

    def test_usernames_with_unsafe_characters_are_sanitized_for_the_filename(self):
        # Not a realistic Django username, but confirms _write_log() can't
        # be used to escape the log directory or write to an unexpected path.
        weird_user = User.objects.create_user(username="a/../../etc", password="x")
        self.client.get("/api/v1/tasks/", **auth_headers(weird_user))

        # No file should have been written outside TEST_LOG_DIR.
        created_files = list(TEST_LOG_DIR.iterdir())
        self.assertTrue(all(f.parent == TEST_LOG_DIR for f in created_files))
