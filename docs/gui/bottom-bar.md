# Bottom bar — camera status & controls

Always visible at the bottom of the window, regardless of the selected tab.

> 🚧 **TODO:** screenshot with callouts.

## Controls

- **Per-camera status** — green/red connection indicator, **Connect/Disconnect** toggle and battery level for each camera. Serial numbers are read from `go2kin_config.json`.
- **Resolution** and **FPS** dropdowns — global; applied to **all connected cameras** simultaneously. Options are currently hardcoded for the Hero 12 Black with 50 Hz anti-flicker (Australia): 1080 / 2.7K / 4K and 25 / 50 / 100 / 200 fps. See [Known issues](../troubleshooting.md) for 60 Hz regions and other camera models.
- **Trial timer** — *(🚧 TODO: describe; known issue — keeps running after Stop.)*

## Settings applied automatically on connect

Applied on every connect, to keep cameras consistent:

| Setting | Value | Reason |
|---|---|---|
| Control Mode | Pro | Full manual control |
| Video Lens | Linear | No distortion for pose estimation |
| GPS | Off | Not needed; saves battery |
| HindSight | Off | Not needed |
| Hypersmooth | Off | Introduces frame warping |
| LCD Brightness | 30% | Saves battery |
| Anti-Flicker | 50 Hz | Australian mains frequency |
| Auto WiFi AP | Off | Not needed over USB |

Resolution, FPS, lens and digital zoom are restored from each camera's saved profile.
