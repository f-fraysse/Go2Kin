# 3. Configure your GoPros

Each camera is identified by its **serial number**, which Go2Kin uses to derive the
camera's USB IP address (`172.2X.1YZ.51:8080`).

## Find the serial numbers

- On the label inside the battery compartment, **or**
- in the camera menu (Preferences → About), **or**
- via USB once the camera is connected.

> 🚧 **TODO:** exact steps for reading the serial over USB, with a photo of where the label sits.

## Enter them in the config

In `go2kin_config.json`, set `gopro_serial_numbers` to your cameras' serials (one entry
per camera, up to four).

> 🚧 **TODO:** example JSON snippet; state whether order in the list matters (e.g. maps to Cam 1–4 in the GUI).

## On-camera settings

Most settings are applied automatically each time a camera connects — see
[Bottom bar](../gui/bottom-bar.md) for the full list.

> 🚧 **TODO:** confirm and document any one-off, on-camera setting required for USB control (e.g. Connections → USB Connection mode).

## Optional: settings discovery tool

Run once per camera model/firmware to generate a settings reference file in
`config/settings_references/` (maps setting IDs to human-readable names and options):

```
python tools/discover_camera_settings.py <camera_serial_number>
```
