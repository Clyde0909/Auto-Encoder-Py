# Advanced Video Encoder

A comprehensive Python-based video encoding application with hardware acceleration support, intelligent resolution scaling, and real-time progress monitoring.

## Features

### Hardware Detection & Acceleration
- **Automatic GPU Detection**: Detects NVIDIA GeForce, AMD Radeon, and Intel integrated graphics
- **Hardware Acceleration**: Supports NVIDIA NVENC, AMD VCE, and Intel QuickSync
- **Smart Codec Selection**: Automatically selects the best encoder based on available hardware
- **Fallback Support**: Falls back to CPU-based encoding when hardware acceleration is unavailable

### Resolution Management
- **Preset Resolutions**: HD (720p), FHD (1080p), QHD (1440p), UHD (4K)
- **Intelligent Scaling**: Automatically downscales videos exceeding target resolution
- **Aspect Ratio Preservation**: Maintains original aspect ratio during scaling
- **No Unnecessary Upscaling**: Preserves smaller videos at their original resolution

### Encoding Methods
- **Quality-Based (CRF)**: Constant Rate Factor encoding for consistent quality
- **Bitrate-Based (VBR)**: Variable bitrate encoding with customizable multipliers
- **Quality Presets**: Ultra High, High, Medium, Low, Very Low quality settings
- **Custom Parameters**: Fine-tune encoding settings for specific requirements

### Real-Time Interface
- **Rich Terminal UI**: Beautiful progress bars and real-time statistics
- **Live Progress Tracking**: Monitor encoding progress for each file
- **Comprehensive Statistics**: File sizes, compression ratios, encoding times
- **Error Handling**: Detailed error reporting and failed file management

## Requirements

- Python 3.8 or higher
- FFmpeg installed and accessible in PATH
- Supported video formats: MP4, AVI, MKV, MOV, WMV, FLV, WebM, M4V

## Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Auto-Encoder-Py
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install FFmpeg:**
   - **Windows**: Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
   - **macOS**: `brew install ffmpeg`
   - **Ubuntu/Debian**: `sudo apt install ffmpeg`

## Usage

### Basic Usage

Run the application:
```bash
python main.py
```

Follow the interactive prompts to:
1. Select target directory
2. Choose maximum resolution preset
3. Configure encoding method (CRF or VBR)
4. Set processing options

### Command Line Example

```python
from video_encoder import VideoEncoder
from resolution_handler import ResolutionPreset
from encoding_config import EncodingMethod

# Initialize encoder
encoder = VideoEncoder()

# Configure settings
encoder.set_resolution_preset(ResolutionPreset.FHD)
encoder.set_encoding_method(EncodingMethod.CRF, 23)

# Discover and encode files
video_files = encoder.discover_video_files("/path/to/videos")
results = encoder.encode_batch(video_files)
```

## Architecture

The application is built using a modular architecture:

### Core Modules

- **`hardware_detector.py`**: GPU detection and hardware acceleration capability assessment
- **`resolution_handler.py`**: Video resolution management and scaling calculations
- **`encoding_config.py`**: Encoding configuration management (CRF/VBR)
- **`progress_display.py`**: Real-time progress monitoring with Rich UI
- **`video_encoder.py`**: Main encoding engine that orchestrates all components
- **`main.py`**: Interactive application interface

### Key Classes

- **`HardwareDetector`**: Detects available GPUs and their encoding capabilities
- **`ResolutionHandler`**: Manages target resolution and scaling operations
- **`EncodingConfigManager`**: Handles encoding method configuration
- **`ProgressDisplay`**: Provides real-time progress feedback
- **`VideoEncoder`**: Main orchestrator for the encoding process

## Resolution Presets

| Preset | Resolution | Description |
|--------|------------|-------------|
| HD     | 1280×720   | HD (720p) - Standard definition |
| FHD    | 1920×1080  | Full HD (1080p) - High definition |
| QHD    | 2560×1440  | Quad HD (1440p) - Ultra high definition |
| UHD    | 3840×2160  | Ultra HD (4K) - Maximum quality |

## Hardware Acceleration

### Supported Encoders

| GPU Vendor | Encoder | Codec Support |
|------------|---------|---------------|
| NVIDIA     | NVENC   | H.264, H.265/HEVC |
| AMD        | VCE     | H.264, H.265/HEVC |
| Intel      | QuickSync | H.264, H.265/HEVC |

### Automatic Detection

The application automatically detects your hardware and selects the best available encoder:

1. **NVIDIA NVENC** (Priority 1) - Best performance and quality
2. **AMD VCE** (Priority 2) - Good performance
3. **Intel QuickSync** (Priority 3) - Decent performance
4. **Software (CPU)** (Fallback) - Highest quality, slowest speed

## Encoding Methods

### CRF (Constant Rate Factor) - Quality-Based
- **Range**: 0-51 (lower = higher quality)
- **Recommended**: 18-28 for most content
- **Use Case**: When consistent quality is more important than file size

### VBR (Variable Bitrate) - Bitrate-Based
- **Range**: 0.1-10.0x multiplier of original bitrate
- **Recommended**: 0.5-1.0x for most content
- **Use Case**: When specific file sizes or bitrates are required

## Performance Tips

1. **Use Hardware Acceleration**: Significantly faster encoding times
2. **Choose Appropriate CRF**: CRF 23 provides good balance of quality and size
3. **Batch Processing**: Process multiple files for efficiency
4. **SSD Storage**: Use SSD for input/output files when possible

## Troubleshooting

### Common Issues

**FFmpeg not found:**
- Ensure FFmpeg is installed and in your system PATH
- Test with: `ffmpeg -version`

**Hardware acceleration not working:**
- Check if your GPU supports hardware encoding
- Update GPU drivers to the latest version
- Some older GPUs may not support modern encoders

**Out of memory errors:**
- Reduce the number of concurrent encodings
- Use a lower resolution preset
- Close other applications to free up memory

**Slow encoding speeds:**
- Check if hardware acceleration is enabled
- Use faster encoding presets (may reduce quality)
- Ensure adequate cooling for sustained workloads

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Acknowledgements

- [FFmpeg](https://ffmpeg.org/) - Multimedia framework
- [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) - Python FFmpeg wrapper
- [Rich](https://github.com/Textualize/rich) - Rich text and beautiful formatting
- [GPUtil](https://github.com/anderskm/gputil) - GPU utilization library

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Support

If you encounter any issues or have questions, please open an issue on the GitHub repository.















































