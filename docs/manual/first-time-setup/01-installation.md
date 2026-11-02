# 1. Install Go2Kin

## Prerequisites

- `git` and `conda` (Miniconda or Anaconda) and a current NVIDIA driver installed.

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

### NVENC ffmpeg (no longer required)

Older versions of Go2Kin re-encoded every clip during sync and needed an ffmpeg build with
NVIDIA's `hevc_nvenc` encoder. Sync now only stores frame offsets and never re-encodes, so
the `conda-forge` ffmpeg installed above is enough. If you have already replaced ffmpeg,
you can keep it. To install the full build anyway (e.g. for GPU video decoding):

1. Close Go2Kin if it is running (otherwise the ffmpeg file is locked and cannot be replaced).
2. Download a build that matches your NVIDIA driver. The **n7.1** build from
   [BtbN's FFmpeg Builds](https://github.com/BtbN/FFmpeg-Builds/releases) —
   `ffmpeg-n7.1-latest-win64-gpl-7.1.zip` — works with current drivers. (Avoid the
   `master`/`latest` build: it requires a very new driver and otherwise fails with
   *"Driver does not support the required nvenc API version"*.)
3. Unzip it, then copy `bin\ffmpeg.exe` and `bin\ffprobe.exe` from the unzipped folder
   **over** the existing files in your Conda environment's binary folder, e.g.
   `C:\Users\<you>\miniconda3\envs\Go2Kin\Library\bin\` (or `D:\Miniconda3\envs\Go2Kin\Library\bin\`).
   Back up the originals first in case you want to revert.
4. Verify in your conda environment:

   ```
   ffmpeg -hide_banner -encoders | findstr nvenc
   ```

   This should list `hevc_nvenc`.

> Running `conda update ffmpeg` (or recreating the environment) reverts ffmpeg to the
> NVENC-less conda version.

## Install Pose2Sim as a submodule:

```
git submodule init
git submodule update
pip install -e ./code/pose2sim
pip uninstall onnxruntime
pip install onnxruntime-gpu==1.20.1
```

> ⚠️ Installing Pose2Sim installs RTMlib which installs onnxruntime (CPU version). The last two steps are to ensure onnxruntime-gpu is the installed version instead.
> 
## Install OpenSim:

```
conda install -c opensim-org opensim
```

## Check the install

> 🚧 **TODO:** quick verification — e.g. `ffmpeg -version` works; `python -c "import onnxruntime; print(onnxruntime.get_device())"` reports `GPU`; the GUI launches. 
