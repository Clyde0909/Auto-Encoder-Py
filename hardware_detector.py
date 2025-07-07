"""
Hardware detection module for determining available GPU acceleration capabilities.
Detects NVIDIA CUDA, AMD VCE, and Intel QuickSync support.
"""

import subprocess
import platform
import re
from typing import Dict, List, Optional
from dataclasses import dataclass

try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False


@dataclass
class GPUInfo:
    """GPU information container"""
    name: str
    vendor: str
    memory: Optional[int] = None
    supports_nvenc: bool = False
    supports_vce: bool = False
    supports_qsv: bool = False


class HardwareDetector:
    """Detects hardware acceleration capabilities for video encoding"""
    
    def __init__(self):
        self.system = platform.system()
        self.gpus: List[GPUInfo] = []
        self.cpu_info = {}
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Main hardware detection method"""
        self._detect_gpus()
        self._detect_cpu()
        self._check_ffmpeg_encoders()
    
    def _detect_gpus(self):
        """Detect available GPUs and their capabilities"""
        if GPUTIL_AVAILABLE:
            try:
                gpu_list = GPUtil.getGPUs()
                for gpu in gpu_list:
                    gpu_info = GPUInfo(
                        name=gpu.name,
                        vendor=self._determine_vendor(gpu.name),
                        memory=gpu.memoryTotal
                    )
                    
                    # Check for specific GPU capabilities
                    if 'nvidia' in gpu.name.lower() or 'geforce' in gpu.name.lower() or 'quadro' in gpu.name.lower():
                        gpu_info.supports_nvenc = self._check_nvenc_support(gpu.name)
                    elif 'amd' in gpu.name.lower() or 'radeon' in gpu.name.lower():
                        gpu_info.supports_vce = self._check_vce_support(gpu.name)
                    elif 'intel' in gpu.name.lower():
                        gpu_info.supports_qsv = self._check_qsv_support(gpu.name)
                    
                    self.gpus.append(gpu_info)
            except Exception as e:
                print(f"Error detecting GPUs with GPUtil: {e}")
                self._fallback_gpu_detection()
        else:
            self._fallback_gpu_detection()
    
    def _fallback_gpu_detection(self):
        """Fallback GPU detection using system commands"""
        try:
            if self.system == "Windows":
                result = subprocess.run(
                    ["wmic", "path", "win32_VideoController", "get", "name"],
                    capture_output=True, text=True, check=True
                )
                gpu_names = [line.strip() for line in result.stdout.split('\n') 
                           if line.strip() and 'Name' not in line]
            else:
                result = subprocess.run(
                    ["lspci", "-nn", "|", "grep", "VGA"],
                    capture_output=True, text=True, shell=True
                )
                gpu_names = [line.strip() for line in result.stdout.split('\n') if line.strip()]
            
            for name in gpu_names:
                if name:
                    gpu_info = GPUInfo(
                        name=name,
                        vendor=self._determine_vendor(name)
                    )
                    
                    if 'nvidia' in name.lower() or 'geforce' in name.lower():
                        gpu_info.supports_nvenc = True
                    elif 'amd' in name.lower() or 'radeon' in name.lower():
                        gpu_info.supports_vce = True
                    elif 'intel' in name.lower():
                        gpu_info.supports_qsv = True
                    
                    self.gpus.append(gpu_info)
                    
        except Exception as e:
            print(f"Fallback GPU detection failed: {e}")
    
    def _detect_cpu(self):
        """Detect CPU information"""
        try:
            if self.system == "Windows":
                result = subprocess.run(
                    ["wmic", "cpu", "get", "name"],
                    capture_output=True, text=True, check=True
                )
                cpu_name = [line.strip() for line in result.stdout.split('\n') 
                          if line.strip() and 'Name' not in line][0]
            else:
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if 'model name' in line:
                            cpu_name = line.split(':')[1].strip()
                            break
            
            self.cpu_info = {
                'name': cpu_name,
                'supports_qsv': 'intel' in cpu_name.lower()
            }
        except Exception as e:
            print(f"CPU detection failed: {e}")
            self.cpu_info = {'name': 'Unknown', 'supports_qsv': False}
    
    def _determine_vendor(self, gpu_name: str) -> str:
        """Determine GPU vendor from name"""
        gpu_name_lower = gpu_name.lower()
        if 'nvidia' in gpu_name_lower or 'geforce' in gpu_name_lower or 'quadro' in gpu_name_lower:
            return 'NVIDIA'
        elif 'amd' in gpu_name_lower or 'radeon' in gpu_name_lower:
            return 'AMD'
        elif 'intel' in gpu_name_lower:
            return 'Intel'
        else:
            return 'Unknown'
    
    def _check_nvenc_support(self, gpu_name: str) -> bool:
        """Check if GPU supports NVENC"""
        # List of NVENC-capable GPU series
        nvenc_series = ['gtx 10', 'gtx 16', 'rtx', 'quadro', 'tesla', 'titan']
        gpu_name_lower = gpu_name.lower()
        return any(series in gpu_name_lower for series in nvenc_series)
    
    def _check_vce_support(self, gpu_name: str) -> bool:
        """Check if GPU supports VCE (Video Coding Engine)"""
        # Most modern AMD GPUs support VCE
        vce_series = ['rx', 'r9', 'r7', 'vega', 'navi', 'rdna']
        gpu_name_lower = gpu_name.lower()
        return any(series in gpu_name_lower for series in vce_series)
    
    def _check_qsv_support(self, gpu_name: str) -> bool:
        """Check if Intel GPU supports QuickSync"""
        # Most Intel integrated graphics support QuickSync
        return 'intel' in gpu_name.lower()
    
    def _check_ffmpeg_encoders(self):
        """Check available FFmpeg encoders"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True, text=True, check=True
            )
            encoders = result.stdout
            
            # Update GPU capabilities based on available encoders
            for gpu in self.gpus:
                if gpu.vendor == 'NVIDIA':
                    gpu.supports_nvenc = 'h264_nvenc' in encoders or 'hevc_nvenc' in encoders
                elif gpu.vendor == 'AMD':
                    gpu.supports_vce = 'h264_amf' in encoders or 'hevc_amf' in encoders
                elif gpu.vendor == 'Intel':
                    gpu.supports_qsv = 'h264_qsv' in encoders or 'hevc_qsv' in encoders
                    
        except Exception as e:
            print(f"Failed to check FFmpeg encoders: {e}")
    
    def get_recommended_encoder(self) -> Dict[str, str]:
        """Get recommended encoder settings based on hardware"""
        recommendations = {
            'hw_accel': None,
            'video_codec': 'libx265',  # Default software encoder
            'description': 'Software encoding (CPU only)'
        }
        
        # Prioritize NVIDIA > AMD > Intel for hardware acceleration
        for gpu in self.gpus:
            if gpu.vendor == 'NVIDIA' and gpu.supports_nvenc:
                recommendations.update({
                    'hw_accel': 'cuda',
                    'video_codec': 'hevc_nvenc',
                    'description': f'NVIDIA NVENC on {gpu.name}'
                })
                break
            elif gpu.vendor == 'AMD' and gpu.supports_vce:
                recommendations.update({
                    'hw_accel': 'auto',
                    'video_codec': 'hevc_amf',
                    'description': f'AMD VCE on {gpu.name}'
                })
                break
            elif gpu.vendor == 'Intel' and gpu.supports_qsv:
                recommendations.update({
                    'hw_accel': 'qsv',
                    'video_codec': 'hevc_qsv',
                    'description': f'Intel QuickSync on {gpu.name}'
                })
        
        return recommendations
    
    def get_hardware_summary(self) -> Dict:
        """Get a summary of detected hardware"""
        return {
            'system': self.system,
            'cpu': self.cpu_info,
            'gpus': [
                {
                    'name': gpu.name,
                    'vendor': gpu.vendor,
                    'memory': gpu.memory,
                    'nvenc': gpu.supports_nvenc,
                    'vce': gpu.supports_vce,
                    'qsv': gpu.supports_qsv
                }
                for gpu in self.gpus
            ],
            'recommended_encoder': self.get_recommended_encoder()
        }


def main():
    """Test hardware detection"""
    detector = HardwareDetector()
    summary = detector.get_hardware_summary()
    
    print("Hardware Detection Summary:")
    print(f"System: {summary['system']}")
    print(f"CPU: {summary['cpu']['name']}")
    print("\nGPUs:")
    for gpu in summary['gpus']:
        print(f"  - {gpu['name']} ({gpu['vendor']})")
        print(f"    NVENC: {gpu['nvenc']}, VCE: {gpu['vce']}, QSV: {gpu['qsv']}")
    
    print(f"\nRecommended Encoder: {summary['recommended_encoder']['description']}")
    print(f"Codec: {summary['recommended_encoder']['video_codec']}")


if __name__ == "__main__":
    main()
