# 2. Create the data folder

Go2Kin stores all projects, sessions and trial videos under a single **data root** folder.

!!! warning "Lots of data"
    Multi-camera video accumulates fast. Put the data root on a drive with plenty of free
    space (ideally an SSD), and avoid a small system (C:) drive.

> 🚧 **TODO:** rough storage figures — GB per minute of 4-camera recording at common Resolution/FPS settings — and a recommended minimum free space.

1. Create a folder on a large drive, e.g. `D:/Markerless_Projects`.
2. Copy the config template and set the data root:

    ```
    cp go2kin_config_template.json go2kin_config.json
    ```

    Edit `go2kin_config.json` and set `data_root` to your folder.

3. Leave `last_project` and `last_session` empty — these are managed by the app.

If you skip this step, Go2Kin will prompt you to select a data root folder on first launch.

See [Data organisation](../reference/data-organisation.md) for what ends up inside this folder.

> 🚧 **TODO:** backup / archiving policy for the data root.
