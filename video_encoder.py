"""
Video encoder module that integrates all components for comprehensive video processing.
Handles the complete encoding pipeline with hardware detection, resolution scaling, and progress tracking.
"""

import os
import re
import time
from typing import List, Dict, Optional, Callable
from pathlib import Path
import ffmpeg

from hardware_detector import HardwareDetector
from resolution_handler import ResolutionHandler, ResolutionPreset
from encoding_config import EncodingConfigManager, EncodingMethod, VideoCodec
from progress_display import ProgressDisplay


class VideoFile:
    """Represents a video file with its properties"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.size_bytes = 0
        self.size_mb = 0.0
        self.bitrate = None
        self.duration = None
        self.resolution = None
        self.codec = None
        self.error = None
        
        self._load_file_info()
    
    def _load_file_info(self):
        """Load file information using FFmpeg probe"""
        try:
            # Get file size
            self.size_bytes = os.path.getsize(self.file_path)
            self.size_mb = self.size_bytes / (1024 * 1024)
            
            # Get video properties
            probe = ffmpeg.probe(self.file_path)
            
            # Find video stream
            video_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                None
            )
            
            if video_stream:
                self.bitrate = video_stream.get('bit_rate')
                self.duration = float(video_stream.get('duration', 0))
                self.codec = video_stream.get('codec_name')
                
                # Get resolution
                width = int(video_stream.get('width', 0))
                height = int(video_stream.get('height', 0))
                self.resolution = f"{width}x{height}"
            
        except Exception as e:
            self.error = str(e)
    
    def is_valid(self) -> bool:
        """Check if file is a valid video file"""
        return self.error is None and self.bitrate is not None
    
    def get_output_filename(self, suffix: str = "_encoded") -> str:
        """Generate output filename"""
        path = Path(self.file_path)
        return str(path.parent / f"{path.stem}{suffix}{path.suffix}")


class VideoEncoder:
    """Main video encoder class that orchestrates the encoding process"""
    
    # Supported video file extensions
    SUPPORTED_EXTENSIONS = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    
    def __init__(self, progress_callback: Optional[Callable] = None):
        self.hardware_detector = HardwareDetector()
        self.resolution_handler = ResolutionHandler()
        self.encoding_config = EncodingConfigManager()
        self.progress_display = ProgressDisplay()
        self.progress_callback = progress_callback
        
        # Session tracking
        self.video_files: List[VideoFile] = []
        self.processing_stats = {
            'total_files': 0,
            'processed_files': 0,
            'failed_files': 0,
            'total_original_size': 0.0,
            'total_encoded_size': 0.0,
            'failed_file_paths': []
        }
        
        # Apply recommended hardware settings
        self._apply_hardware_recommendations()
    
    def _apply_hardware_recommendations(self):
        """Apply recommended hardware acceleration settings"""
        recommendations = self.hardware_detector.get_recommended_encoder()
        if recommendations['hw_accel']:
            self.encoding_config.set_hardware_acceleration(
                recommendations['hw_accel'],
                recommendations['video_codec']
            )
            # Update codec type to match the recommended encoder
            if 'h264' in recommendations['video_codec']:
                self.encoding_config.set_codec_type(VideoCodec.H264, recommendations['hw_accel'])
            else:
                self.encoding_config.set_codec_type(VideoCodec.H265, recommendations['hw_accel'])
    
    def discover_video_files(self, target_directory: str, recursive: bool = True) -> List[VideoFile]:
        """Discover video files in target directory"""
        video_files = []
        target_path = Path(target_directory)
        
        if not target_path.exists():
            raise ValueError(f"Target directory does not exist: {target_directory}")
        
        # Search pattern
        if recursive:
            pattern = "**/*"
        else:
            pattern = "*"
        
        for file_path in target_path.glob(pattern):
            if (file_path.is_file() and 
                file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS and
                not re.search(r"_encoded\.", str(file_path)) and
                not re.search(r"_modified\.", str(file_path))):
                
                video_file = VideoFile(str(file_path))
                if video_file.is_valid():
                    video_files.append(video_file)
                else:
                    print(f"Warning: Skipping invalid video file: {file_path}")
        
        self.video_files = video_files
        return video_files
    
    def set_resolution_preset(self, preset: ResolutionPreset):
        """Set target resolution preset"""
        self.resolution_handler.set_target_preset(preset)
    
    def set_encoding_method(self, method: EncodingMethod, value: float, preset: str = "medium"):
        """Set encoding method and parameters"""
        if method == EncodingMethod.CRF:
            self.encoding_config.set_crf_encoding(value, preset)
        elif method == EncodingMethod.VBR:
            self.encoding_config.set_vbr_encoding(value, preset)
    
    def set_codec_type(self, codec_type: VideoCodec):
        """Set video codec type (H.264 or H.265)"""
        self.encoding_config.set_codec_type(codec_type, self.encoding_config.config.hw_accel)
    
    def encode_single_file(self, video_file: VideoFile, output_path: Optional[str] = None) -> Dict:
        """Encode a single video file"""
        if output_path is None:
            output_path = video_file.get_output_filename()
        
        encoding_start_time = time.time()
        result = {
            'success': False,
            'input_file': video_file.file_path,
            'output_file': output_path,
            'original_size_mb': video_file.size_mb,
            'encoded_size_mb': 0.0,
            'encoding_time': 0.0,
            'compression_ratio': 0.0,
            'error': None
        }
        
        try:
            # Get resolution information
            resolution_info = self.resolution_handler.get_resolution_info(video_file.file_path)
            if 'error' in resolution_info:
                raise Exception(resolution_info['error'])
            
            # Generate FFmpeg parameters
            ffmpeg_params = self.encoding_config.generate_ffmpeg_params(
                video_file.file_path,
                output_path,
                video_file.bitrate,
                resolution_info.get('scale_filter')
            )
            
            # Build FFmpeg command
            input_stream = ffmpeg_params['input_config']
            
            # Apply video filters and parameters
            output_stream = input_stream.output(
                output_path,
                **ffmpeg_params['video_params']
            )
            
            # Add global arguments
            if ffmpeg_params['global_args']:
                output_stream = output_stream.global_args(*ffmpeg_params['global_args'])
            
            # Add progress monitoring if callback is provided
            if self.progress_callback:
                # Note: Real progress monitoring would require parsing FFmpeg output
                # This is a simplified implementation
                output_stream = output_stream.global_args('-progress', 'pipe:1')
            
            # Execute encoding with progress monitoring
            try:
                if self.progress_callback:
                    # Use progress monitoring
                    self._encode_with_progress(output_stream, video_file, output_path)
                else:
                    # Standard execution
                    output_stream.run(overwrite_output=True, quiet=False, capture_stdout=True, capture_stderr=True)
            except ffmpeg.Error as e:
                # Get detailed error information
                error_msg = f"FFmpeg error: {e.stderr.decode() if e.stderr else 'Unknown error'}"
                raise Exception(error_msg)
            
            # Calculate results
            encoding_time = time.time() - encoding_start_time
            
            if os.path.exists(output_path):
                encoded_size_bytes = os.path.getsize(output_path)
                encoded_size_mb = encoded_size_bytes / (1024 * 1024)
                compression_ratio = (encoded_size_mb / video_file.size_mb) * 100 if video_file.size_mb > 0 else 0
                
                result.update({
                    'success': True,
                    'encoded_size_mb': encoded_size_mb,
                    'encoding_time': encoding_time,
                    'compression_ratio': compression_ratio
                })
            else:
                raise Exception("Output file was not created")
                
        except Exception as e:
            result['error'] = str(e)
            result['encoding_time'] = time.time() - encoding_start_time
            
            # Clean up failed output file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except:
                    pass
        
        return result
    
    def encode_batch(self, video_files: Optional[List[VideoFile]] = None, 
                    delete_originals: bool = False) -> Dict:
        """Encode a batch of video files with progress tracking"""
        if video_files is None:
            video_files = self.video_files
        
        if not video_files:
            raise ValueError("No video files to process")
        
        # Initialize progress tracking
        total_files = len(video_files)
        self.progress_display.initialize_session(total_files, [vf.filename for vf in video_files])
        
        # Reset processing stats
        self.processing_stats = {
            'total_files': total_files,
            'processed_files': 0,
            'failed_files': 0,
            'total_original_size': sum(vf.size_mb for vf in video_files),
            'total_encoded_size': 0.0,
            'failed_file_paths': []
        }
        
        # Process files with live display
        with self.progress_display.live_display():
            for i, video_file in enumerate(video_files, 1):
                # Start processing display
                self.progress_display.start_file_processing(video_file.filename, i)
                
                # Set up real-time progress callback for current file
                def progress_callback(percent: float):
                    """Update progress for current file"""
                    self.progress_display.update_file_progress(percent)
                
                # Set the callback for this file encoding
                self.progress_callback = progress_callback
                
                # Encode the file
                result = self.encode_single_file(video_file)
                
                # Clear callback after encoding
                self.progress_callback = None
                
                # Update statistics
                if result['success']:
                    self.processing_stats['processed_files'] += 1
                    self.processing_stats['total_encoded_size'] += result['encoded_size_mb']
                    
                    # Delete original if requested
                    if delete_originals:
                        try:
                            os.remove(video_file.file_path)
                        except Exception as e:
                            print(f"Warning: Could not delete original file {video_file.file_path}: {e}")
                else:
                    self.processing_stats['failed_files'] += 1
                    self.processing_stats['failed_file_paths'].append(video_file.file_path)
                
                # Complete processing display
                self.progress_display.complete_file_processing(
                    video_file.filename,
                    result['success'],
                    result['original_size_mb'],
                    result['encoded_size_mb'],
                    result['encoding_time'],
                    result.get('error')
                )
        
        # Show final summary
        self.progress_display.show_final_summary()
        
        return self.processing_stats
    
    def cleanup_failed_files(self):
        """Clean up files that failed to encode"""
        for file_path in self.processing_stats['failed_file_paths']:
            # Try to remove any partial output files
            try:
                video_file = VideoFile(file_path)
                output_path = video_file.get_output_filename()
                if os.path.exists(output_path):
                    os.remove(output_path)
                    print(f"Cleaned up failed output: {output_path}")
            except Exception as e:
                print(f"Error cleaning up {file_path}: {e}")
    
    def get_encoding_summary(self) -> Dict:
        """Get a summary of current encoding configuration"""
        hardware_summary = self.hardware_detector.get_hardware_summary()
        resolution_info = self.resolution_handler.get_preset_info()
        encoding_info = self.encoding_config.get_config_summary()
        
        return {
            'hardware': {
                'recommended_encoder': hardware_summary['recommended_encoder']['description'],
                'video_codec': hardware_summary['recommended_encoder']['video_codec'],
                'hw_acceleration': hardware_summary['recommended_encoder']['hw_accel']
            },
            'resolution': {
                'target_preset': resolution_info['name'],
                'description': resolution_info['description'],
                'max_resolution': f"{resolution_info['width']}x{resolution_info['height']}"
            },
            'encoding': {
                'method': encoding_info['method'],
                'description': encoding_info['description'],
                'codec': encoding_info['video_codec'],
                'preset': encoding_info['preset']
            },
            'session': self.processing_stats
        }
    
    def _encode_with_progress(self, output_stream, video_file: VideoFile, output_path: str):
        """Execute encoding with real-time progress monitoring"""
        import subprocess
        import re
        import threading
        import time
        
        # Build the FFmpeg command - use stderr progress instead of stdout
        cmd = output_stream.compile()
        
        # Remove any existing progress or stats arguments
        cmd = [arg for arg in cmd if arg not in ['-progress', 'pipe:1', '-nostats', '-stats', '-v', 'info']]
        
        # Add progress monitoring to stderr (default FFmpeg behavior)
        cmd.extend(['-stats'])
        
        # Start FFmpeg process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Progress parsing function for stderr
        def parse_progress():
            last_update_time = time.time()
            progress_count = 0
            lines_read = 0
            
            try:
                while True:
                    line = process.stderr.readline()
                    if not line:
                        break
                        
                    line = line.strip()
                    lines_read += 1
                    
                    if not line:
                        continue
                    
                    # Parse FFmpeg progress from stderr output
                    # Look for multiple patterns that indicate progress
                    is_progress_line = False
                    current_time_seconds = None
                    
                    # Pattern 1: Standard progress line with time= and bitrate=
                    if 'time=' in line and ('bitrate=' in line or 'fps=' in line):
                        is_progress_line = True
                        time_match = re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line)
                        if time_match:
                            try:
                                hours = int(time_match.group(1))
                                minutes = int(time_match.group(2))
                                seconds = float(time_match.group(3))
                                current_time_seconds = hours * 3600 + minutes * 60 + seconds
                            except (ValueError, IndexError):
                                pass
                    
                    # Pattern 2: Alternative format with just time=
                    elif line.startswith('time=') or 'frame=' in line:
                        is_progress_line = True
                        # Try to extract time in various formats
                        time_matches = [
                            re.search(r'time=(\d+):(\d+):(\d+\.?\d*)', line),
                            re.search(r'time=(\d+\.?\d*)', line)
                        ]
                        
                        for time_match in time_matches:
                            if time_match:
                                try:
                                    if ':' in time_match.group(0):
                                        # HH:MM:SS format
                                        hours = int(time_match.group(1))
                                        minutes = int(time_match.group(2))
                                        seconds = float(time_match.group(3))
                                        current_time_seconds = hours * 3600 + minutes * 60 + seconds
                                    else:
                                        # Seconds only
                                        current_time_seconds = float(time_match.group(1))
                                    break
                                except (ValueError, IndexError):
                                    continue
                    
                    if is_progress_line:
                        progress_count += 1
                        current_time = time.time()
                        
                        # Throttle updates to avoid overwhelming the UI
                        if current_time - last_update_time >= 0.1:
                            if current_time_seconds is not None and video_file.duration and video_file.duration > 0:
                                try:
                                    progress_percent = min(100.0, (current_time_seconds / video_file.duration) * 100.0)
                                    
                                    # Update progress display
                                    if hasattr(self, 'progress_display') and self.progress_display:
                                        self.progress_display.update_file_progress(progress_percent)
                                    
                                    # Call progress callback if provided
                                    if self.progress_callback:
                                        self.progress_callback(progress_percent)
                                    
                                    last_update_time = current_time
                                    
                                except (ValueError, ZeroDivisionError, TypeError):
                                    pass
                                
            except Exception:
                pass
        
        # Start progress monitoring thread
        progress_thread = threading.Thread(target=parse_progress)
        progress_thread.daemon = True
        progress_thread.start()
        
        # Wait for process to complete
        return_code = process.wait()
        
        # Wait for progress thread to finish
        progress_thread.join(timeout=2.0)
        
        # Check for errors
        if return_code != 0:
            # Read any remaining stderr for error details
            stderr_output = process.stderr.read() if process.stderr else ""
            error_message = stderr_output if stderr_output else f"FFmpeg failed with return code {return_code}"
            raise Exception(f"FFmpeg encoding failed: {error_message}")
        
        # Ensure progress reaches 100% on successful completion
        if self.progress_callback:
            self.progress_callback(100.0)
        if hasattr(self, 'progress_display') and self.progress_display:
            self.progress_display.update_file_progress(100.0)

def main():
    """Test video encoder functionality"""
    encoder = VideoEncoder()
    
    print("Video Encoder Test")
    print("=" * 50)
    
    # Print configuration summary
    summary = encoder.get_encoding_summary()
    print(f"Hardware: {summary['hardware']['recommended_encoder']}")
    print(f"Target Resolution: {summary['resolution']['description']}")
    print(f"Encoding Method: {summary['encoding']['description']}")
    
    # Test file discovery (using current directory for demo)
    try:
        video_files = encoder.discover_video_files(".", recursive=True)
        print(f"\nFound {len(video_files)} video files")
        
        for vf in video_files[:3]:  # Show first 3 files
            print(f"  - {vf.filename} ({vf.size_mb:.1f} MB, {vf.resolution})")
            
    except Exception as e:
        print(f"Error discovering files: {e}")


if __name__ == "__main__":
    main()
