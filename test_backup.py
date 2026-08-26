import json
import unittest
from urllib.parse import urlencode

from unittest import mock

import backup


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, dashboards_pages, dashboard_payload):
        self.routes = {}
        self.calls = []
        self.dashboards_pages = dashboards_pages
        self.dashboard_payload = dashboard_payload
        self.gist_calls = []

    def _match(self, url, method):
        for (prefix, m), handler in self.routes.items():
            if url.startswith(prefix) and m == method:
                return handler(url)
        raise AssertionError(f"no route for {method} {url}")

    def get(self, url, **kwargs):
        params = kwargs.get("params")
        if params:
            url = f"{url}?{urlencode(params)}"
        self.calls.append(("get", url))
        if "/api/dashboards/search" in url:
            page = kwargs["params"]["page"]
            return FakeResponse(self.dashboards_pages.get(page, {"dashboards": []}))
        if "/api/dashboards/uid/" in url:
            return FakeResponse(self.dashboard_payload)
        raise AssertionError(f"unexpected get {url}")

    def post(self, url, **kwargs):
        self.gist_calls.append(("post", url, kwargs["json"]))
        return FakeResponse({"id": "new-gist-id", "html_url": "https://github.com/gist/new"})

    def patch(self, url, **kwargs):
        self.gist_calls.append(("patch", url, kwargs["json"]))
        return FakeResponse({"id": "existing-gist-id", "html_url": "https://github.com/gist/existing"})


class FetchDashboardsTest(unittest.TestCase):
    def test_pagination(self):
        session = FakeSession(
            dashboards_pages={
                1: {"dashboards": [{"uid": "a"}, {"uid": "b"}], "nextPage": 2},
                2: {"dashboards": [{"uid": "c"}], "nextPage": 0},
            },
            dashboard_payload={},
        )
        result = backup.fetch_dashboards(session)
        self.assertEqual([d["uid"] for d in result], ["a", "b", "c"])
        self.assertIn("page=2", session.calls[1][1])


class BuildFilesTest(unittest.TestCase):
    def test_slug_and_content(self):
        session = FakeSession(
            dashboards_pages={},
            dashboard_payload={"dashboard": {"uid": "a", "title": "My Dash 1"}},
        )
        files = backup.build_files(session, [{"uid": "a", "title": "My Dash 1"}])
        self.assertIn("My-Dash-1.json", files)
        self.assertEqual(files["My-Dash-1.json"]["content"], json.dumps({"uid": "a", "title": "My Dash 1"}, indent=2))


class UploadGistTest(unittest.TestCase):
    def test_create_when_no_id(self):
        backup.GITHUB_GIST_ID = ""
        session = FakeSession(dashboards_pages={}, dashboard_payload={})
        gist = backup.upload_gist(session, {"a.json": {"content": "{}"}})
        self.assertEqual(gist["id"], "new-gist-id")
        self.assertEqual(session.gist_calls[0][0], "post")

    def test_update_when_id_set(self):
        backup.GITHUB_GIST_ID = "existing-gist-id"
        session = FakeSession(dashboards_pages={}, dashboard_payload={})
        gist = backup.upload_gist(session, {"a.json": {"content": "{}"}})
        self.assertEqual(gist["id"], "existing-gist-id")
        self.assertEqual(session.gist_calls[0][0], "patch")
        self.assertIn("existing-gist-id", session.gist_calls[0][1])


if __name__ == "__main__":
    unittest.main()
