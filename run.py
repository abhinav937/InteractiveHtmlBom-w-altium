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
        # Try to find KiCad in Program Files with version-specific paths
        for pf in [r'C:\Program Files', r'C:\Program Files (x86)']:
            if os.path.exists(pf):
                # First, try to find version-specific directories (e.g., KiCad\9.0\bin\python.exe, KiCad\9.1\bin\python.exe, etc.)
                # The '*' wildcard matches any version number (9.0, 9.1, 9.2, 9.10, etc.)
                version_matches = glob.glob(os.path.join(pf, 'KiCad', '*', 'bin', 'python.exe'))
                if version_matches:
                    # Sort to get the latest version first (if multiple versions exist)
                    # Natural sort handles version numbers better than alphabetical
                    def version_key(path):
                        # Extract version number from path for better sorting
                        parts = path.split(os.sep)
                        for part in parts:
                            if part.replace('.', '').isdigit():
                                try:
                                    return float(part)
                                except ValueError:
                                    pass
                        return 0.0
                    version_matches.sort(key=version_key, reverse=True)
                    return version_matches[0]
                # Then try generic KiCad\bin\python.exe
                generic_path = os.path.join(pf, 'KiCad', 'bin', 'python.exe')
                if os.path.exists(generic_path):
                    return generic_path
                # Also try KiCad*\bin\python.exe pattern (catches any KiCad directory)
                matches = glob.glob(os.path.join(pf, 'KiCad*', 'bin', 'python.exe'))
                if matches:
                    matches.sort(reverse=True)
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
    # Use subprocess instead of os.execv for better Windows compatibility with paths containing spaces
    import subprocess
    web_server_path = os.path.join(script_dir, 'web', 'web_server.py')
    subprocess.run([python_cmd, web_server_path])
else:
    print("KiCad Python not found. Trying system Python...")
    print("Note: File processing may fail if pcbnew module is not available.")
    # Fall back to system Python
    import subprocess
    subprocess.run([sys.executable, os.path.join(script_dir, 'web', 'web_server.py')])

