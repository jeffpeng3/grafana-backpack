import json
import unittest

import backup


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data

    def raise_for_status(self):
        return None


class GistSession:
    def __init__(self):
        self.gist_calls = []

    def post(self, url, **kwargs):
        self.gist_calls.append(("post", url, kwargs["json"]))
        return FakeResponse({"id": "new-gist-id", "html_url": "https://github.com/gist/new"})

    def patch(self, url, **kwargs):
        self.gist_calls.append(("patch", url, kwargs["json"]))
        return FakeResponse({"id": "existing-gist-id", "html_url": "https://github.com/gist/existing"})


class DashboardsSession:
    def __init__(self, pages, uid_payload=None):
        self.pages = pages
        self.uid_payload = uid_payload

    def get(self, url, params=None, **kwargs):
        if "/api/search" in url:
            offset = (params or {}).get("offset", 0)
            return FakeResponse(self.pages.get(offset, []))
        if "/api/dashboards/uid/" in url:
            return FakeResponse(self.uid_payload)
        raise AssertionError(f"unexpected url {url}")


class FetchDashboardsTest(unittest.TestCase):
    def test_pagination_and_filter(self):
        limit = 1000
        page0 = []
        for i in range(limit):
            if i == 1:
                page0.append({"uid": "folder1", "type": "folder"})
            elif i == 3:
                page0.append({"uid": "b", "type": "dash-db"})
            else:
                page0.append({"uid": f"n{i}", "type": "dash-db"})
        pages = {0: page0, limit: [{"uid": "c", "type": "dash-db"}]}
        session = DashboardsSession(pages)
        result = backup.fetch_dashboards(session)
        uids = [d["uid"] for d in result]
        self.assertNotIn("folder1", uids)
        self.assertEqual(uids[0], "n0")
        self.assertIn("b", uids)
        self.assertIn("c", uids)

    def test_stops_when_page_short(self):
        pages = {
            0: [{"uid": "a", "type": "dash-db"}],
            1000: [{"uid": "should-not-happen", "type": "dash-db"}],
        }
        session = DashboardsSession(pages)
        result = backup.fetch_dashboards(session)
        self.assertEqual([d["uid"] for d in result], ["a"])


class BuildFilesTest(unittest.TestCase):
    def test_slug_and_content(self):
        session = DashboardsSession({}, {"dashboard": {"uid": "a", "title": "My Dash 1"}})
        files = backup.build_files(session, [{"uid": "a", "title": "My Dash 1"}])
        self.assertIn("My-Dash-1.json", files)
        self.assertEqual(files["My-Dash-1.json"]["content"], json.dumps({"uid": "a", "title": "My Dash 1"}, indent=2))


class UploadGistTest(unittest.TestCase):
    def test_create_when_no_id(self):
        backup.GITHUB_GIST_ID = ""
        session = GistSession()
        gist = backup.upload_gist(session, {"a.json": {"content": "{}"}})
        self.assertEqual(gist["id"], "new-gist-id")
        self.assertEqual(session.gist_calls[0][0], "post")

    def test_update_when_id_set(self):
        backup.GITHUB_GIST_ID = "existing-gist-id"
        session = GistSession()
        gist = backup.upload_gist(session, {"a.json": {"content": "{}"}})
        self.assertEqual(gist["id"], "existing-gist-id")
        self.assertEqual(session.gist_calls[0][0], "patch")
        self.assertIn("existing-gist-id", session.gist_calls[0][1])


if __name__ == "__main__":
    unittest.main()
