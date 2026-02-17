"""
Video encoder module that integrates all components for comprehensive video processing.
Handles the complete encoding pipeline with hardware detection, resolution scaling, and progress tracking.
"""

import os
import re
import sys
import time
import threading
import subprocess
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
            
            # Get video properties with retry mechanism and encoding handling
            max_retries = 3
            probe = None
            
            for attempt in range(max_retries):
                try:
                    # Use FFmpeg probe with proper encoding handling
                    probe = ffmpeg.probe(self.file_path)
                    break
                except ffmpeg.Error as e:
                    # Handle encoding errors in FFmpeg output
                    try:
                        error_msg = e.stderr.decode('utf-8', errors='replace') if e.stderr else str(e)
                    except:
                        error_msg = "FFmpeg probe error with encoding issues"
                    
                    if attempt == max_retries - 1:
                        raise Exception(f"FFmpeg probe failed: {error_msg}")
                    time.sleep(0.5)  # Wait before retry
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    time.sleep(0.5)  # Wait before retry
            
            if not probe:
                raise Exception("Failed to probe video file")
            
            # Find video stream
            video_stream = next(
                (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                None
            )
            
            if video_stream:
                # Get bitrate with fallback
                self.bitrate = video_stream.get('bit_rate')
                if not self.bitrate and 'format' in probe:
                    # Try to get bitrate from format if not available in stream
                    self.bitrate = probe['format'].get('bit_rate')
                
                # Get duration with multiple fallback methods
                self.duration = None
                duration_sources = [
                    video_stream.get('duration'),
                    probe.get('format', {}).get('duration'),
                    video_stream.get('tags', {}).get('DURATION')
                ]
                
                for duration_source in duration_sources:
                    if duration_source:
                        try:
                            # Handle both numeric and string duration formats
                            if isinstance(duration_source, str):
                                # Handle HH:MM:SS.mmm format
                                if ':' in duration_source:
                                    time_parts = duration_source.split(':')
                                    if len(time_parts) >= 3:
                                        hours = float(time_parts[0])
                                        minutes = float(time_parts[1])
                                        seconds = float(time_parts[2])
                                        self.duration = hours * 3600 + minutes * 60 + seconds
                                    else:
                                        self.duration = float(duration_source)
                                else:
                                    self.duration = float(duration_source)
                            else:
                                self.duration = float(duration_source)
                            
                            if self.duration > 0:
                                break  # Successfully got duration
                        except (ValueError, TypeError, IndexError):
                            continue
                
                # If still no duration, try to estimate from frame count and fps
                if not self.duration or self.duration <= 0:
                    try:
                        nb_frames = video_stream.get('nb_frames')
                        fps_str = video_stream.get('r_frame_rate', '0/1')
                        if nb_frames and fps_str:
                            # Parse frame rate (e.g., "30000/1001" or "30/1")
                            if '/' in fps_str:
                                num, den = fps_str.split('/')
                                fps = float(num) / float(den) if float(den) != 0 else 0
                            else:
                                fps = float(fps_str)
                            
                            if fps > 0:
                                self.duration = float(nb_frames) / fps
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass
                
                # Get codec information
                self.codec = video_stream.get('codec_name')
                
                # Get resolution
                width = int(video_stream.get('width', 0))
                height = int(video_stream.get('height', 0))
                self.resolution = f"{width}x{height}"
            
        except Exception as e:
            # Safely handle error message with potential encoding issues
            try:
                error_msg = str(e).encode('utf-8', errors='replace').decode('utf-8')
            except:
                error_msg = "Error loading file info with encoding issues"
            
            self.error = error_msg
            # Set default values for failed probe
            if not hasattr(self, 'size_bytes'):
                self.size_bytes = 0
                self.size_mb = 0.0
    
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
        
        # Graceful cancellation support
        self._cancel_event = threading.Event()
        self._cancel_listener_thread: Optional[threading.Thread] = None
        self._cancel_listener_stop = threading.Event()
        
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
    
    def _start_cancel_listener(self):
        """Start a background thread that listens for 'q' key to schedule cancellation"""
        self._cancel_event.clear()
        self._cancel_listener_stop.clear()
        
        def _listen_for_cancel():
            try:
                if sys.platform == 'win32':
                    import msvcrt
                    while not self._cancel_listener_stop.is_set():
                        if msvcrt.kbhit():
                            key = msvcrt.getch()
                            if key in (b'q', b'Q'):
                                self._cancel_event.set()
                                self.progress_display.set_cancel_scheduled(True)
                                break
                        self._cancel_listener_stop.wait(timeout=0.1)
                else:
                    import select
                    import tty
                    import termios
                    old_settings = termios.tcgetattr(sys.stdin)
                    try:
                        tty.setcbreak(sys.stdin.fileno())
                        while not self._cancel_listener_stop.is_set():
                            if select.select([sys.stdin], [], [], 0.1)[0]:
                                key = sys.stdin.read(1)
                                if key in ('q', 'Q'):
                                    self._cancel_event.set()
                                    self.progress_display.set_cancel_scheduled(True)
                                    break
                    finally:
                        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
            except Exception:
                pass  # Silently ignore listener errors
        
        self._cancel_listener_thread = threading.Thread(target=_listen_for_cancel, daemon=True)
        self._cancel_listener_thread.start()
    
    def _stop_cancel_listener(self):
        """Stop the cancel listener thread"""
        self._cancel_listener_stop.set()
        if self._cancel_listener_thread and self._cancel_listener_thread.is_alive():
            self._cancel_listener_thread.join(timeout=2.0)
        self._cancel_listener_thread = None
    
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
            # Validate input file
            if not os.path.exists(video_file.file_path):
                raise Exception(f"Input file does not exist: {video_file.file_path}")
            
            if video_file.error:
                raise Exception(f"Invalid video file: {video_file.error}")
            
            # Get resolution information with retry
            max_retries = 3
            resolution_info = None
            
            for attempt in range(max_retries):
                try:
                    resolution_info = self.resolution_handler.get_resolution_info(video_file.file_path)
                    if 'error' not in resolution_info:
                        break
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise Exception(f"Failed to get resolution info after {max_retries} attempts: {e}")
                    time.sleep(0.5)
            
            if not resolution_info or 'error' in resolution_info:
                raise Exception(resolution_info.get('error', 'Unknown resolution error'))
            
            # Generate FFmpeg parameters
            try:
                ffmpeg_params = self.encoding_config.generate_ffmpeg_params(
                    video_file.file_path,
                    output_path,
                    video_file.bitrate,
                    resolution_info.get('scale_filter')
                )
            except Exception as e:
                raise Exception(f"Failed to generate FFmpeg parameters: {e}")
            
            # Build FFmpeg command
            input_stream = ffmpeg_params['input_config']
            
            # Apply video filters and parameters
            try:
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
                
            except Exception as e:
                raise Exception(f"Failed to build FFmpeg command: {e}")
            
            # Execute encoding with progress monitoring
            try:
                if self.progress_callback:
                    # Use progress monitoring
                    self._encode_with_progress(output_stream, video_file, output_path)
                else:
                    # Standard execution with timeout
                    # Add -nostdin to prevent FFmpeg from reading keyboard input
                    output_stream = output_stream.global_args('-nostdin')
                    try:
                        output_stream.run(
                            overwrite_output=True, 
                            quiet=False, 
                            capture_stdout=True, 
                            capture_stderr=True,
                            timeout=3600  # 1 hour timeout
                        )
                    except subprocess.TimeoutExpired:
                        raise Exception("Encoding timed out after 1 hour")
                        
            except ffmpeg.Error as e:
                # Get detailed error information with safe encoding handling
                try:
                    stderr_output = e.stderr.decode('utf-8', errors='replace') if e.stderr else 'No error details available'
                except (UnicodeDecodeError, AttributeError):
                    stderr_output = 'Error details unavailable due to encoding issues'
                
                try:
                    stdout_output = e.stdout.decode('utf-8', errors='replace') if e.stdout else ''
                except (UnicodeDecodeError, AttributeError):
                    stdout_output = ''
                
                # Try to extract meaningful error message
                error_lines = stderr_output.split('\n')
                meaningful_error = None
                
                for line in error_lines:
                    try:
                        if any(keyword in line.lower() for keyword in ['error', 'failed', 'invalid', 'unsupported']):
                            meaningful_error = line.strip()
                            break
                    except (UnicodeError, AttributeError):
                        continue
                
                if not meaningful_error:
                    try:
                        meaningful_error = stderr_output.strip()[:200] + "..." if len(stderr_output) > 200 else stderr_output.strip()
                    except:
                        meaningful_error = "FFmpeg error with encoding issues in error message"
                
                raise Exception(f"FFmpeg error: {meaningful_error}")
            
            # Calculate results
            encoding_time = time.time() - encoding_start_time
            
            # Verify output file was created and is valid
            if not os.path.exists(output_path):
                raise Exception("Output file was not created")
            
            try:
                encoded_size_bytes = os.path.getsize(output_path)
                if encoded_size_bytes == 0:
                    raise Exception("Output file is empty")
                    
                encoded_size_mb = encoded_size_bytes / (1024 * 1024)
                compression_ratio = (encoded_size_mb / video_file.size_mb) * 100 if video_file.size_mb > 0 else 0
                
                # Quick validation that output file is a valid video
                try:
                    probe = ffmpeg.probe(output_path)
                    video_streams = [s for s in probe['streams'] if s['codec_type'] == 'video']
                    if not video_streams:
                        raise Exception("Output file contains no video streams")
                except Exception:
                    raise Exception("Output file is not a valid video file")
                
                result.update({
                    'success': True,
                    'encoded_size_mb': encoded_size_mb,
                    'encoding_time': encoding_time,
                    'compression_ratio': compression_ratio
                })
                
            except Exception as e:
                # Clean up invalid output file
                try:
                    os.remove(output_path)
                except:
                    pass
                raise Exception(f"Output file validation failed: {e}")
                
        except Exception as e:
            result['error'] = str(e)
            result['encoding_time'] = time.time() - encoding_start_time
            
            # Clean up failed output file
            if os.path.exists(output_path):
                try:
                    os.remove(output_path)
                except Exception as cleanup_error:
                    print(f"Warning: Could not clean up failed output file {output_path}: {cleanup_error}")
        
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
        try:
            self._start_cancel_listener()
            with self.progress_display.live_display():
                for i, video_file in enumerate(video_files, 1):
                    # Check for scheduled cancellation before starting next file
                    if self._cancel_event.is_set():
                        break
                    
                    try:
                        # Start processing display
                        self.progress_display.start_file_processing(video_file.filename, i)
                        
                        # Set up real-time progress callback for current file
                        def progress_callback(percent: float):
                            """Update progress for current file"""
                            try:
                                self.progress_display.update_file_progress(percent)
                            except Exception:
                                pass  # Don't let display errors break encoding
                        
                        # Set the callback for this file encoding
                        self.progress_callback = progress_callback
                        
                        # Encode the file
                        result = self.encode_single_file(video_file)
                        
                    except Exception as e:
                        # Handle encoding errors for individual files
                        result = {
                            'success': False,
                            'input_file': video_file.file_path,
                            'output_file': video_file.get_output_filename(),
                            'original_size_mb': video_file.size_mb,
                            'encoded_size_mb': 0.0,
                            'encoding_time': 0.0,
                            'compression_ratio': 0.0,
                            'error': str(e)
                        }
                    finally:
                        # Always clear callback after encoding
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
                    try:
                        self.progress_display.complete_file_processing(
                            video_file.filename,
                            result['success'],
                            result['original_size_mb'],
                            result['encoded_size_mb'],
                            result['encoding_time'],
                            result.get('error')
                        )
                    except Exception as e:
                        print(f"Warning: Display update failed: {e}")
                        
        except KeyboardInterrupt:
            print("\nEncoding interrupted by user")
            raise
        except Exception as e:
            print(f"\nBatch encoding error: {e}")
            raise
        finally:
            # Stop cancel listener
            self._stop_cancel_listener()
            
            # Ensure display is properly closed
            try:
                if self._cancel_event.is_set():
                    self.processing_stats['cancelled'] = True
                self.progress_display.show_final_summary()
            except Exception as e:
                print(f"Warning: Could not show final summary: {e}")
        
        return self.processing_stats
    
    def cleanup_failed_files(self):
        """Clean up files that failed to encode"""
        cleaned_count = 0
        for file_path in self.processing_stats['failed_file_paths']:
            # Try to remove any partial output files
            try:
                video_file = VideoFile(file_path)
                output_path = video_file.get_output_filename()
                if os.path.exists(output_path):
                    os.remove(output_path)
                    print(f"Cleaned up failed output: {output_path}")
                    cleaned_count += 1
            except Exception as e:
                print(f"Error cleaning up {file_path}: {e}")
        
        # Also clean up any orphaned encoded files
        try:
            if self.video_files:
                for video_file in self.video_files:
                    output_path = video_file.get_output_filename()
                    if os.path.exists(output_path):
                        # Check if the file is very small (likely incomplete)
                        file_size = os.path.getsize(output_path)
                        if file_size < 1024:  # Less than 1KB, likely incomplete
                            os.remove(output_path)
                            print(f"Cleaned up incomplete output: {output_path}")
                            cleaned_count += 1
        except Exception as e:
            print(f"Warning during cleanup: {e}")
        
        if cleaned_count > 0:
            print(f"Cleaned up {cleaned_count} failed/incomplete output files")
        else:
            print("No files needed cleanup")
    
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
        import queue
        
        # Build the FFmpeg command - use stderr progress instead of stdout
        cmd = output_stream.compile()
        
        # Remove any existing progress or stats arguments
        cmd = [arg for arg in cmd if arg not in ['-progress', 'pipe:1', '-nostats', '-stats', '-v', 'info']]
        
        # Add -nostdin to prevent FFmpeg from reading keyboard input,
        # and progress monitoring to stderr (default FFmpeg behavior)
        cmd.extend(['-nostdin', '-stats', '-loglevel', 'info'])
        
        # Thread-safe progress communication
        progress_queue = queue.Queue()
        stop_event = threading.Event()
        
        # Start FFmpeg process with non-blocking I/O and proper encoding
        try:
            # Set environment variables for proper Unicode handling
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            if os.name == 'nt':  # Windows
                env['CHCP'] = '65001'  # UTF-8 code page
            
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,  # Prevent FFmpeg from reading keyboard input
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                encoding='utf-8',  # Force UTF-8 encoding
                errors='replace',  # Replace problematic characters instead of failing
                bufsize=0,  # Unbuffered for real-time output
                env=env  # Pass environment with UTF-8 settings
            )
        except Exception as e:
            raise Exception(f"Failed to start FFmpeg process: {e}")
        
        # Validate video duration for progress calculation
        duration = video_file.duration if video_file.duration and video_file.duration > 0 else None
        if not duration:
            # Try to get duration from FFmpeg probe again
            try:
                probe = ffmpeg.probe(video_file.file_path)
                video_stream = next(
                    (stream for stream in probe['streams'] if stream['codec_type'] == 'video'),
                    None
                )
                if video_stream and 'duration' in video_stream:
                    duration = float(video_stream['duration'])
            except:
                duration = None
        
        # Progress parsing function for stderr
        def parse_progress():
            last_update_time = time.time()
            stderr_lines = []
            
            try:
                while not stop_event.is_set() and process.poll() is None:
                    try:
                        # Read stderr with timeout to avoid blocking
                        line = process.stderr.readline()
                        if not line:
                            time.sleep(0.01)
                            continue
                        
                        # Handle encoding issues safely
                        try:
                            line = line.strip()
                        except UnicodeDecodeError:
                            # Skip lines that can't be decoded properly
                            continue
                            
                        stderr_lines.append(line)  # Store for error reporting
                        
                        if not line:
                            continue
                        
                        # Parse FFmpeg progress from stderr output
                        current_time_seconds = None
                        is_progress_line = False
                        
                        # Pattern 1: Standard progress line with time= and bitrate=
                        if 'time=' in line and ('bitrate=' in line or 'fps=' in line or 'speed=' in line):
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
                        elif line.startswith('time=') or ('frame=' in line and 'time=' in line):
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
                        
                        # Update progress if we found valid time information
                        if is_progress_line and current_time_seconds is not None:
                            current_time = time.time()
                            
                            # Throttle updates to avoid overwhelming the UI
                            if current_time - last_update_time >= 0.1:
                                if duration and duration > 0:
                                    try:
                                        progress_percent = min(100.0, (current_time_seconds / duration) * 100.0)
                                        progress_queue.put(progress_percent)
                                        last_update_time = current_time
                                    except (ValueError, ZeroDivisionError, TypeError):
                                        pass
                                else:
                                    # If no duration, show indeterminate progress
                                    progress_queue.put(-1)  # Signal indeterminate progress
                                    last_update_time = current_time
                                    
                    except (UnicodeDecodeError, UnicodeError) as e:
                        # Skip problematic lines but continue processing
                        continue
                    except Exception as e:
                        # Store stderr for error reporting, but sanitize it first
                        safe_stderr = []
                        for line in stderr_lines:
                            try:
                                # Ensure line is properly encoded
                                safe_line = str(line).encode('utf-8', errors='replace').decode('utf-8')
                                safe_stderr.append(safe_line)
                            except:
                                safe_stderr.append('[Line with encoding issues]')
                        
                        progress_queue.put(('error', str(e), safe_stderr))
                        break
                        
            except Exception as e:
                # Final fallback - create safe error message
                safe_error = str(e).encode('utf-8', errors='replace').decode('utf-8')
                progress_queue.put(('error', safe_error, ['[Error reading stderr - encoding issues]']))
            finally:
                progress_queue.put('done')
        
        # Start progress monitoring thread
        progress_thread = threading.Thread(target=parse_progress)
        progress_thread.daemon = True
        progress_thread.start()
        
        # Process progress updates in main thread
        last_progress = 0
        try:
            while True:
                try:
                    # Get progress update with timeout
                    update = progress_queue.get(timeout=1.0)
                    
                    if update == 'done':
                        break
                    elif isinstance(update, tuple) and update[0] == 'error':
                        _, error_msg, stderr_lines = update
                        raise Exception(f"Progress parsing error: {error_msg}")
                    elif isinstance(update, (int, float)):
                        if update == -1:
                            # Indeterminate progress - just show that we're working
                            last_progress = min(99, last_progress + 1)
                        else:
                            last_progress = update
                        
                        # Update progress display
                        if hasattr(self, 'progress_display') and self.progress_display:
                            self.progress_display.update_file_progress(last_progress)
                        
                        # Call progress callback if provided
                        if self.progress_callback:
                            self.progress_callback(last_progress)
                    
                except queue.Empty:
                    # Check if process is still running
                    if process.poll() is not None:
                        break
                    # Show that we're still working even without updates
                    if hasattr(self, 'progress_display') and self.progress_display:
                        self.progress_display.update_file_progress(last_progress)
                        
        except Exception as e:
            # Stop progress thread and process if error occurs
            stop_event.set()
            if process.poll() is None:
                process.terminate()
                time.sleep(1)
                if process.poll() is None:
                    process.kill()
            raise e
        
        # Stop progress thread
        stop_event.set()
        
        # Wait for process to complete with timeout
        try:
            return_code = process.wait(timeout=30)  # 30 second timeout
        except subprocess.TimeoutExpired:
            # Process is taking too long, terminate it
            process.terminate()
            time.sleep(2)
            if process.poll() is None:
                process.kill()
            raise Exception("FFmpeg process timed out and was terminated")
        
        # Wait for progress thread to finish
        progress_thread.join(timeout=5.0)
        
        # Check for errors
        if return_code != 0:
            # Read any remaining stderr for error details with safe encoding
            try:
                if hasattr(process.stderr, 'read'):
                    stderr_output = process.stderr.read()
                    if stderr_output:
                        # Try to decode safely
                        if isinstance(stderr_output, bytes):
                            stderr_output = stderr_output.decode('utf-8', errors='replace')
                    else:
                        stderr_output = ""
                else:
                    stderr_output = ""
            except Exception:
                stderr_output = "Could not read error details due to encoding issues"
            
            if not stderr_output:
                stderr_output = f"FFmpeg failed with return code {return_code}"
            
            # Sanitize error message
            try:
                error_message = str(stderr_output).encode('utf-8', errors='replace').decode('utf-8')
            except:
                error_message = f"FFmpeg failed with return code {return_code} (encoding issues in error message)"
            
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
