"""人間 vs AI の対戦をブラウザで行うローカルサーバー。

    py scripts/play_human.py            # http://127.0.0.1:8765/ を開く
    py scripts/play_human.py --port 9000 --no-browser

対局記録は runs/human/games.jsonl に追記される。集計は scripts/summarize_human.py。
評価の手順は docs/HUMAN_EVAL.md。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from carcassonne.state import State
from carcassonne.webplay import (
    LEVELS,
    HumanGame,
    make_advisor,
    make_agent,
    make_coach,
    tile_library,
)

LOCK = threading.Lock()
AGENTS: dict[str, object] = {}
GAME: HumanGame | None = None


def get_agent(level: str):
    if level not in AGENTS:
        AGENTS[level] = make_agent(level)
    return AGENTS[level]


def warmup(level: str) -> None:
    """Numbaのコンパイルを起動時に済ませる（初手が数十秒止まるのを避ける）。"""
    import random

    agent = get_agent(level)
    agent.act(State.new_game(0), random.Random(0))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # 標準のアクセスログは出さない
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json")

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            html = (ROOT / "web" / "play.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
        elif self.path == "/play_features.js":
            js = (ROOT / "web" / "play_features.js").read_bytes()
            self._send(200, js, "text/javascript; charset=utf-8")
        elif self.path == "/api/tiles":
            self._json({"tiles": tile_library(), "levels": LEVELS})
        elif self.path == "/api/state":
            with LOCK:
                self._json(GAME.view() if GAME else None)
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:
        global GAME
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or b"{}")
        try:
            with LOCK:
                if self.path == "/api/new":
                    level = data.get("level", "strong")
                    if level not in LEVELS:
                        raise ValueError("未知の強さ")
                    GAME = HumanGame(
                        int(data["seed"]),
                        int(data["human_seat"]),
                        level,
                        get_agent(level),
                        str(data.get("name", ""))[:40],
                        coach=make_coach(get_agent("strong")) if data.get("coach") else None,
                        advisor=make_advisor(get_agent("strong")),
                    )
                    self._json(GAME.view())
                elif self.path == "/api/move":
                    if GAME is None:
                        raise ValueError("対局が始まっていません")
                    piece = data.get("piece")
                    GAME.human_move(
                        int(data["x"]),
                        int(data["y"]),
                        int(data["variant"]),
                        None if piece is None else int(piece),
                    )
                    self._json(GAME.view())
                elif self.path in ("/api/undo", "/api/hint"):
                    if GAME is None:
                        raise ValueError("対局が始まっていません")
                    if self.path == "/api/undo":
                        GAME.undo()
                    else:
                        GAME.request_hint()
                    self._json(GAME.view())
                else:
                    self._send(404, b"not found", "text/plain")
        except (ValueError, KeyError) as e:
            self._json({"error": str(e)}, 400)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--no-warmup", action="store_true")
    args = ap.parse_args()
    if not args.no_warmup:
        print("AIを準備中（初回はNumbaのコンパイルで数十秒かかります）...", flush=True)
        warmup("strong")
    url = f"http://127.0.0.1:{args.port}/"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"起動しました: {url}  （Ctrl+Cで終了）", flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
