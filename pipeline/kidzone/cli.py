"""kidzone CLI.

  kidzone run <brief.json> [--autopilot] [--redo STAGE ...]   brief → packaged videos
  kidzone schema                                              print the EpisodeBrief JSON Schema
  kidzone shows                                               list shows in the library
  kidzone pixar <episode.toml> [--phase P] [--only ..] [--redo ..] [--dry-run] [--plan]
                                                              Pixar-style episode (see kidzone/pixar.py)
  kidzone draft <episode.toml> [--all]                        writer LLM fills empty shot prompts from the lyrics
  kidzone upload <episode.toml> [--text] [--thumbs] [--force] YouTube upload text + thumbnails (upload/)
  kidzone asset <draft id>                                    4 FLUX options for a new library character/prop/scene
  kidzone song <episode.toml> [--n 4] | --master <take> | --import <audio>
                                                              ACE-Step takes / master the picked take / reuse a mastered song
  kidzone voice <voice id> [...]                              30 s samples of voice styles (assets/voices.toml)
  kidzone check <episode.toml> --stage keys|clips [--force]   auto-check pictures (extra/doubled characters, drawing mistakes)
  kidzone studio [--port 8765]                                the Rhymeworks studio (API + GPU queue)
Stages (in order): write, song, align, props, direct, render, package. Each writes its own output in
episodes/<slug>/, so a re-run resumes where it stopped; --redo clears a stage and everything after it.
"""

import argparse
import json
import shutil
import sys
import time

from . import director
from .core import LIB, Episode, log, read_json
from .models import EpisodeBrief
from .stages import align, finish, master, props, song, write

STAGES = ["write", "song", "align", "master", "props", "direct", "render", "package"]
OUTPUTS = {
    "write": ["storyboard.json"],
    "song": ["songs", "gates"],
    "align": ["align"],
    "master": ["songs/master"],
    "props": [],
    "direct": ["episode_en.json", "episode_hi.json"],
    "render": ["renders"],
    "package": ["package"],
}


def clear_from(ep: Episode, stage: str) -> None:
    for s in STAGES[STAGES.index(stage):]:
        for name in OUTPUTS[s]:
            p = ep.path(name)
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()


def cmd_run(args: argparse.Namespace) -> None:
    brief = EpisodeBrief.model_validate_json(open(args.brief).read())
    if args.autopilot:
        brief.autopilot = True
    show = read_json(LIB / brief.show / "show.json")
    ep = Episode(write.default_slug(brief))
    (ep.path("brief.json")).write_text(brief.model_dump_json(indent=1))
    for stage in args.redo or []:
        clear_from(ep, stage)
    t0 = time.time()
    log("run", f"episode '{ep.slug}' ({show['title']}) → {ep.dir}")

    sb = write.run(ep, brief, show)
    chosen = song.run(ep, brief, show, sb)
    timings = align.run(ep, sb, chosen)
    audio = master.run(ep, brief, show, chosen, timings)
    prop_files = props.run(ep, show, sb)
    episodes = director.run(ep, show, sb, timings, prop_files, audio)
    log("direct", f"timelines: {', '.join(p.name for p in episodes.values())}")
    renders = finish.render(ep, episodes)
    pkg = finish.package(ep, brief, show, sb, episodes, renders)
    log("run", f"done in {(time.time() - t0) / 60:.1f} min → {pkg}")


def main() -> None:
    ap = argparse.ArgumentParser(prog="kidzone")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("brief")
    r.add_argument("--autopilot", action="store_true")
    r.add_argument("--redo", nargs="*", choices=STAGES)
    sub.add_parser("schema")
    sub.add_parser("shows")
    px = sub.add_parser("pixar", help="Pixar-style episode from episodes/<slug>/episode.toml")
    px.add_argument("spec")
    px.add_argument("--phase", default="keys", choices=["keys", "clips", "assemble", "package", "all"])
    px.add_argument("--only", nargs="*", help="limit keys/clips to these shot ids")
    px.add_argument("--redo", nargs="*", help="delete and regenerate these shots in the current phase")
    px.add_argument("--dry-run", action="store_true", help="print the commands instead of running them")
    px.add_argument("--plan", action="store_true", help="print the resolved shot plan (prompts, images, timing) as JSON")
    px.add_argument("--intro", action="store_true", help="package: also make the version with the project's intro clip")
    dr = sub.add_parser("draft", help="draft keyframe/motion prompts for shots that have none (local writer LLM)")
    dr.add_argument("spec")
    dr.add_argument("--all", action="store_true", help="redraft every shot")
    up = sub.add_parser("upload", help="upload text (title, description, tags) + thumbnails into upload/")
    up.add_argument("spec")
    up.add_argument("--text", action="store_true")
    up.add_argument("--thumbs", action="store_true")
    up.add_argument("--force", action="store_true", help="redo existing files")
    asp = sub.add_parser("asset", help="make 4 options for a library draft (studio/drafts/<id>)")
    asp.add_argument("draft")
    sg = sub.add_parser("song", help="song takes for an episode, or master the picked take")
    sg.add_argument("spec")
    sg.add_argument("--n", type=int, default=4)
    sg.add_argument("--master", metavar="TAKE")
    sg.add_argument("--import", dest="import_", metavar="AUDIO", help="use an existing mastered song (shots rebuilt on its bar grid)")
    vo = sub.add_parser("voice", help="make a sample of a voice style")
    vo.add_argument("voice", nargs="+")
    op = sub.add_parser("options", help="draw N versions of one shot's keyframe (keys/options/<shot>/)")
    op.add_argument("spec")
    op.add_argument("shot")
    op.add_argument("--n", type=int, default=4)
    di = sub.add_parser("director", help="propose shot-list changes from a plain-words request (applied in the studio)")
    di.add_argument("spec")
    di.add_argument("--ask", required=True)
    di.add_argument("--shots", nargs="*")
    ck = sub.add_parser("check", help="auto-check keyframes or clips with the local vision model (hints in checks.json)")
    ck.add_argument("spec")
    ck.add_argument("--stage", choices=["keys", "clips"], default="clips")
    ck.add_argument("--only", nargs="*")
    ck.add_argument("--force", action="store_true", help="check again even if unchanged")
    hm = sub.add_parser("home", help="show (or --set) this computer's content folder")
    hm.add_argument("--set", metavar="DIR", help="use DIR as the content folder (creates it from templates/home)")
    mg = sub.add_parser("migrate", help="move episodes/assets/library/briefs out of the repo into a content folder")
    mg.add_argument("--to", required=True, metavar="DIR")
    mg.add_argument("--dry-run", action="store_true")
    st = sub.add_parser("studio", help="run the Rhymeworks studio (web app + GPU queue) on http://127.0.0.1:PORT")
    st.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    if args.cmd in ("home", "migrate"):
        from pathlib import Path

        from . import paths
        if args.cmd == "migrate":
            for line in paths.migrate(Path(args.to), args.dry_run):
                print(("would move " if args.dry_run else "moved ") + line)
            if not args.dry_run:
                print(f"content folder → {Path(args.to).expanduser().resolve()} (saved in {paths.LOCAL_CONFIG.name}); restart the studio")
        elif args.set:
            home = paths.ensure_home(Path(args.set).expanduser().resolve())
            paths.set_home(home)
            print(f"content folder → {home} (saved in {paths.LOCAL_CONFIG.name}); restart the studio")
        else:
            print(f"content folder: {paths.HOME}  ({paths.HOME_SOURCE})")
            print(f"this computer only: {paths.STATE}")
        return
    if args.cmd == "studio":
        from .studio.app import serve
        serve(args.port)
    elif args.cmd == "song":
        from . import songmaker
        songmaker.main(args)
    elif args.cmd == "voice":
        from . import songmaker
        songmaker.voice_main(args)
    elif args.cmd == "asset":
        from . import assetmaker
        assetmaker.main(args)
    elif args.cmd == "upload":
        from . import upload
        upload.main(args)
    elif args.cmd == "options":
        from . import keyoptions
        keyoptions.main(args)
    elif args.cmd == "director":
        from . import shotdirector
        shotdirector.main(args)
    elif args.cmd == "check":
        from . import checks
        checks.main(args)
    elif args.cmd == "draft":
        from . import drafter
        drafter.main(args)
    elif args.cmd == "pixar":
        from . import pixar
        pixar.main(args)
    elif args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "schema":
        print(json.dumps(EpisodeBrief.model_json_schema(), indent=2))
    elif args.cmd == "shows":
        for p in sorted(LIB.glob("*/show.json")):
            s = read_json(p)
            print(f"{s['id']:<16} {s['title']:<18} cast: {', '.join(c['id'] for c in s['cast'])}; scenes: {', '.join(x['id'] for x in s['scenes'])}")


if __name__ == "__main__":
    sys.exit(main())
