"""
Advanced Video Encoder Application
==================================

A comprehensive video encoding application with hardware acceleration support,
resolution scaling, and real-time progress monitoring.

Features:
- Hardware acceleration detection (NVIDIA NVENC, AMD VCE, Intel QuickSync)
- Automatic resolution scaling with aspect ratio preservation
- Multiple encoding methods (CRF quality-based, VBR bitrate-based)
- Real-time progress monitoring with rich terminal interface
- Batch processing with comprehensive statistics
"""

import os
import sys
from pathlib import Path
from typing import List, Optional

from hardware_detector import HardwareDetector
from resolution_handler import ResolutionHandler, ResolutionPreset
from encoding_config import EncodingConfigManager, EncodingMethod, VideoCodec
from video_encoder import VideoEncoder


class VideoEncoderApp:
    """Main application class for the video encoder"""
    
    def __init__(self):
        self.encoder = VideoEncoder()
        self.hardware_detector = HardwareDetector()
        
    def print_welcome_message(self):
        """Display welcome message and system information"""
        print("\n" + "="*60)
        print("ADVANCED VIDEO ENCODER")
        print("="*60)
        print("A comprehensive video encoding solution with hardware acceleration")
        print()
        
        # Display hardware information
        hardware_summary = self.hardware_detector.get_hardware_summary()
        print("System Information:")
        print(f"   OS: {hardware_summary['system']}")
        print(f"   CPU: {hardware_summary['cpu']['name']}")
        
        print("\nGraphics Hardware:")
        if hardware_summary['gpus']:
            for gpu in hardware_summary['gpus']:
                acceleration = []
                if gpu['nvenc']:
                    acceleration.append("NVENC")
                if gpu['vce']:
                    acceleration.append("VCE")
                if gpu['qsv']:
                    acceleration.append("QuickSync")
                
                accel_str = f" ({', '.join(acceleration)})" if acceleration else " (No hardware acceleration)"
                print(f"   - {gpu['name']}{accel_str}")
        else:
            print("   - No dedicated GPU detected")
        
        print(f"\nRecommended Encoder: {hardware_summary['recommended_encoder']['description']}")
        print(f"   Codec: {hardware_summary['recommended_encoder']['video_codec']}")
        print()
    
    def get_target_directory(self) -> str:
        """Get target directory from user input"""
        while True:
            target_dir = input("Enter target directory path: ").strip()
            if not target_dir:
                print("Error: Please enter a valid directory path.")
                continue
            
            # Strip surrounding quotes (users may paste paths with quotes)
            target_dir = target_dir.strip('"').strip("'")
            
            # Normalize and resolve path
            try:
                target_dir = os.path.normpath(os.path.abspath(target_dir))
            except (ValueError, OSError) as e:
                print(f"Error: Invalid path format: {e}")
                continue
            
            if not os.path.exists(target_dir):
                print(f"Error: Directory does not exist: {target_dir}")
                continue
            
            if not os.path.isdir(target_dir):
                print(f"Error: Path is not a directory: {target_dir}")
                continue
            
            # Check read permission
            if not os.access(target_dir, os.R_OK):
                print(f"Error: No read permission for directory: {target_dir}")
                continue
            
            return target_dir
    
    def select_resolution_preset(self) -> ResolutionPreset:
        """Allow user to select resolution preset"""
        print("\nSelect Maximum Resolution:")
        presets = ResolutionHandler.get_available_presets()
        
        options = []
        for i, (name, (width, height)) in enumerate(presets.items(), 1):
            description = {
                'HD': 'HD (720p)',
                'FHD': 'Full HD (1080p)',
                'QHD': 'Quad HD (1440p)',
                'UHD': 'Ultra HD (4K)'
            }.get(name, name)
            print(f"   {i}. {description} - {width}x{height}")
            options.append(name)
        
        while True:
            try:
                choice = input(f"\nSelect resolution (1-{len(options)}, default: 2 for FHD): ").strip()
                if not choice:
                    choice = "2"
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(options):
                    preset_name = options[choice_idx]
                    return ResolutionPreset[preset_name]
                else:
                    print(f"Please enter a number between 1 and {len(options)}")
            except ValueError:
                print("Please enter a valid number")
    
    def select_encoding_method(self) -> tuple:
        """Allow user to select encoding method"""
        print("\nSelect Encoding Method:")
        print("   1. CRF (Quality-based) - Recommended for most users")
        print("   2. VBR (Bitrate-based) - For specific bitrate targets")
        
        while True:
            method_choice = input("\nSelect encoding method (1-2, default: 1): ").strip()
            if not method_choice:
                method_choice = "1"
            
            if method_choice == "1":
                return self._configure_crf_encoding()
            elif method_choice == "2":
                return self._configure_vbr_encoding()
            else:
                print("Please enter 1 or 2")
    
    def select_codec_type(self) -> VideoCodec:
        """Allow user to select video codec"""
        print("\nSelect Video Codec:")
        print("   1. H.265/HEVC - Better compression, newer standard (default)")
        print("   2. H.264/AVC - Better compatibility, older standard")
        
        while True:
            codec_choice = input("\nSelect codec (1-2, default: 1): ").strip()
            if not codec_choice:
                codec_choice = "1"
            
            if codec_choice == "1":
                return VideoCodec.H265
            elif codec_choice == "2":
                return VideoCodec.H264
            else:
                print("Please enter 1 or 2")
    
    def _configure_crf_encoding(self) -> tuple:
        """Configure CRF encoding parameters"""
        print("\nCRF Quality Presets:")
        presets = EncodingConfigManager.CRF_PRESETS
        
        options = []
        for i, (name, value) in enumerate(presets.items(), 1):
            description = {
                'ultra_high': 'Ultra High (Near Lossless)',
                'high': 'High Quality',
                'medium': 'Medium Quality (Balanced)',
                'low': 'Low Quality (Smaller Size)',
                'very_low': 'Very Low Quality'
            }.get(name, name.title())
            print(f"   {i}. {description} - CRF {value}")
            options.append((name, value))
        
        print(f"   {len(options)+1}. Custom CRF value (0-51)")
        
        while True:
            try:
                choice = input(f"\nSelect quality preset (1-{len(options)+1}, default: 3): ").strip()
                if not choice:
                    choice = "3"
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(options):
                    name, value = options[choice_idx]
                    return (EncodingMethod.CRF, value, "medium")
                elif choice_idx == len(options):
                    # Custom CRF value
                    while True:
                        try:
                            custom_crf = float(input("Enter custom CRF value (0-51, lower=higher quality): "))
                            if 0 <= custom_crf <= 51:
                                return (EncodingMethod.CRF, custom_crf, "medium")
                            else:
                                print("CRF value must be between 0 and 51")
                        except ValueError:
                            print("Please enter a valid number")
                else:
                    print(f"Please enter a number between 1 and {len(options)+1}")
            except ValueError:
                print("Please enter a valid number")
    
    def _configure_vbr_encoding(self) -> tuple:
        """Configure VBR encoding parameters"""
        print("\nVBR Bitrate Presets:")
        presets = EncodingConfigManager.VBR_PRESETS
        
        options = []
        for i, (name, value) in enumerate(presets.items(), 1):
            description = {
                'highest': 'Highest Quality',
                'high': 'High Quality',
                'medium': 'Medium Quality',
                'low': 'Low Quality',
                'lowest': 'Lowest Quality'
            }.get(name, name.title())
            print(f"   {i}. {description} - {int(value*100)}% of original bitrate")
            options.append((name, value))
        
        print(f"   {len(options)+1}. Custom multiplier")
        
        while True:
            try:
                choice = input(f"\nSelect bitrate preset (1-{len(options)+1}, default: 3): ").strip()
                if not choice:
                    choice = "3"
                
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(options):
                    name, value = options[choice_idx]
                    return (EncodingMethod.VBR, value, "medium")
                elif choice_idx == len(options):
                    # Custom multiplier
                    while True:
                        try:
                            custom_mult = float(input("Enter custom bitrate multiplier (0.1-10.0): "))
                            if 0.1 <= custom_mult <= 10.0:
                                return (EncodingMethod.VBR, custom_mult, "medium")
                            else:
                                print("Multiplier must be between 0.1 and 10.0")
                        except ValueError:
                            print("Please enter a valid number")
                else:
                    print(f"Please enter a number between 1 and {len(options)+1}")
            except ValueError:
                print("Please enter a valid number")
    
    @staticmethod
    def _ask_yes_no(prompt: str, default: Optional[str] = None) -> bool:
        """Ask a yes/no question with input validation.
        
        Args:
            prompt: The question to display.
            default: Default value ('y' or 'n'). If None, no default is applied.
        
        Returns:
            True for yes, False for no.
        """
        while True:
            answer = input(prompt).strip().lower()
            if not answer and default is not None:
                return default == 'y'
            if answer in ('y', 'yes'):
                return True
            elif answer in ('n', 'no'):
                return False
            else:
                print("Invalid input. Please enter 'y' or 'n'.")
    
    def get_processing_options(self) -> dict:
        """Get additional processing options"""
        print("\nProcessing Options:")
        
        # Recursive directory search
        recursive = self._ask_yes_no(
            "Search subdirectories recursively? (y/n, default: y): ", default='y'
        )
        
        # Delete original files
        delete_originals = self._ask_yes_no(
            "Delete original files after successful encoding? (y/n, default: n): ", default='n'
        )
        
        if delete_originals:
            delete_originals = self._ask_yes_no(
                "Are you sure you want to delete original files? This cannot be undone! (y/n): "
            )
        
        return {
            'recursive': recursive,
            'delete_originals': delete_originals
        }
    
    def run(self):
        """Main application loop"""
        try:
            # Welcome message
            self.print_welcome_message()
            
            # Get target directory
            target_directory = self.get_target_directory()
            
            # Select resolution preset
            resolution_preset = self.select_resolution_preset()
            self.encoder.set_resolution_preset(resolution_preset)
            
            # Select video codec
            codec_type = self.select_codec_type()
            self.encoder.set_codec_type(codec_type)
            
            # Select encoding method
            encoding_method, value, preset = self.select_encoding_method()
            self.encoder.set_encoding_method(encoding_method, value, preset)
            
            # Get processing options
            options = self.get_processing_options()
            
            # Discover video files
            print(f"\nDiscovering video files in: {target_directory}")
            video_files = self.encoder.discover_video_files(target_directory, options['recursive'])
            
            if not video_files:
                print("No video files found in the specified directory")
                return
            
            print(f"Found {len(video_files)} video files")
            
            # Show configuration summary
            self._show_configuration_summary()
            
            # Confirm processing
            if not self._confirm_processing(video_files):
                print("Processing cancelled by user")
                return
            
            # Process files
            print("\nStarting encoding process...")
            try:
                results = self.encoder.encode_batch(video_files, options['delete_originals'])
            except KeyboardInterrupt:
                print("\nEncoding interrupted by user")
                return
            
            # Clean up failed files
            if results['failed_files'] > 0:
                try:
                    if self._ask_yes_no(
                        f"\nClean up {results['failed_files']} failed output files? (y/n, default: y): ",
                        default='y'
                    ):
                        self.encoder.cleanup_failed_files()
                except KeyboardInterrupt:
                    print("\nCleanup cancelled by user")
            
            print("\nEncoding process completed!")
            
        except KeyboardInterrupt:
            print("\nProcess interrupted by user")
            # Attempt graceful cleanup
            try:
                print("Cleaning up partial files...")
                self.encoder.cleanup_failed_files()
            except:
                pass
        except Exception as e:
            print(f"\nAn error occurred: {e}")
            import traceback
            traceback.print_exc()
            # Attempt cleanup on error
            try:
                print("Attempting to clean up partial files...")
                self.encoder.cleanup_failed_files()
            except:
                pass
    
    def _show_configuration_summary(self):
        """Display configuration summary"""
        summary = self.encoder.get_encoding_summary()
        
        print("\nConfiguration Summary:")
        print(f"   Hardware Acceleration: {summary['hardware']['recommended_encoder']}")
        print(f"   Video Codec: {summary['encoding']['codec']}")
        print(f"   Target Resolution: {summary['resolution']['description']}")
        print(f"   Encoding Method: {summary['encoding']['description']}")
        print(f"   Encoding Preset: {summary['encoding']['preset']}")
    
    def _confirm_processing(self, video_files: List) -> bool:
        """Confirm processing with user"""
        # Calculate total size
        total_size_mb = sum(vf.size_mb for vf in video_files)
        total_size_gb = total_size_mb / 1024
        
        print(f"\nProcessing Summary:")
        print(f"   Files to process: {len(video_files)}")
        print(f"   Total size: {total_size_mb:.1f} MB ({total_size_gb:.2f} GB)")
        
        # Show first few files
        print(f"\nFiles to process (showing first 5):")
        for i, vf in enumerate(video_files[:5], 1):
            print(f"   {i}. {vf.filename} ({vf.size_mb:.1f} MB, {vf.resolution})")
        
        if len(video_files) > 5:
            print(f"   ... and {len(video_files) - 5} more files")
        
        while True:
            confirm = input(f"\nStart processing {len(video_files)} files? (y/n): ").strip().lower()
            if confirm in ['y', 'yes']:
                return True
            elif confirm in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' or 'n'")


def main():
    """Main application entry point"""
    app = VideoEncoderApp()
    app.run()


if __name__ == "__main__":
    main()
