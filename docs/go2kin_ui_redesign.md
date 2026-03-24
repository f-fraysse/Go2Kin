# Go2Kin GUI Redesign Plan

## Overall Architecture

### Persistent Top Bar (replaces Project tab)
- **Project** dropdown + "+" button
- **Session** dropdown + "+" button
- **Participant** dropdown + "+" button
- **Calibration** name + age indicator (e.g. "calib_initial — 3 days old") — static text
- Cascading enablement: no project → session disabled, no session → participant disabled, etc.
- First-time users see an empty project dropdown with everything else greyed out — self-explanatory

```
┌─────────────────────────────────────────────────────┐
│ Project:[tests_home▾][+] Session:[weekend_march▾][+]│
│ Participant:[P01▾][+]  Calib: initial — ✅ 3d  [⚙] │
├─────────────────────────────────────────────────────┤
│ Preview│Calibration│Recording│Processing│Visualise  │
├─────────────────────────────────────────────────────┤
│                                                     │
│             (active tab content)                    │
│                                                     │
```

First-time / empty state:
```
┌─────────────────────────────────────────────────────┐
│ Project:[        ▾][+] Session:[(disabled)▾]        │
│ Participant:[(disabled)▾] Calib: —     ← start [⚙] │
├─────────────────────────────────────────────────────┤
│ Preview│Calibration│Recording│Processing│Visualise  │
```

### Persistent Bottom Bar
- Camera connection status: GP1–GP4 with connect buttons, status indicators
- Resolution, FPS, Rec delay settings
- Sync method: exclusive radio buttons — Manual (hand clap) | Speaker

```
│             (active tab content)                    │
│                                                     │
├─────────────────────────────────────────────────────┤
│ Log [cal][rec][proc]                                │
│ 14:32 Extrinsic cal complete — reproj 0.42px        │
│ 14:31 Audio sync OK — 4/4 cameras synced            │
├─────────────────────────────────────────────────────┤
│ 🟢GP1[Con] 🟢GP2[Con] 🔴GP3[Con] 🔴GP4[Con]       │
│ Res:[4K▾] FPS:[50▾] Sync:◉Manual ○Speaker Dly:[3]s │
└─────────────────────────────────────────────────────┘
```

### Tab Structure
Old: Project | Live Preview | Calibration | Recording | Processing | Visualisation
New: Live Preview | **Calibration** | **Recording** | **Processing** | **Visualisation**

Project tab is eliminated — its contents move to the top bar. Project management (delete trials, participants, calibrations) accessible via a gear icon or "Manage" button in the top bar.

### Shared Progress Log
- Fixed panel docked just above the camera bar (shown in bottom bar layout above)
- Always visible on every tab — not collapsible
- Shows 3-4 lines, scrollable for history
- Logs calibration, recording, and processing events in one chronological stream
- Filter buttons by source (cal / rec / proc) to reduce noise
- Acts as a passive system heartbeat — user glances down to confirm things are working

---

## Design Principles

### Button Hierarchy
- **Primary actions** (Record, Process, Calibrate): large, visually dominant, colored
- **Secondary actions** (Browse, Save, Load): standard grey
- **Destructive actions** (Delete, Clear): distinct style (e.g. red outline)
- Every button that does the same kind of thing should look the same across all tabs

### Record/Stop Pattern (define once, reuse everywhere)
Used in: intrinsic calibration, extrinsic calibration, set origin, trial recording.
- Same visual language everywhere: grey when idle, red when recording, same animation, same stop icon
- **Scale differs**: trial recording gets the big dramatic version; calibration record buttons are smaller
- State change must be unmissable — even from across the room

### Session Trials List (shared component across tabs)
Appears on: **Recording**, **Processing**, **Visualisation**
- Same position, same appearance, same behavior on all three tabs — switching tabs should feel seamless, eye doesn't have to re-find the list
- Shows all trials for the current session
- Columns: Trial name, Sync status (✅ green / 🟡 amber)
- Additional columns per tab: Processing adds processing status; Visualisation highlights the selected/active trial
- Delete trial available from any tab where the list appears
- Selection state persists when switching tabs (if you selected "walking_02" on Recording, it's still highlighted on Processing)

### Status Indicators (consistent everywhere)
- ✅ Green checkmark = done / good
- ⚫ Grey dash = not started
- 🟡 Amber = stale / old / partial
- 🔴 Red = failed / needs attention
- Replace all plain-text status ("Not calibrated", "Processed", "3 days old") with visual indicators

---

## Calibration Tab

### Layout: Vertical Pipeline

The tab is structured as a sequential pipeline flowing top to bottom. Each step enables the next.

```
┌─────────────────────────────────┐  ┌──────────────────────────┐
│                                 │  │                          │
│  [Charuco Board Config ▸]      │  │    Camera Positions      │
│  (collapsed by default)        │  │    3D Plot               │
│  Status: ✅ 5×7, 11.7cm       │  │                          │
│                                 │  │    (updates live as      │
│  ─────────────────────────      │  │     calibration steps    │
│                                 │  │     complete)            │
│  [Calibrate Intrinsics ▸]      │  │                          │
│  (collapsed by default)        │  │                          │
│  Status: ✅ 4/4 cameras        │  │                          │
│                                 │  │    (updates live as      │
│  ─────────────────────────      │  │     calibration steps    │
│                                 │  │     complete)            │
│  [ Calibrate Extrinsics ]      │  │                          │
│  (main daily action)           │  │                          │
│  Sound source: X__ Y__ Z__    │  │                          │
│  Status: not calibrated        │  │                          │
│                                 │  │                          │
│  ─────────────────────────      │  │                          │
│                                 │  │                          │
│  [ Set Origin ]                │  │                          │
│  (enabled after extrinsics)    │  │                          │
│  Sound source: X__ Y__ Z__    │  │                          │
│  Status: not set               │  │                          │
│                                 │  │                          │
│  ─────────────────────────      │  │                          │
│                                 │  │                          │
│  [ Apply Calibration ]          │  │                          │
│  (enabled after all steps)     │  │                          │
│                                 │  │                          │
└─────────────────────────────────┘  └──────────────────────────┘
```

### Flow (top to bottom)

1. **Load** (in top bar) — loads existing calibration, intrinsics populate automatically
2. **Charuco Board Config** — collapsed by default. Only needed on first setup or board change
3. **Calibrate Intrinsics** — collapsed by default, shows status. Expand only on first setup or camera change
4. **Calibrate Extrinsics** — primary daily action, always visible
5. **Set Origin** — enabled after extrinsics complete
6. **Apply** — user reviews result (3D plot, quality indicators), clicks Apply to make it the active calibration. Auto-saved with timestamp name behind the scenes. Top bar updates to "calib — 0 days old." If result looks bad, user simply recalibrates without having committed a junk calibration.

### Calibrate Extrinsics: Automated Flow
User experience: **one button press**

1. User clicks **"Calibrate Extrinsics"**
2. **5-second countdown** — big, visually obvious ("3... 2... 1..."), user knows "don't move yet"
3. Recording starts — button turns red, shows timer
4. User waves charuco board
5. User clicks **Stop**
6. App automatically: downloads videos → audio sync → runs calibration algorithm
7. **If audio sync fails** → popup warning, user re-does calibration
8. **If calibration quality is poor** → amber/red status indicator
9. **If success** → green checkmark, Set Origin button enables
10. Videos deleted automatically after processing (no file management for user)

### Set Origin: Same Automated Flow
Same one-button pattern as extrinsics. Click → countdown → record → stop → auto-process.

### Charuco Board Configuration
- Collapsed by default — show status line like "✅ Board configured (5×7, 11.7cm)"
- On first setup or if no board config found: expanded with prompt to configure
- Once set, basically never touched again (only if physically changing the board)

### Intrinsic Calibration
- Collapsed by default — show status line like "✅ Intrinsics loaded (4 cameras)"
- On first setup or if no intrinsics found: expanded with prompt to complete intrinsics first
- For new projects: redo intrinsics (simpler than cross-project import; takes a few minutes)

### Sound Source Position
- **Not** a standalone section (remove current separate group box)
- Sync method selected via radio buttons in the bottom bar: **Manual** (hand clap) | **Speaker**
- **Manual mode**: sound source X/Y/Z field appears inline within Extrinsic section, Set Origin section, and Recording tab trial setup. Contextual: "where am I clapping from for this recording?" Defaults to last-used position.
- **Speaker mode**: sound source X/Y/Z set once (in bottom bar or project settings), stays fixed. Displayed as a reminder but not re-entered per recording.

---

## Live Preview Tab

### Zoom Control
- This is the **only** tab where digital zoom level can be changed
- Prominent static warning displayed whenever zoom controls are visible:
  **"⚠ Changing zoom requires recalibrating intrinsics"**
- Warning should be impossible to miss — not a tooltip or fine print, but a visible persistent label next to the zoom control

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  ┌───────────────────┐ ┌───────────────────┐   │
│  │                   │ │                   │   │
│  │     GP1 feed      │ │     GP2 feed      │   │
│  │                   │ │                   │   │
│  └───────────────────┘ └───────────────────┘   │
│  ┌───────────────────┐ ┌───────────────────┐   │
│  │                   │ │                   │   │
│  │     GP3 feed      │ │     GP4 feed      │   │
│  │                   │ │                   │   │
│  └───────────────────┘ └───────────────────┘   │
│                                                 │
│  Zoom: [====○=========] 1.0x                    │
│  ⚠ Changing zoom requires recalibrating         │
│    intrinsics                                   │
│                                                 │
└─────────────────────────────────────────────────┘
```

---

## Recording Tab

### Design Philosophy
This is the "doing the thing" tab — should feel like a cockpit, not a form.

### Layout
- **Big, fat buttons and text** — this tab has space, use it
- Trial setup at top, big record button in the center, session trials list on the side or below
- **START RECORDING** button: large, prominent, impossible to miss
- Camera selection: clear checkboxes showing which cameras are active

Idle state:
```
┌──────────────────────────────┐ ┌────────────────┐
│                              │ │ Session Trials  │
│  Trial: [walking_03     ]    │ │                │
│                              │ │ walking     ✅ │
│  Calib: initial — ✅ 3d     │ │ walking_02  ✅ │
│  Cameras: ☑GP1 ☑GP2 ☑GP3   │ │ jumping     🟡 │
│  Sound src: X[0] Y[1] Z[0]  │ │                │
│                              │ │                │
│      ┌───────────────┐      │ │                │
│      │               │      │ │                │
│      │  ● RECORD     │      │ │                │
│      │               │      │ │          [DEL] │
│      └───────────────┘      │ └────────────────┘
│                              │
└──────────────────────────────┘
```

Recording state:
```
┌──────────────────────────────┐ ┌────────────────┐
│                              │ │ Session Trials  │
│  Trial: walking_03           │ │                │
│                              │ │ walking     ✅ │
│  ┌────────────────────────┐  │ │ walking_02  ✅ │
│  │                        │  │ │ jumping     🟡 │
│  │    🔴  02:34           │  │ │                │
│  │                        │  │ │                │
│  │   ┌──────────────┐    │  │ │                │
│  │   │  ■ STOP      │    │  │ │                │
│  │   └──────────────┘    │  │ │                │
│  │                        │  │ │                │
│  └────────────────────────┘  │ │          [DEL] │
│                              │ └────────────────┘
└──────────────────────────────┘
```

### Recording State Change
Clicking Record triggers a dramatic, unmissable visual change:
- 5-second countdown before recording begins
- Button turns **red**, changes to say **"STOP"**, appears "pushed in"
- **Red circle** with **red mm:ss timer** appears prominently
- The whole tab should feel different when recording vs idle
- Must be visible from across the room while positioning a participant

### Post-Recording: Auto Sync
After user clicks Stop:
1. Videos download from cameras
2. Audio sync runs automatically (takes a few seconds)
3. Trial appears in session list with sync status
4. Trial name field auto-advances to next name

### Trial Name
- Big, prominent text field — this is the main thing you set before each recording
- Auto-updates to show what the **next** trial will be saved as (don't keep previous trial name stale)
- Keep existing `_01`, `_02` auto-increment logic if name unchanged between trials
- E.g. after recording "walking", field auto-updates to "walking_02"

### Trial Setup
- Participant dropdown (from top bar selection)
- Calibration dropdown with age hint ("3 days old" — keep this, it's good)
- Sound source position (X, Y, Z) — shown if sync mode is Manual

### Session Trials List
- Visual list of trials completed in this session, updates live after each recording
- Shows at-a-glance progress: how many trials done, their names, sync status
- Sync status indicators:
  - ✅ Green: good sync (two claps detected on all cameras, consistent delays, sensible values)
  - 🟡 Amber: sync had issues (flag only — no detailed diagnosis in UI; user was there, they'll know what went wrong)
- Trials with bad sync are kept, not deleted — user decides whether to redo or keep
- Select a trial and delete it — useful for cleaning up botched recordings on the spot rather than dealing with junk data later

---

## Processing Tab

### Layout
- Flat list of trials for the current session (session selected via top bar)
- Select All / Deselect All buttons
- Delete selected trial(s) — same as Recording tab, useful for cleaning up amber-sync trials you don't want to process
- No Refresh button — list updates automatically via events (trial recorded, trial processed, trial deleted)
- **"Process Selected"** button should be visually dominant — primary action of the tab
- Tab will be fairly empty — that's fine for now

```
┌─────────────────────────────────────────────────┐
│                                                 │
│  [Select All] [Deselect All]           [Delete] │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │   Trial        Sync  Processing         │   │
│  │ ☑ walking       ✅    ✅ Processed      │   │
│  │ ☑ walking_02    ✅    ⚫ Pending        │   │
│  │ ☐ jumping       🟡    ⚫ Pending        │   │
│  │                                         │   │
│  └─────────────────────────────────────────┘   │
│                                                 │
│  ┌─────────────────────────┐                   │
│  │                         │                   │
│  │   PROCESS SELECTED      │                   │
│  │                         │                   │
│  └─────────────────────────┘                   │
│                                                 │
│  Processing: pose detection 2/4 cameras         │
│  [===========             ] 45%                 │
│                                                 │
└─────────────────────────────────────────────────┘
```

### Trial List
- Columns: Trial name, Sync status (carried from recording: ✅ green / 🟡 amber), Processing status
- Processing status icons: ⚫ Pending | 🔄 Processing | ✅ Processed | ❌ Failed
- Both statuses visible at a glance — user can decide to skip amber-sync trials or process them anyway
- Progress indicator: show current step (e.g. "pose detection 2/4 cameras") or at minimum a progress bar for the active trial

### Updates
- Event-driven, not polling: list refreshes when a trial finishes recording, finishes processing, or gets deleted
- No timer loop needed — the app already knows when these events happen

### Log
- Uses shared log panel at bottom — no dedicated log box on this tab

---

## Visualisation Tab

### Changes (minor — already the best tab)
- Uses shared Session Trials List component (same position and behavior as Recording/Processing tabs)
- Clicking a trial in the list loads it for playback
- Playback scrubber: make it larger / easier to grab
- Consider expanding abbreviations: "2D kpts" → "2D Keypoints", "3D kpts" → "3D Keypoints"
- Info panel: could be lightly structured rather than plain text

```
┌────────────────┐ ┌──────────────────────────────┐
│ Session Trials  │ │                              │
│                │ │                              │
│ walking     ✅ │ │                              │
│ walking_02  ✅ │ │       Video playback         │
│ jumping     🟡 │ │       with overlaid          │
│                │ │       keypoints               │
│          [DEL] │ │                              │
├────────────────┤ │                              │
│ Camera         │ │                              │
│ [GP1] GP2 GP3  │ │                              │
├────────────────┤ │                              │
│ Overlay        │ └──────────────────────────────┘
│ ☑ 2D Keypoints │ ┌──────────────────────────────┐
│ ☐ 3D Keypoints │ │ << -1 [Play] +1 >> Loop      │
├────────────────┤ │ [======○===========] 42/251   │
│ Info           │ └──────────────────────────────┘
│ Subject: P01   │
│ FPS: 50        │
│ Res: 3840x2160 │
│ Frames: 251    │
└────────────────┘
```

---

## Space Management

### Problem
Multiple tabs have fixed-size containers (subjects table, progress logs, trial lists) that waste space when content is short.

### Solution
- Lists and tables should shrink to fit content, not fill a fixed area
- Give reclaimed space to elements that benefit from it (video preview, 3D plot, etc.)
- Empty states should be compact with clear calls to action, not giant empty boxes

---

## Future Considerations (not immediate)

- **Guided first-run experience**: welcome screen for brand new users (only needed if distributing to strangers)
- **Settings/Config area**: for rarely-changed options that don't belong on workflow tabs
- **Quick start guide**: one-page markdown for onboarding grad students (more valuable than onboarding UI)

## Notes on log in GUI

currently inconsistent.
need to fix the way log is done between console / terminal. At the moment i'm essentially trying to "pipe" / redirect the terminal output to the console. It does not work cleanly. Also, I have lost some terminal output (doesn't appear in either terminal or GUI console). I think I will just remove GUI log, make sure everything is back in terminal then think  about it once rest of UI is redesigned. Can just monitor terminal on the side in the meantime