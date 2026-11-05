"""Verify local UI serving without exposing repository or journal files."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Set before importing the backend; this test never opens production data.
_temp = tempfile.TemporaryDirectory(prefix="reflect-ui-test-")
os.environ["INNERBLOOM_DATA_DIR"] = _temp.name
import app
from fastapi.testclient import TestClient

class WorkspaceServingTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app, base_url="http://127.0.0.1:5000")

    def test_workspace_and_local_assets(self):
        with patch.dict(os.environ, {"INNERBLOOM_DEMO": "0"}):
            response = self.client.get("/app")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["cache-control"])
        self.assertNotIn('name="innerbloom-demo"', response.text)
        self.assertNotIn("fonts.googleapis.com", response.text)
        for asset in ["base.css", "glass.css", "refinements.css", "app.js", "workspace.js", "fonts/Urbanist-Variable.ttf", "images/sculptural-room.webp"]:
            self.assertEqual(self.client.get("/assets/" + asset).status_code, 200, asset)

    def test_spotify_registered_callback_serves_workspace(self):
        response = self.client.get("/index.html?code=test-code&state=test-state")
        self.assertEqual(response.status_code, 200)
        self.assertIn("assets/app.js", response.text)
        self.assertNotIn("test-code", response.text)

    def test_private_paths_are_not_static(self):
        for path in ["/data/journal.json", "/app.py", "/.env", "/assets/%2e%2e/app.py"]:
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_demo_is_explicitly_identified(self):
        with patch.dict(os.environ, {"INNERBLOOM_DEMO": "1"}):
            self.assertIn('name="innerbloom-demo"', self.client.get("/app").text)

if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        _temp.cleanup()
