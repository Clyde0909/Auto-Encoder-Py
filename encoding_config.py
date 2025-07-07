"""
Encoding configuration module for video processing.
Manages encoding methods: bitrate-based (VBR) and quality-based (CRF) encoding.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Any
import ffmpeg


class EncodingMethod(Enum):
    """Encoding method types"""
    VBR = "vbr"  # Variable Bitrate (bitrate-based)
    CRF = "crf"  # Constant Rate Factor (quality-based)


class VideoCodec(Enum):
    """Video codec types"""
    H264 = "h264"  # H.264/AVC
    H265 = "h265"  # H.265/HEVC


@dataclass
class EncodingConfig:
    """Encoding configuration container"""
    method: EncodingMethod
    value: float
    video_codec: str = "libx265"
    codec_type: VideoCodec = VideoCodec.H265
    hw_accel: Optional[str] = None
    preset: str = "medium"
    additional_params: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.additional_params is None:
            self.additional_params = {}


class EncodingConfigManager:
    """Manages encoding configuration and FFmpeg parameter generation"""
    
    # Quality presets for CRF encoding
    CRF_PRESETS = {
        'ultra_high': 18,   # Near lossless
        'high': 23,         # High quality
        'medium': 28,       # Balanced quality/size
        'low': 33,          # Lower quality, smaller size
        'very_low': 38      # Very low quality
    }
    
    # Bitrate multiplier presets for VBR encoding
    VBR_PRESETS = {
        'highest': 1.2,     # 120% of original bitrate
        'high': 1.0,        # 100% of original bitrate
        'medium': 0.75,     # 75% of original bitrate
        'low': 0.5,         # 50% of original bitrate
        'lowest': 0.25      # 25% of original bitrate
    }
    
    def __init__(self):
        self.config = EncodingConfig(
            method=EncodingMethod.CRF,
            value=23,  # Default CRF value
            video_codec="libx265",
            codec_type=VideoCodec.H265
        )
    
    def set_crf_encoding(self, crf_value: float, preset: str = "medium"):
        """Configure for CRF (quality-based) encoding"""
        # Validate CRF range (0-51 for x264/x265)
        crf_value = max(0, min(51, crf_value))
        
        self.config.method = EncodingMethod.CRF
        self.config.value = crf_value
        self.config.preset = preset
    
    def set_vbr_encoding(self, bitrate_multiplier: float, preset: str = "medium"):
        """Configure for VBR (bitrate-based) encoding"""
        # Validate multiplier range
        bitrate_multiplier = max(0.1, min(10.0, bitrate_multiplier))
        
        self.config.method = EncodingMethod.VBR
        self.config.value = bitrate_multiplier
        self.config.preset = preset
    
    def set_hardware_acceleration(self, hw_accel: str, video_codec: str):
        """Set hardware acceleration settings"""
        self.config.hw_accel = hw_accel
        self.config.video_codec = video_codec
    
    def set_codec_type(self, codec_type: VideoCodec, hw_accel: Optional[str] = None):
        """Set video codec type (H.264 or H.265)"""
        self.config.codec_type = codec_type
        
        # Update video codec based on hardware acceleration and codec type
        if hw_accel:
            if codec_type == VideoCodec.H264:
                if 'nvenc' in self.config.video_codec:
                    self.config.video_codec = 'h264_nvenc'
                elif 'amf' in self.config.video_codec:
                    self.config.video_codec = 'h264_amf'
                elif 'qsv' in self.config.video_codec:
                    self.config.video_codec = 'h264_qsv'
                else:
                    self.config.video_codec = 'libx264'
            else:  # H.265
                if 'nvenc' in self.config.video_codec:
                    self.config.video_codec = 'hevc_nvenc'
                elif 'amf' in self.config.video_codec:
                    self.config.video_codec = 'hevc_amf'
                elif 'qsv' in self.config.video_codec:
                    self.config.video_codec = 'hevc_qsv'
                else:
                    self.config.video_codec = 'libx265'
        else:
            # Software encoding
            if codec_type == VideoCodec.H264:
                self.config.video_codec = 'libx264'
            else:  # H.265
                self.config.video_codec = 'libx265'
    
    def get_crf_from_preset(self, preset_name: str) -> float:
        """Get CRF value from preset name"""
        return self.CRF_PRESETS.get(preset_name.lower(), 23)
    
    def get_vbr_from_preset(self, preset_name: str) -> float:
        """Get VBR multiplier from preset name"""
        return self.VBR_PRESETS.get(preset_name.lower(), 0.75)
    
    def calculate_target_bitrate(self, original_bitrate: str) -> int:
        """Calculate target bitrate for VBR encoding"""
        if self.config.method != EncodingMethod.VBR:
            raise ValueError("Can only calculate target bitrate for VBR encoding")
        
        try:
            original_bitrate_int = int(original_bitrate)
            return int(original_bitrate_int * self.config.value)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid original bitrate: {original_bitrate}")
    
    def generate_ffmpeg_params(self, input_file: str, output_file: str, 
                             original_bitrate: Optional[str] = None,
                             scale_filter: Optional[str] = None) -> Dict[str, Any]:
        """Generate FFmpeg parameters based on current configuration"""
        # Base input configuration
        input_config = ffmpeg.input(input_file)
        
        # Hardware acceleration
        global_args = []
        if self.config.hw_accel:
            global_args.extend(['-hwaccel', self.config.hw_accel])
        
        # Video encoding parameters
        video_params = {
            'vcodec': self.config.video_codec
        }
        
        # Add preset only for software encoders and some hardware encoders
        if ('amf' not in self.config.video_codec and 
            'qsv' not in self.config.video_codec):
            video_params['preset'] = self.config.preset
        
        # Method-specific parameters
        if self.config.method == EncodingMethod.CRF:
            video_params['crf'] = int(self.config.value)
        elif self.config.method == EncodingMethod.VBR:
            if original_bitrate:
                target_bitrate = self.calculate_target_bitrate(original_bitrate)
                video_params['b:v'] = f"{target_bitrate}"
            else:
                raise ValueError("Original bitrate required for VBR encoding")
        
        # Add scale filter if needed
        filter_chain = []
        if scale_filter:
            filter_chain.append(scale_filter)
        
        # Combine filters
        if filter_chain:
            video_params['vf'] = ','.join(filter_chain)
        
        # Additional codec-specific optimizations
        if 'nvenc' in self.config.video_codec:
            video_params.update(self._get_nvenc_optimizations())
        elif 'amf' in self.config.video_codec:
            video_params.update(self._get_amf_optimizations())
        elif 'qsv' in self.config.video_codec:
            video_params.update(self._get_qsv_optimizations())
        elif 'x265' in self.config.video_codec or 'libx265' in self.config.video_codec:
            video_params.update(self._get_x265_optimizations())
        
        # Add additional parameters
        video_params.update(self.config.additional_params)
        
        return {
            'input_config': input_config,
            'output_file': output_file,
            'video_params': video_params,
            'global_args': global_args
        }
    
    def _get_nvenc_optimizations(self) -> Dict[str, Any]:
        """Get NVIDIA NVENC specific optimizations"""
        return {
            'rc': 'vbr' if self.config.method == EncodingMethod.VBR else 'cqp',
            'profile:v': 'main',
            'level': '4.1',
            'b_ref_mode': 'middle',
            'spatial_aq': '1',
            'temporal_aq': '1'
        }
    
    def _get_amf_optimizations(self) -> Dict[str, Any]:
        """Get AMD AMF specific optimizations"""
        optimizations = {
            'profile:v': 'main',
            'level': '4.1'
        }
        
        # Rate control mode
        if self.config.method == EncodingMethod.VBR:
            optimizations['rc'] = 'vbr_peak'
        else:
            optimizations['rc'] = 'cqp'
        
        # Quality settings
        optimizations['quality'] = 'balanced'
        
        return optimizations
    
    def _get_qsv_optimizations(self) -> Dict[str, Any]:
        """Get Intel QuickSync specific optimizations"""
        return {
            'profile:v': 'main',
            'level': '4.1',
            'look_ahead': '1',
            'look_ahead_depth': '40'
        }
    
    def _get_x265_optimizations(self) -> Dict[str, Any]:
        """Get x265 software encoder specific optimizations"""
        return {
            'profile:v': 'main',
            'level': '4.1',
            'x265-params': 'aq-mode=3:aq-strength=0.8:deblock=1,1'
        }
    
    def get_config_summary(self) -> Dict[str, Any]:
        """Get a summary of current encoding configuration"""
        summary = {
            'method': self.config.method.value,
            'value': self.config.value,
            'video_codec': self.config.video_codec,
            'codec_type': self.config.codec_type.value,
            'codec_name': 'H.264/AVC' if self.config.codec_type == VideoCodec.H264 else 'H.265/HEVC',
            'hw_accel': self.config.hw_accel,
            'preset': self.config.preset
        }
        
        if self.config.method == EncodingMethod.CRF:
            summary['description'] = f"Quality-based encoding (CRF {self.config.value})"
            summary['quality_preset'] = self._get_crf_quality_description()
        else:
            summary['description'] = f"Bitrate-based encoding ({self.config.value}x multiplier)"
            summary['bitrate_preset'] = self._get_vbr_quality_description()
        
        return summary
    
    def _get_crf_quality_description(self) -> str:
        """Get quality description for CRF value"""
        crf = self.config.value
        if crf <= 18:
            return "Ultra High Quality (Near Lossless)"
        elif crf <= 23:
            return "High Quality"
        elif crf <= 28:
            return "Medium Quality (Balanced)"
        elif crf <= 33:
            return "Low Quality"
        else:
            return "Very Low Quality"
    
    def _get_vbr_quality_description(self) -> str:
        """Get quality description for VBR multiplier"""
        multiplier = self.config.value
        if multiplier >= 1.0:
            return "High Quality (Preserve/Increase Bitrate)"
        elif multiplier >= 0.75:
            return "Medium Quality (Moderate Compression)"
        elif multiplier >= 0.5:
            return "Low Quality (High Compression)"
        else:
            return "Very Low Quality (Maximum Compression)"
    
    @staticmethod
    def get_available_presets() -> Dict[str, Dict]:
        """Get all available quality presets"""
        return {
            'crf': {name: {'value': value, 'description': f"CRF {value}"} 
                   for name, value in EncodingConfigManager.CRF_PRESETS.items()},
            'vbr': {name: {'value': value, 'description': f"{int(value*100)}% of original"} 
                   for name, value in EncodingConfigManager.VBR_PRESETS.items()}
        }


def main():
    """Test encoding configuration functionality"""
    manager = EncodingConfigManager()
    
    print("Encoding Configuration Test")
    print("\nAvailable CRF presets:")
    for name, value in manager.CRF_PRESETS.items():
        print(f"  {name}: CRF {value}")
    
    print("\nAvailable VBR presets:")
    for name, value in manager.VBR_PRESETS.items():
        print(f"  {name}: {int(value*100)}% of original bitrate")
    
    # Test CRF configuration
    print("\n--- Testing CRF Configuration ---")
    manager.set_crf_encoding(23, "medium")
    summary = manager.get_config_summary()
    print(f"Method: {summary['description']}")
    print(f"Codec: {summary['video_codec']}")
    print(f"Quality: {summary['quality_preset']}")
    
    # Test VBR configuration
    print("\n--- Testing VBR Configuration ---")
    manager.set_vbr_encoding(0.75, "fast")
    summary = manager.get_config_summary()
    print(f"Method: {summary['description']}")
    print(f"Quality: {summary['bitrate_preset']}")
    
    # Test bitrate calculation
    original_bitrate = "5000000"  # 5 Mbps
    target_bitrate = manager.calculate_target_bitrate(original_bitrate)
    print(f"Original: {int(original_bitrate)/1000000} Mbps -> Target: {target_bitrate/1000000} Mbps")


if __name__ == "__main__":
    main()
