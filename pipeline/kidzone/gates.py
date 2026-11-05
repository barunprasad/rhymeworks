"""Choice gates: a tiny local page to listen/look at candidates and pick one. Autopilot picks the top score.

Serves the episode folder on 127.0.0.1 and blocks until a choice is POSTed (written to gates/<name>.choice.json).
"""

import html
import json
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .core import Episode, log, read_json, write_json

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>Kidzone — {title}</title>
<style>
 body{{font-family:-apple-system,system-ui,sans-serif;background:#111418;color:#e9edf2;margin:0;padding:32px}}
 h1{{font-size:20px;margin:0 0 4px}} p{{color:#9aa5b1;margin:0 0 24px}}
 .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:16px}}
 .card{{background:#1b2027;border:1px solid #2a313a;border-radius:14px;padding:16px}}
 .card.best{{border-color:#3b82f6}} .tag{{font-size:12px;color:#60a5fa}} audio,img{{width:100%;margin:10px 0}} img{{border-radius:10px;background:#fff}}
 button{{width:100%;padding:10px;border-radius:10px;border:0;background:#2563eb;color:#fff;font-weight:600;cursor:pointer}}
 button:hover{{background:#1d4ed8}} .done{{color:#34d399;font-size:18px}}
</style></head><body><h1>{title}</h1><p>{subtitle}</p><div class="grid">{cards}</div>
<script>
async function pick(id){{await fetch('/choose',{{method:'POST',body:JSON.stringify({{gate:'{gate}',choice:id}})}});
document.body.innerHTML='<p class="done">✓ Chosen — the pipeline is continuing. You can close this tab.</p>';}}
</script></body></html>"""


class _Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, episode: Episode, **kw):
        self.episode = episode
        super().__init__(*a, directory=str(episode.dir), **kw)

    def log_message(self, *_):  # quiet
        pass

    def handle(self):
        # Browsers abort audio downloads when you skip between takes — not an error.
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):  # noqa: N802
        if self.path != "/choose":
            self.send_error(404)
            return
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        write_json(self.episode.path("gates", f"{body['gate']}.choice.json"), {"choice": body["choice"]})
        self.send_response(200)
        self.end_headers()


def choose(ep: Episode, gate: str, title: str, subtitle: str, candidates: list[dict], autopilot: bool) -> str:
    """candidates: [{id, label, audio?|image?, score_text?, best?}] with media paths relative to the episode dir."""
    done = ep.path("gates", f"{gate}.choice.json")
    if done.exists():
        return read_json(done)["choice"]
    best = next((c for c in candidates if c.get("best")), candidates[0])
    if autopilot:
        write_json(done, {"choice": best["id"], "autopilot": True})
        log("gate", f"{gate}: autopilot → {best['id']}")
        return best["id"]

    cards = []
    for c in candidates:
        media = ""
        if c.get("audio"):
            media = f'<audio controls preload="none" src="/{html.escape(c["audio"])}"></audio>'
        if c.get("image"):
            media += f'<img src="/{html.escape(c["image"])}">'
        cards.append(
            f'<div class="card{" best" if c.get("best") else ""}"><b>{html.escape(c["label"])}</b>'
            f'{"<div class=tag>★ best score</div>" if c.get("best") else ""}'
            f'<div class="tag">{html.escape(c.get("score_text", ""))}</div>{media}'
            f'<button onclick="pick(\'{c["id"]}\')">Choose</button></div>'
        )
    page = ep.path("gates", f"{gate}.html")
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(PAGE.format(title=html.escape(title), subtitle=html.escape(subtitle), cards="".join(cards), gate=gate))

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Handler, episode=ep))
    url = f"http://127.0.0.1:{server.server_address[1]}/gates/{gate}.html"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log("gate", f"{title} → {url}  (waiting for your choice)")
    webbrowser.open(url)
    try:
        while not done.exists():
            threading.Event().wait(1.0)
    finally:
        server.shutdown()
    choice = read_json(done)["choice"]
    log("gate", f"{gate}: you chose {choice}")
    return choice
