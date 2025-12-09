#!/usr/bin/env python3
"""
Simple launcher for Interactive HTML BOM web server.
Run this file to start the web interface.
"""
import os
import sys
import platform

def find_kicad_python():
    """Find KiCad Python installation."""
    system = platform.system()
    
    if system == 'Darwin':  # macOS
        kicad_paths = [
            '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3',
            '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.11/bin/python3',
            '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.10/bin/python3',
            '/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3',
        ]
        for path in kicad_paths:
            if os.path.exists(path):
                return path
    
    elif system == 'Linux':
        kicad_paths = [
            '/usr/bin/kicad-python3',
            '/usr/local/bin/kicad-python3',
        ]
        for path in kicad_paths:
            if os.path.exists(path):
                return path
        # Try to find in /usr/lib/kicad
        for kicad_dir in ['/usr/lib/kicad', '/usr/local/lib/kicad']:
            if os.path.exists(kicad_dir):
                python_path = os.path.join(kicad_dir, 'bin', 'python3')
                if os.path.exists(python_path):
                    return python_path
    
    elif system == 'Windows':
        import glob
        kicad_paths = [
            r'C:\Program Files\KiCad\bin\python.exe',
            r'C:\Program Files (x86)\KiCad\bin\python.exe',
        ]
        for path in kicad_paths:
            if os.path.exists(path):
                return path
        # Try to find in Program Files
        for pf in [r'C:\Program Files', r'C:\Program Files (x86)']:
            if os.path.exists(pf):
                matches = glob.glob(os.path.join(pf, 'KiCad*', 'bin', 'python.exe'))
                if matches:
                    return matches[0]
    
    return None

# Get the directory of this script
script_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
os.chdir(script_dir)

# Find KiCad Python
python_cmd = find_kicad_python()

if python_cmd:
    print(f"Using KiCad Python: {python_cmd}")
    # Run web_server.py with KiCad Python
    os.execv(python_cmd, [python_cmd, os.path.join(script_dir, 'web_server.py')])
else:
    print("KiCad Python not found. Trying system Python...")
    print("Note: File processing may fail if pcbnew module is not available.")
    # Fall back to system Python
    import subprocess
    subprocess.run([sys.executable, os.path.join(script_dir, 'web_server.py')])

