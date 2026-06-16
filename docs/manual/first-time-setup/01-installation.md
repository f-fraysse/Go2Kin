# 1. Install Go2Kin

## Prerequisites

- Windows 11
- `git`, `conda` (Miniconda or Anaconda) and a current NVIDIA driver installed

> 🚧 **TODO:** links to installers; note any admin rights / IT requests needed on managed (e.g. university) PCs.

## Install

Clone the repository:

```
git clone https://github.com/f-fraysse/Go2Kin.git
cd Go2Kin
```

Create and activate the Conda environment:

```
conda create -n Go2Kin python=3.10
conda activate Go2Kin
```

Install dependencies:

```
pip install -r requirements.txt
conda install -c conda-forge ffmpeg
```

### NVENC ffmpeg (required for high-resolution / high-frame-rate recording)

The automatic audio synchronisation re-encodes each clip on the NVIDIA GPU using
ffmpeg's `hevc_nvenc` encoder. The `conda-forge` ffmpeg installed above **does not
include NVENC** and cannot process high-resolution / high-frame-rate footage (for
example 2.7K at 200 fps) — sync will fail with an encoder error. You must replace it with
a full ffmpeg build that has NVENC:

1. **Close Go2Kin** if it is running (otherwise the ffmpeg file is locked and cannot be replaced).
2. Download a build that matches your NVIDIA driver. The **n7.1** build from
   [BtbN's FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds/releases) —
   `ffmpeg-n7.1-latest-win64-gpl-7.1.zip` — works with current drivers. (Avoid the
   `master`/`latest` build: it requires a very new driver and otherwise fails with
   *"Driver does not support the required nvenc API version"*.)
3. Unzip it, then copy `bin\ffmpeg.exe` and `bin\ffprobe.exe` from the unzipped folder
   **over** the existing files in your Conda environment's binary folder, e.g.
   `C:\Users\<you>\miniconda3\envs\Go2Kin\Library\bin\` (or `D:\Miniconda3\envs\Go2Kin\Library\bin\`).
   Back up the originals first (rename them to `ffmpeg.exe.bak` / `ffprobe.exe.bak`) in case you want to revert.
4. Verify in an activated environment:

   ```
   ffmpeg -hide_banner -encoders | findstr nvenc
   ```

   This should list `hevc_nvenc`.

> ⚠️ Running `conda update ffmpeg` (or recreating the environment) reverts ffmpeg to the
> NVENC-less conda version. If high-frame-rate sync stops working after an update, repeat
> the steps above.

Install Pose2Sim as a submodule:

```
git submodule init
git submodule update
pip install -e ./code/pose2sim
pip uninstall onnxruntime
pip install onnxruntime-gpu==1.20.1
```

Install OpenSim:

```
conda install -c opensim-org opensim
```

## Check the install

> 🚧 **TODO:** quick verification — e.g. `ffmpeg -version` works; `python -c "import onnxruntime; print(onnxruntime.get_device())"` reports `GPU`; the GUI launches. List common install errors and fixes here as they're encountered.
