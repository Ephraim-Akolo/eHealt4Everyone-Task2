import json
import shutil
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

TEST_LOG_DIR = Path(__file__).resolve().parent.parent / "test_logs"


@override_settings(REQUEST_LOG_DIR=TEST_LOG_DIR)
class SampleDataViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="alice", password="testpass123")
        self.token = str(RefreshToken.for_user(self.user).access_token)
        cache.clear()
        TEST_LOG_DIR.mkdir(exist_ok=True)

    def tearDown(self):
        shutil.rmtree(TEST_LOG_DIR, ignore_errors=True)

    def auth_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.token}"}

    # --- Authentication ---

    def test_unauthenticated_request_is_rejected(self):
        response = self.client.get("/api/sample-data/")
        self.assertEqual(response.status_code, 401)

    def test_authenticated_request_succeeds(self):
        response = self.client.get("/api/sample-data/", **self.auth_headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["requested_by"], "alice")

    def test_invalid_token_is_rejected(self):
        response = self.client.get(
            "/api/sample-data/", HTTP_AUTHORIZATION="Bearer garbage.token.value"
        )
        self.assertEqual(response.status_code, 401)

    # --- Caching / cache-busting ---

    def test_second_identical_request_is_served_from_cache(self):
        first = self.client.get("/api/sample-data/", **self.auth_headers())
        second = self.client.get("/api/sample-data/", **self.auth_headers())

        self.assertFalse(first.json()["from_cache"])
        self.assertTrue(second.json()["from_cache"])

    def test_different_query_params_bust_cache(self):
        first = self.client.get("/api/sample-data/?category=a", **self.auth_headers())
        second = self.client.get("/api/sample-data/?category=b", **self.auth_headers())

        # Different params -> different cache key -> both computed fresh.
        self.assertFalse(first.json()["from_cache"])
        self.assertFalse(second.json()["from_cache"])

    def test_different_user_roles_get_separate_cache_entries(self):
        staff_user = User.objects.create_user(username="bob", password="testpass123", is_staff=True)
        staff_token = str(RefreshToken.for_user(staff_user).access_token)

        self.client.get("/api/sample-data/", **self.auth_headers())
        response = self.client.get(
            "/api/sample-data/", HTTP_AUTHORIZATION=f"Bearer {staff_token}"
        )

        # Same path/params, different role -> not served from the regular user's cache entry.
        self.assertFalse(response.json()["from_cache"])
        self.assertEqual(response.json()["role"], "staff")

    def test_refresh_param_forces_cache_bypass(self):
        self.client.get("/api/sample-data/", **self.auth_headers())
        response = self.client.get(
            "/api/sample-data/?refresh=true", **self.auth_headers()
        )
        self.assertFalse(response.json()["from_cache"])

    # --- Logging ---

    def test_request_is_logged_to_user_file(self):
        self.client.get("/api/sample-data/", **self.auth_headers())

        log_file = TEST_LOG_DIR / "alice.jsonl"
        self.assertTrue(log_file.exists())

        with open(log_file) as f:
            entry = json.loads(f.readline())

        self.assertEqual(entry["user"], "alice")
        self.assertEqual(entry["method"], "GET")
        self.assertEqual(entry["status_code"], 200)
        self.assertIn("start_time", entry)
        self.assertIn("end_time", entry)
        self.assertIn("duration_seconds", entry)

    def test_anonymous_request_logs_under_anonymous_file(self):
        self.client.get("/api/sample-data/")  # unauthenticated, gets 401

        log_file = TEST_LOG_DIR / "anonymous.jsonl"
        self.assertTrue(log_file.exists())

        