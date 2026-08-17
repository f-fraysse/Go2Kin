# 3. Configure your GoPros

Each camera is identified by its **serial number**, which Go2Kin uses to derive the
camera's USB IP address (`172.2X.1YZ.51:8080`).

## Find the serial numbers

[Instructions from GoPro - find your GoPro serial number](https://community.gopro.com/s/article/How-to-Find-Your-GoPro-Serial-Number?language=en_US#h11)

## Enter them in the config

In `go2kin_config.json`, set `gopro_serial_numbers` to your cameras' serials (one entry
per camera, up to four).

## On-camera settings

Most settings are applied automatically each time a camera connects — see
[Bottom bar](../gui/bottom-bar.md) for the full list.


## Optional: settings discovery tool

Different GoPro versions (9/10/11/12/13) have slightly different API endpoints available [GoPro HTTP API reference](https://gopro.github.io/OpenGoPro/http/).
The settings discovery tool sends a request for each setting in turn, with an invalid option, so the GoPro returns a list of available options. It then builds a list of available settings for this camera.

You should only need this tool if you're using a different model than Hero 11 (and even then, we don't guarantee it works 100% as there seems to be out-of-date info in the API doc). 

Run once per camera model/firmware to generate a settings reference file in
`config/settings_references/` (maps setting IDs to human-readable names and options):

```
python tools/discover_camera_settings.py <camera_serial_number>
```

