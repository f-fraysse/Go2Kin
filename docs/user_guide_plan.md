# User Guide with MkDocs

## Context
Go2Kin needs a user guide/manual accessible from the GUI. MkDocs with Material theme will generate a static HTML site from Markdown files. A "?" button in the top bar opens it in the default browser.

## Implementation

### 1. MkDocs setup
- Create `mkdocs.yml` in repo root with Material theme config, nav structure
- Source files in `docs/user_guide/`, built site output to `docs/user_guide/site/`
- Built site committed to git (no build step needed for end users)

### 2. Guide content (Markdown pages)
- `index.md` — Overview, getting started, general workflow
- `live-preview.md` — Live Preview tab
- `calibration.md` — Calibration tab
- `recording.md` — Recording tab (including audio sync)
- `processing.md` — Processing tab (Pose2Sim)
- `visualisation.md` — Visualisation tab
- `camera-bar.md` — Bottom camera bar (connect, resolution, FPS)
- `project-setup.md` — Top bar project/session/participant management

Content will be basic descriptions of each tab's purpose, controls, and typical workflow. Can be expanded later.

### 3. GUI button — `code/GUI/top_bar.py`
- Add a "?" button packed `side=tk.RIGHT` in the top bar (next to Manage button)
- On click: `webbrowser.open()` pointing to `docs/user_guide/site/index.html`
- Derive repo root from `__file__` path (top_bar.py -> GUI/ -> code/ -> repo root)

### 4. Build & dependencies
- Add `mkdocs-material` to requirements.txt
- Document rebuild command: `mkdocs build` (run from repo root when docs change)
- Built site committed to git — works out of the box

### Files to create/modify
- **Create**: `mkdocs.yml`, `docs/user_guide/*.md` (8 files)
- **Modify**: `code/GUI/top_bar.py` (add ? button + webbrowser.open)
- **Modify**: `requirements.txt` (add mkdocs-material)

### Verification
- Run `mkdocs build` and confirm site generates in `docs/user_guide/site/`
- Run `python code/go2kin.py`, click "?" button, confirm browser opens user guide
- Navigate between pages to verify inter-page links work
