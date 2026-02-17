"""
Progress display module providing real-time responsive shell interface.
Uses Rich library for beautiful progress bars and status updates.
"""

import time
import threading
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from contextlib import contextmanager

try:
    from rich.console import Console
    from rich.progress import (
        Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn,
        TimeElapsedColumn, MofNCompleteColumn, SpinnerColumn
    )
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.columns import Columns
    from rich import box
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


@dataclass
class FileProcessingStats:
    """Statistics for file processing"""
    filename: str
    original_size_mb: float = 0.0
    encoded_size_mb: float = 0.0
    original_bitrate: int = 0
    target_bitrate: int = 0
    encoding_time: float = 0.0
    compression_ratio: float = 0.0
    status: str = "pending"
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class SessionStats:
    """Overall session statistics"""
    total_files: int = 0
    completed_files: int = 0
    failed_files: int = 0
    total_original_size_mb: float = 0.0
    total_encoded_size_mb: float = 0.0
    total_encoding_time: float = 0.0
    session_start: datetime = field(default_factory=datetime.now)
    current_file: Optional[str] = None
    estimated_time_remaining: Optional[timedelta] = None


class ProgressDisplay:
    """Rich-based progress display for video encoding"""
    
    def __init__(self, use_rich: bool = True):
        self.use_rich = use_rich and RICH_AVAILABLE
        self.console = Console() if self.use_rich else None
        self.progress = None
        self.live = None
        self.layout = None
        
        # Progress tracking
        self.overall_task_id = None  # Optional[TaskID]
        self.current_task_id = None  # Optional[TaskID]
        self.file_stats: List[FileProcessingStats] = []
        self.session_stats = SessionStats()
        
        # Threading
        self._stop_event = threading.Event()
        self._update_thread: Optional[threading.Thread] = None
        self._overall_task_created = False
        
        # Cancellation
        self._cancel_scheduled = False
        
    def set_cancel_scheduled(self, value: bool):
        """Set cancel scheduled state"""
        self._cancel_scheduled = value
    
    def initialize_session(self, total_files: int, file_list: List[str]):
        """Initialize the progress session"""
        self.session_stats.total_files = total_files
        self.session_stats.session_start = datetime.now()
        
        # Initialize file stats with safe filename handling
        self.file_stats = []
        for filename in file_list:
            try:
                safe_filename = str(filename).encode('utf-8', errors='replace').decode('utf-8')
            except:
                safe_filename = f"File_{len(self.file_stats)+1}"
            
            self.file_stats.append(FileProcessingStats(filename=safe_filename))
        
        if self.use_rich:
            self._setup_rich_display()
        else:
            self._setup_simple_display()
    
    def _setup_rich_display(self):
        """Setup Rich-based display"""
        # Create progress bars
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TimeElapsedColumn(),
            TextColumn("•"),
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        # Create layout
        self.layout = Layout()
        self.layout.split(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=10)
        )
        
        # Add overall progress task
        self.overall_task_id = self.progress.add_task(
            "Overall Progress", total=self.session_stats.total_files
        )
    
    def _setup_simple_display(self):
        """Setup simple text-based display"""
        print(f"Starting encoding session: {self.session_stats.total_files} files")
        print("Press 'q' to cancel after the current file finishes.")
        print("-" * 50)
    
    @contextmanager
    def live_display(self):
        """Context manager for live display"""
        if self.use_rich:
            with Live(self.layout, console=self.console, refresh_per_second=2) as live:
                self.live = live
                self._start_update_thread()
                try:
                    yield
                finally:
                    self._stop_update_thread()
        else:
            yield
    
    def _start_update_thread(self):
        """Start the display update thread"""
        self._stop_event.clear()
        self._update_thread = threading.Thread(target=self._update_display_loop)
        self._update_thread.daemon = True
        self._update_thread.start()
    
    def _stop_update_thread(self):
        """Stop the display update thread"""
        if self._update_thread:
            self._stop_event.set()
            # Give thread more time to finish gracefully
            self._update_thread.join(timeout=5.0)
            if self._update_thread.is_alive():
                print("Warning: Display update thread did not terminate cleanly")
            self._update_thread = None
    
    def _update_display_loop(self):
        """Main display update loop"""
        while not self._stop_event.is_set():
            if self.use_rich and self.live:
                self._update_rich_layout()
            time.sleep(0.25)
    
    def _update_rich_layout(self):
        """Update the Rich layout"""
        # Header
        if self._cancel_scheduled:
            header_text = Text(
                "⚠ Cancellation scheduled - finishing current file...",
                style="bold yellow"
            )
        else:
            header_text = Text(
                f"Video Encoder - Session started at {self.session_stats.session_start.strftime('%H:%M:%S')}  |  Press 'q' to cancel after current file",
                style="bold magenta"
            )
        self.layout["header"].update(Panel(header_text, box=box.ROUNDED))
        
        # Main progress area
        self.layout["main"].update(Panel(self.progress, title="Progress", box=box.ROUNDED))
        
        # Footer with statistics
        stats_columns = self._create_stats_columns()
        self.layout["footer"].update(Panel(stats_columns, title="Statistics", box=box.ROUNDED))
    
    def _create_stats_columns(self):
        """Create side-by-side statistics columns"""
        left_table = self._create_session_stats_table()
        right_table = self._create_size_stats_table()
        return Columns([left_table, right_table], expand=True, equal=True)
    
    def _create_session_stats_table(self) -> Table:
        """Create session statistics table (left side)"""
        table = Table(show_header=True, header_style="bold cyan", expand=True, title="Session")
        table.add_column("Metric", style="white")
        table.add_column("Value", style="green")
        
        # Calculate statistics
        completed = self.session_stats.completed_files
        failed = self.session_stats.failed_files
        total = self.session_stats.total_files
        
        # Time calculations
        elapsed = datetime.now() - self.session_stats.session_start
        avg_time_per_file = (elapsed.total_seconds() / completed) if completed > 0 else 0
        remaining_files = total - completed - failed
        estimated_remaining = timedelta(seconds=avg_time_per_file * remaining_files) if avg_time_per_file > 0 else None
        
        # Size calculations
        total_original = self.session_stats.total_original_size_mb
        total_encoded = self.session_stats.total_encoded_size_mb
        
        # Add rows
        table.add_row("Progress", f"{completed}/{total} files completed")
        table.add_row("Success Rate", f"{completed}/{completed + failed} - {completed / (completed + failed) * 100:.1f}%" if (completed + failed) > 0 else "0/0 - 0.0%")
        table.add_row("Files Failed", str(failed))
        table.add_row("Current File", self.session_stats.current_file or "None")
        if self._cancel_scheduled:
            table.add_row("Status", "[bold yellow]Cancellation scheduled[/bold yellow]")
        table.add_row("Elapsed Time", str(elapsed).split('.')[0])
        if estimated_remaining:
            table.add_row("Est. Remaining", str(estimated_remaining).split('.')[0])
        
        return table
    
    def _create_size_stats_table(self) -> Table:
        """Create size/compression statistics table (right side)"""
        table = Table(show_header=True, header_style="bold cyan", expand=True, title="Size")
        table.add_column("Metric", style="white")
        table.add_column("Value", style="green")
        
        total_original = self.session_stats.total_original_size_mb
        total_encoded = self.session_stats.total_encoded_size_mb
        compression_ratio = (total_encoded / total_original * 100) if total_original > 0 else 0
        reduction = 100 - compression_ratio if total_original > 0 else 0
        saved_mb = total_original - total_encoded if total_original > 0 else 0
        
        table.add_row("Total Original", f"{total_original:.1f} MB")
        table.add_row("Total Encoded", f"{total_encoded:.1f} MB")
        if total_original > 0:
            reduction_style = "green" if reduction > 0 else "red"
            table.add_row("Reduction", f"[{reduction_style}]{reduction:.1f}% ({saved_mb:.1f} MB saved)[/{reduction_style}]")
        else:
            table.add_row("Reduction", "-")
        
        return table
    
    def start_file_processing(self, filename: str, file_index: int):
        """Start processing a new file"""
        # Safely handle filename encoding
        try:
            safe_filename = str(filename).encode('utf-8', errors='replace').decode('utf-8')
        except:
            safe_filename = f"File_{file_index}"
        
        self.session_stats.current_file = safe_filename
        
        # Find the file stats
        file_stat = next((fs for fs in self.file_stats if fs.filename == filename), None)
        if file_stat:
            file_stat.status = "processing"
            file_stat.start_time = datetime.now()
        
        if self.use_rich and self.progress:
            # Update current file task
            if self.current_task_id:
                self.progress.remove_task(self.current_task_id)
            
            self.current_task_id = self.progress.add_task(
                f"Encoding: {safe_filename}", total=100
            )
            
            # Update overall progress description to show which file we're on
            if self.overall_task_id is not None:
                overall_description = f"Overall Progress"
                self.progress.update(
                    self.overall_task_id,
                    description=overall_description
                )
        else:
            print(f"\n[{file_index}/{self.session_stats.total_files}] Processing: {safe_filename}")
    
    def update_file_progress(self, progress_percent: float):
        """Update current file progress"""
        try:
            if self.use_rich and self.progress and self.current_task_id:
                # Clamp progress to valid range
                progress_percent = max(0.0, min(100.0, progress_percent))
                self.progress.update(self.current_task_id, completed=progress_percent)
        except Exception:
            # Silently ignore progress update errors to prevent breaking encoding
            pass
    
    def complete_file_processing(self, filename: str, success: bool, 
                               original_size_mb: float = 0, encoded_size_mb: float = 0,
                               encoding_time: float = 0, error_message: Optional[str] = None):
        """Complete file processing"""
        # Safely handle filename and error message encoding
        try:
            safe_filename = str(filename).encode('utf-8', errors='replace').decode('utf-8')
        except:
            safe_filename = "[Filename with encoding issues]"
        
        if error_message:
            try:
                safe_error_message = str(error_message).encode('utf-8', errors='replace').decode('utf-8')
            except:
                safe_error_message = "Error message with encoding issues"
        else:
            safe_error_message = None
        
        # Update file stats
        file_stat = next((fs for fs in self.file_stats if fs.filename == filename), None)
        if file_stat:
            file_stat.status = "completed" if success else "failed"
            file_stat.end_time = datetime.now()
            file_stat.original_size_mb = original_size_mb
            file_stat.encoded_size_mb = encoded_size_mb
            file_stat.encoding_time = encoding_time
            file_stat.error_message = safe_error_message
            
            if success and original_size_mb > 0:
                file_stat.compression_ratio = (encoded_size_mb / original_size_mb) * 100
        
        # Update session stats
        if success:
            self.session_stats.completed_files += 1
            self.session_stats.total_original_size_mb += original_size_mb
            self.session_stats.total_encoded_size_mb += encoded_size_mb
        else:
            self.session_stats.failed_files += 1
        
        self.session_stats.total_encoding_time += encoding_time
        
        if self.use_rich and self.progress:
            # Complete current file task
            if self.current_task_id:
                self.progress.update(self.current_task_id, completed=100)
                self.progress.remove_task(self.current_task_id)
                self.current_task_id = None
            
            # Update overall progress
            if self.overall_task_id is not None: # overall_task_id is '0' but python considers it as False, so use is not None
                completed = self.session_stats.completed_files + self.session_stats.failed_files
                
                # Update the description to show current progress manually
                overall_description = f"Overall Progress"
                
                # Ensure values are integers
                completed = int(completed)
                total = int(self.session_stats.total_files)
                
                self.progress.update(
                    self.overall_task_id,
                    completed=completed,
                    total=total,
                    description=overall_description
                )
                
                # Additional force refresh
                self.progress.refresh()
                if self.live:
                    self.live.refresh()
        else:
            status = "✓ SUCCESS" if success else "✗ FAILED"
            print(f"  {status}: {safe_filename}")
            if safe_error_message:
                print(f"    Error: {safe_error_message}")
            if success:
                compression = (encoded_size_mb / original_size_mb * 100) if original_size_mb > 0 else 0
                print(f"    Size: {original_size_mb:.1f}MB → {encoded_size_mb:.1f}MB ({compression:.1f}%)")
                print(f"    Time: {encoding_time:.1f}s")
    
    def show_final_summary(self):
        """Show final session summary"""
        if self.use_rich:
            self._show_rich_summary()
        else:
            self._show_simple_summary()
    
    def _show_rich_summary(self):
        """Show Rich-based final summary"""
        title = "Encoding Session Summary"
        if self._cancel_scheduled:
            title += " (Cancelled by user)"
        summary_table = Table(title=title, show_header=True, header_style="bold cyan")
        summary_table.add_column("Metric", style="white")
        summary_table.add_column("Value", style="green")
        
        total_time = datetime.now() - self.session_stats.session_start
        
        summary_table.add_row("Total Files", str(self.session_stats.total_files))
        summary_table.add_row("Successfully Encoded", str(self.session_stats.completed_files))
        summary_table.add_row("Failed", str(self.session_stats.failed_files))
        if self._cancel_scheduled:
            skipped = self.session_stats.total_files - self.session_stats.completed_files - self.session_stats.failed_files
            summary_table.add_row("Skipped (Cancelled)", f"[yellow]{skipped}[/yellow]")
        summary_table.add_row("Total Time", str(total_time).split('.')[0])
        summary_table.add_row("Original Total Size", f"{self.session_stats.total_original_size_mb:.1f} MB")
        summary_table.add_row("Encoded Total Size", f"{self.session_stats.total_encoded_size_mb:.1f} MB")
        
        if self.session_stats.total_original_size_mb > 0:
            compression = (self.session_stats.total_encoded_size_mb / self.session_stats.total_original_size_mb) * 100
            space_saved = self.session_stats.total_original_size_mb - self.session_stats.total_encoded_size_mb
            summary_table.add_row("Overall Compression", f"{compression:.1f}%")
            summary_table.add_row("Space Saved", f"{space_saved:.1f} MB")
        
        self.console.print("\n")
        self.console.print(Panel(summary_table, box=box.ROUNDED))
        
        # Show failed files if any
        if self.session_stats.failed_files > 0:
            failed_files = [fs for fs in self.file_stats if fs.status == "failed"]
            if failed_files:
                self.console.print("\n[bold red]Failed Files:[/bold red]")
                for fs in failed_files:
                    self.console.print(f"  • {fs.filename}: {fs.error_message or 'Unknown error'}")
    
    def _show_simple_summary(self):
        """Show simple text-based final summary"""
        print("\n" + "="*60)
        if self._cancel_scheduled:
            print("ENCODING SESSION SUMMARY (Cancelled by user)")
        else:
            print("ENCODING SESSION SUMMARY")
        print("="*60)
        
        total_time = datetime.now() - self.session_stats.session_start
        
        print(f"Total Files: {self.session_stats.total_files}")
        print(f"Successfully Encoded: {self.session_stats.completed_files}")
        print(f"Failed: {self.session_stats.failed_files}")
        if self._cancel_scheduled:
            skipped = self.session_stats.total_files - self.session_stats.completed_files - self.session_stats.failed_files
            print(f"Skipped (Cancelled): {skipped}")
        print(f"Total Time: {total_time}")
        print(f"Original Total Size: {self.session_stats.total_original_size_mb:.1f} MB")
        print(f"Encoded Total Size: {self.session_stats.total_encoded_size_mb:.1f} MB")
        
        if self.session_stats.total_original_size_mb > 0:
            compression = (self.session_stats.total_encoded_size_mb / self.session_stats.total_original_size_mb) * 100
            space_saved = self.session_stats.total_original_size_mb - self.session_stats.total_encoded_size_mb
            print(f"Overall Compression: {compression:.1f}%")
            print(f"Space Saved: {space_saved:.1f} MB")
        
        # Show failed files if any
        if self.session_stats.failed_files > 0:
            print(f"\nFailed Files:")
            failed_files = [fs for fs in self.file_stats if fs.status == "failed"]
            for fs in failed_files:
                print(f"  - {fs.filename}: {fs.error_message or 'Unknown error'}")


def main():
    """Test progress display functionality"""
    import random
    
    display = ProgressDisplay()
    
    # Simulate file list
    file_list = [f"video_{i:03d}.mp4" for i in range(1, 6)]
    display.initialize_session(len(file_list), file_list)
    
    with display.live_display():
        for i, filename in enumerate(file_list, 1):
            display.start_file_processing(filename, i)
            
            # Simulate encoding progress
            for progress in range(0, 101, 10):
                display.update_file_progress(progress)
                time.sleep(0.2)
            
            # Simulate completion
            success = random.choice([True, True, True, False])  # 75% success rate
            if success:
                display.complete_file_processing(
                    filename, True, 
                    original_size_mb=random.uniform(50, 200),
                    encoded_size_mb=random.uniform(30, 150),
                    encoding_time=random.uniform(10, 60)
                )
            else:
                display.complete_file_processing(
                    filename, False,
                    error_message="Simulated encoding error"
                )
    
    display.show_final_summary()


if __name__ == "__main__":
    main()
