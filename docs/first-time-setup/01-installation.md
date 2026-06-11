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
