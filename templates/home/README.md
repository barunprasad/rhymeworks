# Rhymeworks content folder

Everything you make lives here, separate from the Rhymeworks code:

- `episodes/<slug>/`: each episode (episode.toml, song, keyframes, clips, the finished film)
- `assets/`: your characters, props and places (`registry.toml` lists them), `brand/` (optional channel intro and icon), voice styles
- `projects.toml`: your channels

Put this folder inside Google Drive for desktop, iCloud Drive or Dropbox to see your work on your other computers,
then point Rhymeworks at it: `uv run --project pipeline kidzone home --set "<this folder>"`.

Never stored here: the job queue, logs and drafts (they may hold photo references of real people). Those stay on each computer.
