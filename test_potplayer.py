"""
Test script for PotPlayer integration.
This script demonstrates how to use the PotPlayer integration module.
"""

import time
import sys
import os

# Add the parent directory to sys.path to import from simkl_mps
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simkl_mps.players.potplayer import PotPlayerIntegration

# This is an interactive manual verification script, exclude from automated pytest discovery
__test__ = False

def format_time(seconds):
    """Format seconds into HH:MM:SS format."""
    if seconds is None:
        return "00:00:00"
    
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def test_potplayer_integration():
    """Test the PotPlayer integration."""
    print("Testing PotPlayer Integration...")
    print("=" * 50)
    
    integration = PotPlayerIntegration()
    
    if integration.platform != 'windows':
        print("PotPlayer integration only works on Windows")
        return
    
    print(f"Platform: {integration.platform}")
    print(f"Integration name: {integration.name}")
    print()
    
    print("Starting monitoring loop...")
    print("Press Ctrl+C to stop")
    print("-" * 30)
    
    last_output = None
    error_count = 0
    success_count = 0
    
    try:
        while True:
            try:
                # Test getting position and duration
                position, duration = integration.get_position_duration()
                
                if position is not None and duration is not None:
                    # Format the output
                    pos_str = format_time(position)
                    dur_str = format_time(duration)
                    percentage = (position / duration * 100) if duration > 0 else 0
                    
                    # Test getting current file path
                    filepath = integration.get_current_filepath()
                    filename = os.path.basename(filepath) if filepath else "Unknown"
                    
                    # Test pause state
                    is_paused = integration.is_paused()
                    state = "Paused" if is_paused else "Playing" if is_paused is False else "Unknown"
                    
                    output = f"{pos_str} / {dur_str} ({percentage:.1f}%) - {filename} - {state}"
                    
                    if output != last_output:
                        print(output)
                        last_output = output
                    
                    success_count += 1
                    error_count = 0  # Reset error count on success
                    
                else:
                    error_count += 1
                    if error_count <= 3:  # Only show first few errors
                        print("PotPlayer not running or no media loaded")
                    elif error_count == 4:
                        print("(Suppressing further 'not running' messages...)")
                    
                    last_output = None
                    
            except Exception as e:
                error_count += 1
                if error_count <= 3:  # Only show first few errors
                    print(f"Error: {e}")
                elif error_count == 4:
                    print("(Suppressing further error messages...)")
                    
                last_output = None
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("Monitoring stopped")
        print(f"Successful reads: {success_count}")
        print(f"Total errors: {error_count}")

if __name__ == "__main__":
    test_potplayer_integration()
