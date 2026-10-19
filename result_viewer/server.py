"""Read-only browser for explicitly selected XSkill experiment directories."""

import argparse
import difflib
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

STATIC = Path(__file__).parent / "static"
ARTIFACTS = {
    "metrics_at_k.json",
    "metrics_summary.json",
    "metrics_sample.json",
    "metrics.json",
    "traj.jsonl",
    "injected_system_prompt.txt",
    "exp_summary_prompt.txt",
    "exp_summary_resp.txt",
    "exp_intra_prompt.txt",
    "exp_intra_resp.txt",
    "exp_items.json",
    "skill_raw.md",
    "tt_decomposition_info.txt",
    "tt_skill_adapted.md",
    "tt_skill_original.md",
    "experiences.json",
    "SKILL.md",
    "metadata.json",
    "exp_refine_prompt.txt",
    "exp_refine_resp.txt",
}


def artifact_path(root, relative):
    """Constrain all reads, including symlinks, to selected experiment artifacts."""
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Path is outside the selected experiment")
    image = path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    analysis = path.parent.name == ".analysis_cache" and path.name.endswith(
        "_analysis.txt"
    )
    if path.name not in ARTIFACTS and not image and not analysis:
        raise PermissionError("Not an experiment artifact")
    if not path.is_file():
        raise FileNotFoundError(relative)
    return path


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def inventory(root, folder):
    records = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        try:
            artifact_path(root, relative)
        except PermissionError:
            continue
        records.append(
            {"path": relative, "name": path.name, "size": path.stat().st_size}
        )
    return records


class Handler(BaseHTTPRequestHandler):
    def send_content(self, content, mime, status=200):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        # Serve only fixed assets and the read-only API.
        url = urlsplit(self.path)
        query = parse_qs(url.query)
        try:
            if url.path in {"/", "/app.js", "/style.css"}:
                path = STATIC / ("index.html" if url.path == "/" else url.path[1:])
                self.send_content(
                    path.read_bytes(), mimetypes.guess_type(path)[0] + "; charset=utf-8"
                )
                return
            if url.path == "/api/experiments":
                data = [
                    {"id": i, "name": p.name, "path": str(p)}
                    for i, p in enumerate(self.server.roots)
                ]
            else:
                index = int(query["experiment"][0])
                if not 0 <= index < len(self.server.roots):
                    raise ValueError("Unknown experiment")
                root = self.server.roots[index]
                if url.path == "/api/overview":
                    samples = []
                    for folder in sorted(root.iterdir()):
                        if not folder.is_dir() or folder.name in {
                            "snapshots",
                            "memory_bank",
                            "tmp",
                        }:
                            continue
                        if (
                            not (folder / "metrics_sample.json").exists()
                            and not list(folder.glob("rollout_*/traj.jsonl"))
                            and not (folder / "traj.jsonl").exists()
                        ):
                            continue
                        summary = None
                        error = None
                        try:
                            summary = read_json(
                                artifact_path(
                                    root, f"{folder.name}/metrics_sample.json"
                                )
                            )
                        except (FileNotFoundError, json.JSONDecodeError) as exc:
                            error = str(exc)
                        samples.append(
                            {"id": folder.name, "summary": summary, "error": error}
                        )
                    summary = None
                    if (root / "metrics_at_k.json").exists():
                        summary = read_json(artifact_path(root, "metrics_at_k.json"))
                    data = {"samples": samples, "summary": summary}
                elif url.path == "/api/sample":
                    folder = (root / query["sample"][0]).resolve()
                    if folder.parent != root or not folder.is_dir():
                        raise PermissionError("Invalid sample directory")
                    data = inventory(root, folder)
                elif url.path == "/api/knowledge":
                    data = []
                    for name in ("snapshots", "memory_bank"):
                        folder = root / name
                        if folder.is_dir() and folder.resolve().is_relative_to(root):
                            data.extend(inventory(root, folder))
                elif url.path == "/api/file":
                    path = artifact_path(root, query["path"][0])
                    mime = mimetypes.guess_type(path)[0] or "text/plain"
                    self.send_content(path.read_bytes(), mime)
                    return
                elif url.path == "/api/diff":
                    left = artifact_path(root, query["left"][0])
                    right = artifact_path(root, query["right"][0])
                    data = {
                        "diff": "".join(
                            difflib.unified_diff(
                                left.read_text().splitlines(True),
                                right.read_text().splitlines(True),
                                fromfile=query["left"][0],
                                tofile=query["right"][0],
                            )
                        )
                    }
                else:
                    self.send_content(b"Not found", "text/plain", 404)
                    return
            self.send_content(
                json.dumps(data, ensure_ascii=False).encode(),
                "application/json; charset=utf-8",
            )
        except (
            PermissionError,
            FileNotFoundError,
            ValueError,
            KeyError,
            OSError,
        ) as exc:
            status = 403 if isinstance(exc, PermissionError) else 400
            self.send_content(
                json.dumps({"error": str(exc)}).encode(), "application/json", status
            )


if __name__ == "__main__":
    # Reuse the project's Python without importing or running experiment modules.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, action="append", required=True)
    parser.add_argument("--port", type=int, default=28765)
    args = parser.parse_args()
    roots = [p.resolve(strict=True) for p in args.experiment]
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    server.roots = roots
    print(f"XSkill viewer: http://10.1.110.29:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
