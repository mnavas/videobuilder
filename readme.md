# VideoBuilder

A desktop video editor (Windows-Movie-Maker-style timeline editing): video/audio/image clips,
trimming, crossfades, titles, and batch-adding photos as a stop-motion-style sequence, all in one
timeline, exporting via ffmpeg.

See [analysis.md](analysis.md) for scope/rationale and [plan.md](plan.md) for the
implementation phases. Progress is tracked in [changelog.md](changelog.md).

## Requirements

- Python 3.10+
- `ffmpeg` and `ffprobe` available on `PATH`

## Setup

```bash
cd VideoBuilder
python3 -m venv .venv
source .venv/bin/activate   # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Run

```bash
./run.sh
```

`run.sh` creates the venv and installs dependencies on first use, then launches the app.
Equivalent manual steps:

```bash
source .venv/bin/activate
python -m videobuilder.main
```
