"""Exercise read-only HTTP boundaries and incomplete experiment records."""

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from server import Handler, ThreadingHTTPServer


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.workspace.name).resolve()
        self.experiment = self.root / "experiment"
        self.sample = self.experiment / "q1"
        self.sample.mkdir(parents=True)
        (self.sample / "metrics_sample.json").write_text('{"accuracies": [1]}')
        (self.sample / "traj.jsonl").write_text('{"initial_prompt": "hello"}\n')
        (self.experiment / ".env").write_text("PRIVATE=hidden")
        (self.root / "experiences.json").write_text('{"secret": true}')
        (self.experiment / "experiences.json").symlink_to(
            self.root / "experiences.json"
        )
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.roots = [self.experiment]
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/api/"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.workspace.cleanup()

    def get(self, route, **params):
        with urlopen(
            self.base + route + "?" + urlencode({"experiment": 0, **params})
        ) as response:
            return response.read()

    def test_records_and_incomplete_summary(self):
        data = json.loads(self.get("overview"))
        self.assertEqual(data["samples"][0]["summary"]["accuracies"], [1])
        self.assertIsNone(data["summary"])
        (self.sample / "metrics_sample.json").write_text("{")
        data = json.loads(self.get("overview"))
        self.assertIsNone(data["samples"][0]["summary"])
        self.assertTrue(data["samples"][0]["error"])

    def test_file_boundaries(self):
        for path in (".env", "../experiences.json", "experiences.json"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    self.get("file", path=path)
                self.assertEqual(error.exception.code, 403)
        self.assertIn(b"hello", self.get("file", path="q1/traj.jsonl"))

    def test_inventory_and_difference(self):
        records = json.loads(self.get("sample", sample="q1"))
        self.assertEqual(
            {r["name"] for r in records}, {"traj.jsonl", "metrics_sample.json"}
        )
        (self.sample / "tt_skill_adapted.md").write_text("new\n")
        (self.sample / "tt_skill_original.md").write_text("old\n")
        result = json.loads(
            self.get(
                "diff", left="q1/tt_skill_original.md", right="q1/tt_skill_adapted.md"
            )
        )
        self.assertIn("-old", result["diff"])
        self.assertIn("+new", result["diff"])

    def test_invalid_selection(self):
        for route, params in (
            ("overview", {"experiment": -1}),
            ("sample", {"sample": ".."}),
        ):
            with self.subTest(route=route), self.assertRaises(HTTPError):
                self.get(route, **params)


if __name__ == "__main__":
    unittest.main()
