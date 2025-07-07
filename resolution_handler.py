"""
Resolution handling module for video processing.
Manages target resolution settings and automatic resizing while maintaining aspect ratio.
"""

import ffmpeg
from typing import Tuple, Dict, Optional
from enum import Enum
from dataclasses import dataclass


class ResolutionPreset(Enum):
    """Predefined resolution presets"""
    HD = (1280, 720)      # 720p
    FHD = (1920, 1080)    # 1080p
    QHD = (2560, 1440)    # 1440p
    UHD = (3840, 2160)    # 4K


@dataclass
class VideoResolution:
    """Video resolution information"""
    width: int
    height: int
    
    @property
    def aspect_ratio(self) -> float:
        """Calculate aspect ratio"""
        return self.width / self.height
    
    @property
    def longest_side(self) -> int:
        """Get the longest side length"""
        return max(self.width, self.height)
    
    def __str__(self) -> str:
        return f"{self.width}x{self.height}"


class ResolutionHandler:
    """Handles video resolution processing and scaling"""
    
    def __init__(self, target_preset: ResolutionPreset = ResolutionPreset.FHD):
        self.target_preset = target_preset
        self.target_width, self.target_height = target_preset.value
        self.target_longest_side = max(self.target_width, self.target_height)
    
    def get_video_resolution(self, file_path: str) -> Optional[VideoResolution]:
        """Extract resolution from video file"""
        try:
            probe = ffmpeg.probe(file_path)
            video_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                None
            )
            
            if video_stream:
                width = int(video_stream['width'])
                height = int(video_stream['height'])
                return VideoResolution(width, height)
            
        except Exception as e:
            print(f"Error getting video resolution for {file_path}: {e}")
        
        return None
    
    def needs_resizing(self, current_resolution: VideoResolution) -> bool:
        """Check if video needs resizing based on target preset"""
        return current_resolution.longest_side > self.target_longest_side
    
    def calculate_target_resolution(self, current_resolution: VideoResolution) -> VideoResolution:
        """Calculate target resolution while maintaining aspect ratio"""
        if not self.needs_resizing(current_resolution):
            return current_resolution
        
        # Calculate scaling factor based on the longest side
        scale_factor = self.target_longest_side / current_resolution.longest_side
        
        # Calculate new dimensions
        new_width = int(current_resolution.width * scale_factor)
        new_height = int(current_resolution.height * scale_factor)
        
        # Ensure dimensions are even (required for most codecs)
        new_width = new_width - (new_width % 2)
        new_height = new_height - (new_height % 2)
        
        return VideoResolution(new_width, new_height)
    
    def get_ffmpeg_scale_filter(self, current_resolution: VideoResolution) -> Optional[str]:
        """Generate FFmpeg scale filter string"""
        target_resolution = self.calculate_target_resolution(current_resolution)
        
        if current_resolution.width == target_resolution.width and \
           current_resolution.height == target_resolution.height:
            return None  # No scaling needed
        
        return f"scale={target_resolution.width}:{target_resolution.height}"
    
    def get_resolution_info(self, file_path: str) -> Dict:
        """Get comprehensive resolution information for a file"""
        current_res = self.get_video_resolution(file_path)
        if not current_res:
            return {
                'error': 'Could not determine video resolution',
                'current': None,
                'target': None,
                'needs_resize': False,
                'scale_filter': None
            }
        
        target_res = self.calculate_target_resolution(current_res)
        needs_resize = self.needs_resizing(current_res)
        scale_filter = self.get_ffmpeg_scale_filter(current_res)
        
        return {
            'current': {
                'width': current_res.width,
                'height': current_res.height,
                'aspect_ratio': current_res.aspect_ratio,
                'longest_side': current_res.longest_side,
                'resolution_str': str(current_res)
            },
            'target': {
                'width': target_res.width,
                'height': target_res.height,
                'aspect_ratio': target_res.aspect_ratio,
                'longest_side': target_res.longest_side,
                'resolution_str': str(target_res)
            },
            'needs_resize': needs_resize,
            'scale_filter': scale_filter,
            'target_preset': self.target_preset.name,
            'scale_factor': target_res.longest_side / current_res.longest_side if needs_resize else 1.0
        }
    
    @staticmethod
    def get_available_presets() -> Dict[str, Tuple[int, int]]:
        """Get all available resolution presets"""
        return {preset.name: preset.value for preset in ResolutionPreset}
    
    @staticmethod
    def preset_from_string(preset_name: str) -> Optional[ResolutionPreset]:
        """Convert string to ResolutionPreset enum"""
        try:
            return ResolutionPreset[preset_name.upper()]
        except KeyError:
            return None
    
    def set_target_preset(self, preset: ResolutionPreset):
        """Update target resolution preset"""
        self.target_preset = preset
        self.target_width, self.target_height = preset.value
        self.target_longest_side = max(self.target_width, self.target_height)
    
    def get_preset_info(self) -> Dict:
        """Get information about current preset"""
        return {
            'name': self.target_preset.name,
            'width': self.target_width,
            'height': self.target_height,
            'longest_side': self.target_longest_side,
            'description': self._get_preset_description()
        }
    
    def _get_preset_description(self) -> str:
        """Get human-readable description of current preset"""
        descriptions = {
            ResolutionPreset.HD: "HD (720p) - 1280x720",
            ResolutionPreset.FHD: "Full HD (1080p) - 1920x1080",
            ResolutionPreset.QHD: "Quad HD (1440p) - 2560x1440",
            ResolutionPreset.UHD: "Ultra HD (4K) - 3840x2160"
        }
        return descriptions.get(self.target_preset, "Unknown")


def main():
    """Test resolution handling functionality"""
    handler = ResolutionHandler(ResolutionPreset.QHD)
    
    print("Resolution Handler Test")
    print(f"Target preset: {handler.get_preset_info()['description']}")
    print("\nAvailable presets:")
    for name, (width, height) in ResolutionHandler.get_available_presets().items():
        print(f"  {name}: {width}x{height}")
    
    # Test resolution calculations
    test_resolutions = [
        VideoResolution(1920, 1080),  # FHD
        VideoResolution(3840, 2160),  # UHD
        VideoResolution(1280, 720),   # HD
        VideoResolution(2560, 1440),  # QHD
    ]
    
    print(f"\nTesting with target preset: {handler.target_preset.name}")
    for res in test_resolutions:
        target = handler.calculate_target_resolution(res)
        needs_resize = handler.needs_resizing(res)
        scale_filter = handler.get_ffmpeg_scale_filter(res)
        
        print(f"  {res} -> {target} (resize: {needs_resize})")
        if scale_filter:
            print(f"    Scale filter: {scale_filter}")


if __name__ == "__main__":
    main()
