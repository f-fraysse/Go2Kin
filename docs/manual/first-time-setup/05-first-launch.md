# 5. First launch of the GUI

Activate the environment and start Go2Kin:

```
conda activate Go2Kin
python code/go2kin.py
```

If you didn't set `data_root` in the config, you'll be prompted to select the data
folder now.

## Create your first project, session and participant

All three live in the **top bar** (see [Top bar](../gui/top-bar.md)):

1. **Project** — click **+** next to the Project dropdown.
2. **Session** — click **+** next to the Session dropdown.
3. **Participant** — click **Manage** (or **+**) and enter initials, age, sex, **height** and **mass**. Height and mass are required later for OpenSim model scaling.

Selections persist between launches. The calibration indicator will show **red** — no
calibration exists yet; that comes next.

> 🚧 **TODO:** naming conventions — what a project and a session each represent (study? lab visit?), and a recommended scheme (study code, date-based sessions…).

> 🚧 **TODO:** screenshot of first launch with the three top-bar steps annotated.
