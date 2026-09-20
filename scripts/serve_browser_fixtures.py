"""Serve browser fixtures with room for parallel Chromium asset requests."""

import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class FixtureServer(ThreadingHTTPServer):
    # The stdlib default of five can reset connections during parallel page loads.
    request_queue_size = 128


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "examples/database/output"
    handler = partial(SimpleHTTPRequestHandler, directory=str(output))
    with FixtureServer(("127.0.0.1", args.port), handler) as server:
        server.serve_forever()
