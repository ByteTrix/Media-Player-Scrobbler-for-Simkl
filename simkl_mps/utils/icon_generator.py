"""
Icon generator utility for SIMKL Media Player Scrobbler.
Converts the PNG logo into appropriate formats for the tray icon.
"""

import os
import sys
import logging
from pathlib import Path
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

def generate_icons(base_size=128, output_dir=None, source_file=None):
    """
    Generate various icon formats from the source PNG file.
    
    Args:
        base_size: Base size for the icon (default: 128)
        output_dir: Directory to save the generated icons
        source_file: Source PNG file path
    
    Returns:
        Dictionary of paths to the generated icons
    """
    try:
        script_dir = Path(__file__).parent.parent
        if source_file is None:
            source_file = script_dir / "assets" / "simkl-mps.png"
        if output_dir is None:
            output_dir = script_dir / "assets"
            
        os.makedirs(output_dir, exist_ok=True)
        
        if not os.path.exists(source_file):
            logger.error(f"Source file not found: {source_file}")
            return None
            
        img = Image.open(source_file)
        img = img.convert("RGBA")
        
        icon_sizes = [16, 24, 32, 48, 64, 128, 256]
        icons = {}
        
        for size in icon_sizes:
            resized = img.resize((size, size), Image.LANCZOS)
            output_path = output_dir / f"simkl-mps-{size}.png"
            resized.save(output_path)
            icons[f"{size}"] = output_path
            
        ico_path = output_dir / "simkl-mps.ico"
        img.save(ico_path, format="ICO", sizes=[(s, s) for s in icon_sizes])
        icons["ico"] = ico_path
            
        status_colors = {
            "running": (34, 177, 76, 255),  # Green
            "paused": (255, 127, 39, 255),  # Orange
            "error": (237, 28, 36, 255),    # Red
            "stopped": (112, 146, 190, 255) # Blue
        }
        
        for status, color in status_colors.items():
            base_with_status = img.copy().resize((base_size, base_size), Image.LANCZOS)
            draw = ImageDraw.Draw(base_with_status)
            
            indicator_size = base_size // 3
            ring_color = tuple(int(c * 0.8) for c in color[:3]) + (255,)
            
            if status == "paused":
                padding = indicator_size // 4
                bar_width = (indicator_size - (padding * 3)) // 2
                
                draw.ellipse(
                    [(base_size - indicator_size, base_size - indicator_size), 
                     (base_size, base_size)],
                    fill=color,
                    outline=ring_color,
                    width=max(1, indicator_size // 10)
                )
                
                bar_color = (255, 255, 255, 220)
                
                draw.rectangle(
                    [(base_size - indicator_size + padding, 
                      base_size - indicator_size + padding),
                     (base_size - indicator_size + padding + bar_width,
                      base_size - padding)],
                    fill=bar_color
                )
                
                draw.rectangle(
                    [(base_size - indicator_size + padding * 2 + bar_width, 
                      base_size - indicator_size + padding),
                     (base_size - indicator_size + padding * 2 + bar_width * 2,
                      base_size - padding)],
                    fill=bar_color
                )
                
            elif status == "running":
                draw.ellipse(
                    [(base_size - indicator_size, base_size - indicator_size), 
                     (base_size, base_size)],
                    fill=color,
                    outline=ring_color,
                    width=max(1, indicator_size // 10)
                )
                
                triangle_color = (255, 255, 255, 220)
                padding = indicator_size // 4
                
                center_x = base_size - indicator_size // 2
                center_y = base_size - indicator_size // 2
                triangle_size = indicator_size // 2 - padding
                
                draw.polygon(
                    [(center_x - triangle_size // 2, center_y - triangle_size),
                     (center_x - triangle_size // 2, center_y + triangle_size),
                     (center_x + triangle_size, center_y)],
                    fill=triangle_color
                )
                
            elif status == "error":
                draw.ellipse(
                    [(base_size - indicator_size, base_size - indicator_size), 
                     (base_size, base_size)],
                    fill=color,
                    outline=ring_color,
                    width=max(1, indicator_size // 10)
                )
                
                x_color = (255, 255, 255, 220)
                padding = indicator_size // 3
                line_width = max(2, indicator_size // 12)
                
                x1 = base_size - indicator_size + padding
                y1 = base_size - indicator_size + padding
                x2 = base_size - padding
                y2 = base_size - padding
                
                draw.line([(x1, y1), (x2, y2)], fill=x_color, width=line_width)
                draw.line([(x1, y2), (x2, y1)], fill=x_color, width=line_width)
                
            else:
                draw.ellipse(
                    [(base_size - indicator_size, base_size - indicator_size), 
                     (base_size, base_size)],
                    fill=color,
                    outline=ring_color,
                    width=max(1, indicator_size // 10)
                )
                
                if status == "stopped":
                    stop_color = (255, 255, 255, 220)
                    padding = indicator_size // 3
                    
                    draw.rectangle(
                        [(base_size - indicator_size + padding, 
                          base_size - indicator_size + padding),
                         (base_size - padding, base_size - padding)],
                        fill=stop_color
                    )
            
            status_path = output_dir / f"simkl-mps-{status}.png"
            base_with_status.save(status_path)
            icons[status] = status_path
            
            ico_status_path = output_dir / f"simkl-mps-{status}.ico"
            base_with_status.save(ico_status_path, format="ICO", sizes=[(s, s) for s in [16, 24, 32, 48, 64, 128]])
            icons[f"{status}_ico"] = ico_status_path
            
        logger.info(f"Generated {len(icons)} icon files in {output_dir}")
        return icons
        
    except Exception as e:
        logger.error(f"Error generating icons: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, 
                      format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
    
    source_file = None
    output_dir = None
    
    if len(sys.argv) > 1:
        source_file = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
        
    generated = generate_icons(source_file=source_file, output_dir=output_dir)
    
    if generated:
        print(f"Successfully generated {len(generated)} icon variants")
        print("Icon paths:")
        for name, path in generated.items():
            print(f"  {name}: {path}")
    else:
        print("Failed to generate icons. Check the logs for details.")
        sys.exit(1)