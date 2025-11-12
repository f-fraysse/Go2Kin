# Go2Kin 🎥

**Multi-camera GoPro control for biomechanics research** - A PyQt6 application that bridges consumer hardware with research-grade motion capture workflows.

![Python](https://img.shields.io/badge/python-3.10-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-GUI-green.svg)
![Status](https://img.shields.io/badge/status-Stage%201%20Complete-brightgreen.svg)

## What it does

Go2Kin enables researchers to control up to 4 GoPro HERO12 cameras simultaneously for synchronized biomechanics recording. Built for academic labs, it provides an intuitive interface for multi-camera coordination, trial management, and automated file organization.

## ✨ Key Features

- 🎬 **Multi-Camera Control** - Manage up to 4 GoPro HERO12 cameras simultaneously
- 🔄 **Synchronized Recording** - Coordinated start/stop across selected cameras
- 📁 **Trial Management** - Automatic file naming and organized storage
- ⚡ **Flexible Recording** - Record with any subset of connected cameras (1-4)
- 🖥️ **Responsive UI** - Thread-safe operations with real-time status updates
- 💾 **Configuration Persistence** - Settings saved between sessions
- 🔍 **Live Preview** - Camera selection and positioning support

## 🚀 Quick Start

```bash
# 1. Clone and setup environment
git clone https://github.com/yourusername/Go2Kin.git
cd Go2Kin
conda create -n Go2Kin python=3.10
conda activate Go2Kin

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the application
python main.py
```

**Hardware Setup**: Connect GoPro HERO12 cameras via USB-C and ensure they're on the same network.

## 📱 Usage

1. **Camera Settings** - Connect cameras, configure settings (lens, resolution, FPS)
2. **Recording** - Select cameras, set trial name, start synchronized recording
3. **File Management** - Automatic download and organization in trial folders

## 📁 Project Structure

```
Go2Kin/
├── src/go2kin/          # Main application
│   ├── gopro/           # Camera control
│   └── ui/              # GUI components
├── goproUSB/            # Camera library
├── main.py              # Entry point
└── requirements.txt     # Dependencies
```

## 🛣️ Roadmap

- [x] **Stage 1**: Multi-camera GoPro control ✅
- [ ] **Stage 2**: Camera calibration
- [ ] **Stage 3**: Post-processing synchronization
- [ ] **Stage 4**: Pose detection & estimation
- [ ] **Stage 5**: 3D triangulation & reconstruction
- [ ] **Stage 6**: Kinematic analysis & joint angles

## 🔧 Technical Details

- **Architecture**: Thread-safe PyQt6 GUI with signal/slot communication
- **Camera Communication**: HTTP API via goproUSB library
- **Configuration**: JSON-based persistence with sensible defaults
- **File Organization**: Trial-based structure with auto-incrementing

## 🤝 Contributing

This research-focused project prioritizes clarity and modularity. Contributions welcome for:
- Hardware compatibility testing
- UI/UX improvements
- Pipeline stage implementations
- Documentation enhancements

## 📄 License

Academic research project building on [goproUSB](https://github.com/lukasj/goproUSB). See individual module licenses for terms.

## 🙏 Acknowledgments

- **goproUSB** by Lukasz J. Nowak - Foundation camera control library
- **PyQt6** - Cross-platform GUI framework
- **Research Community** - Biomechanics and motion capture researchers

---

**Version 0.1.0** - Stage 1 Implementation Complete  
*Ready for multi-camera biomechanics research* 🔬
