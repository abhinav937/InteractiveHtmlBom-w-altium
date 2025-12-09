#!/usr/bin/env python3
"""
Web server for Interactive HTML BOM with file upload support.
Opens a browser interface where users can upload .PcbDoc or .kicad_pcb files.
"""
from __future__ import absolute_import

import os
import sys
import tempfile
import shutil
import webbrowser
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import io
import re

# Try to import cgi, fall back to manual parsing for Python 3.13+
try:
    import cgi
    HAS_CGI = True
except ImportError:
    HAS_CGI = False

# Add the project directory to path
script_dir = os.path.dirname(os.path.abspath(os.path.realpath(__file__)))
# Get the project root directory (parent of web/)
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)


def parse_multipart_form_data(post_data, content_type, headers=None):
    """
    Parse multipart/form-data. Compatible with Python 3.13+ (no cgi module).
    Returns a dict-like object similar to cgi.FieldStorage.
    """
    if HAS_CGI:
        # Use cgi if available (Python < 3.13)
        if headers is None:
            headers = {}
        if 'Content-Type' not in headers:
            headers['Content-Type'] = content_type
        form = cgi.FieldStorage(
            fp=io.BytesIO(post_data),
            headers=headers,
            environ={'REQUEST_METHOD': 'POST'}
        )
        return form
    
    # Manual parsing for Python 3.13+
    boundary_match = re.search(r'boundary=([^;]+)', content_type)
    if not boundary_match:
        raise ValueError("No boundary found in Content-Type")
    
    boundary = boundary_match.group(1).strip('"')
    parts = post_data.split(b'--' + boundary.encode())
    
    class FieldStorage:
        def __init__(self):
            self._fields = {}
        
        def __contains__(self, key):
            return key in self._fields
        
        def __getitem__(self, key):
            return self._fields[key]
        
        def get(self, key, default=None):
            return self._fields.get(key, default)
        
        def getvalue(self, key, default=None):
            item = self._fields.get(key)
            if item is None:
                return default
            if hasattr(item, 'value') and item.value is not None:
                return item.value
            # For file fields, return None or default
            if hasattr(item, 'filename') and item.filename:
                return default
            return item
    
    class FieldItem:
        def __init__(self, filename=None, value=None, file_data=None):
            self.filename = filename
            self.value = value
            if file_data is not None:
                self.file = io.BytesIO(file_data)
                self.file.seek(0)  # Reset to beginning
            else:
                self.file = None
    
    form = FieldStorage()
    
    for part in parts:
        if not part.strip() or part.strip() == b'--':
            continue
        
        # Split headers and body
        if b'\r\n\r\n' in part:
            header_part, body = part.split(b'\r\n\r\n', 1)
        elif b'\n\n' in part:
            header_part, body = part.split(b'\n\n', 1)
        else:
            continue
        
        headers = {}
        for line in header_part.decode('utf-8', errors='ignore').split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
        
        # Get Content-Disposition
        content_disp = headers.get('content-disposition', '')
        name_match = re.search(r'name="([^"]+)"', content_disp)
        if not name_match:
            continue
        
        field_name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]+)"', content_disp)
        
        # Remove trailing boundary marker if present
        if body.endswith(b'--\r\n'):
            body = body[:-4]
        elif body.endswith(b'--'):
            body = body[:-2]
        
        # Remove trailing newlines
        body = body.rstrip(b'\r\n')
        
        if filename_match:
            filename = filename_match.group(1)
            form._fields[field_name] = FieldItem(filename=filename, file_data=body)
        else:
            form._fields[field_name] = FieldItem(value=body.decode('utf-8', errors='ignore'))
    
    return form


class BOMHandler(BaseHTTPRequestHandler):
    """HTTP request handler for BOM generation server."""
    
    temp_dir = None
    output_dir = None
    server_url = None  # Store server URL for generating full paths
    file_registry = {}  # Map filename -> output_dir for serving generated files
    
    def log_message(self, format, *args):
        """Override to reduce logging noise."""
        pass
    
    def do_GET(self):
        """Handle GET requests."""
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/' or parsed_path.path == '/index.html':
            self.serve_index()
        elif parsed_path.path.startswith('/generated/'):
            self.serve_generated_file(parsed_path.path)
        elif parsed_path.path == '/status':
            self.serve_status()
        else:
            self.send_error(404, "File not found")
    
    def do_POST(self):
        """Handle POST requests (file uploads)."""
        if self.path == '/upload':
            self.handle_upload()
        elif self.path == '/cleanup':
            self.handle_cleanup()
        else:
            self.send_error(404, "Endpoint not found")
    
    def serve_index(self):
        """Serve the main HTML interface."""
        html_path = os.path.join(script_dir, 'index.html')
        if os.path.exists(html_path):
            with open(html_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "index.html not found")
    
    def serve_generated_file(self, path):
        """Serve generated BOM HTML files."""
        filename = os.path.basename(path)
        
        # Try to find the file in the registry first
        output_dir = self.file_registry.get(filename)
        
        # If not in registry, try current output_dir (for same-request access)
        if not output_dir:
            output_dir = self.output_dir
        
        # If still not found, search in common temp locations
        if not output_dir or not os.path.exists(os.path.join(output_dir, filename)):
            # Search in system temp directory for bom_* directories
            import tempfile
            temp_base = tempfile.gettempdir()
            for item in os.listdir(temp_base):
                if item.startswith('bom_'):
                    potential_dir = os.path.join(temp_base, item, 'output')
                    potential_file = os.path.join(potential_dir, filename)
                    if os.path.exists(potential_file):
                        output_dir = potential_dir
                        # Cache it for future requests
                        self.file_registry[filename] = output_dir
                        break
        
        if not output_dir:
            self.send_error(404, "Generated file not found")
            return
        
        file_path = os.path.join(output_dir, filename)
        
        if os.path.exists(file_path) and os.path.isfile(file_path):
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.send_header('Content-length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404, "Generated file not found")
    
    def serve_status(self):
        """Return server status."""
        status = {
            'temp_dir': self.temp_dir,
            'output_dir': self.output_dir,
            'ready': True
        }
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())
    
    def handle_upload(self):
        """Handle file upload and process it."""
        try:
            content_type = self.headers.get('Content-Type', '')
            if not content_type.startswith('multipart/form-data'):
                self.send_error(400, "Invalid content type")
                return
            
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Parse multipart form data (compatible with Python 3.13+)
            form = parse_multipart_form_data(post_data, content_type, self.headers)
            
            # Get file
            if 'file' not in form:
                self.send_error(400, "No file uploaded")
                return
            
            file_item = form['file']
            if not file_item.filename:
                self.send_error(400, "No file selected")
                return
            
            filename = file_item.filename
            file_data = file_item.file.read()
            
            # Get temp_dir if provided
            temp_dir_input = form.getvalue('temp_dir', '').strip()
            
            # Determine temp directory
            if temp_dir_input:
                temp_base = temp_dir_input.strip()
                if not os.path.isabs(temp_base):
                    temp_base = os.path.join(script_dir, temp_base)
                if not os.path.exists(temp_base):
                    os.makedirs(temp_base)
                work_dir = tempfile.mkdtemp(dir=temp_base, prefix='bom_')
            else:
                work_dir = tempfile.mkdtemp(prefix='bom_')
            
            self.temp_dir = work_dir
            self.output_dir = os.path.join(work_dir, 'output')
            os.makedirs(self.output_dir, exist_ok=True)
            
            # Save uploaded file
            uploaded_file = os.path.join(work_dir, filename)
            with open(uploaded_file, 'wb') as f:
                f.write(file_data)
            
            # Process the file
            result = self.process_file(uploaded_file, work_dir)
            
            if result['success']:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
            else:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(result).encode())
        
        except Exception as e:
            self.send_error(500, f"Server error: {str(e)}")
    
    def process_file(self, file_path, work_dir):
        """Process the uploaded file and generate BOM."""
        try:
            # Lazy import to avoid requiring pcbnew at startup
            from InteractiveHtmlBom.core import ibom
            from InteractiveHtmlBom.core.config import Config
            from InteractiveHtmlBom.ecad import get_parser_by_extension
            from InteractiveHtmlBom.version import version
            
            logger = ibom.Logger(cli=True)
            config = Config(version, work_dir)
            config.bom_dest_dir = 'output'
            config.open_browser = False  # Don't open browser from server
            
            parser = get_parser_by_extension(os.path.abspath(file_path), config, logger)
            
            if not parser:
                file_ext = os.path.splitext(file_path)[1].lower()
                return {
                    'success': False,
                    'error': f'Unsupported file format: {file_ext or "unknown"}\n\nPlease upload one of the following:\n• .PcbDoc (Altium Designer)\n• .kicad_pcb (KiCad)'
                }
            
            pcbdata, components = parser.parse()
            
            if not pcbdata or not components:
                return {
                    'success': False,
                    'error': 'Failed to parse the PCB file. Please check the file and try again.'
                }
            
            pcbdata["bom"] = ibom.generate_bom(components, config)
            pcbdata["ibom_version"] = config.version
            
            # Generate HTML file
            pcb_file_name = os.path.basename(file_path)
            bom_file = ibom.generate_file(work_dir, pcb_file_name, pcbdata, config, logger)
            bom_filename = os.path.basename(bom_file)
            
            # Register the file location for serving
            output_dir = os.path.join(work_dir, 'output')
            self.file_registry[bom_filename] = output_dir
            
            # Generate full URLs
            # Get server address from the request
            host = self.headers.get('Host', 'localhost')
            if ':' in host:
                server_base = f'http://{host}'
            else:
                # Fallback if port not in Host header
                server_port = self.server.server_address[1]
                server_base = f'http://{host}:{server_port}'
            
            full_url = f'{server_base}/generated/{bom_filename}'
            file_url = f'file://{bom_file}'
            
            return {
                'success': True,
                'filename': bom_filename,
                'url': full_url,
                'file_path': bom_file,
                'file_url': file_url,
                'message': f'Successfully generated BOM with {len(components)} components'
            }
        
        except ImportError as e:
            if 'pcbnew' in str(e).lower():
                kicad_python = find_kicad_python()
                error_msg = (
                    'KiCad Python API (pcbnew) not found.\n\n'
                    'The server is running with system Python, but needs KiCad Python.\n\n'
                )
                if kicad_python:
                    error_msg += (
                        f'Please restart the server using:\n'
                        f'  {kicad_python} web_server.py\n\n'
                        f'Or simply use the launcher script:\n'
                        f'  python3 start_bom_server.py\n\n'
                        f'The launcher will automatically use KiCad Python.'
                    )
                else:
                    error_msg += (
                        'Please ensure KiCad is installed and use KiCad Python to run the server.\n'
                        'Or use the launcher script: start_bom_server.py'
                    )
                return {
                    'success': False,
                    'error': error_msg
                }
            return {
                'success': False,
                'error': f'Import error: {str(e)}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error processing file: {str(e)}'
            }
    
    def handle_cleanup(self):
        """Handle cleanup request to delete temp files."""
        try:
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
                self.temp_dir = None
                self.output_dir = None
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'success': True}).encode())
        except Exception as e:
            self.send_error(500, f"Cleanup error: {str(e)}")


def find_free_port():
    """Find a free port for the server."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


def check_kicad_python():
    """Check if pcbnew module is available."""
    try:
        import pcbnew
        return True, None
    except ImportError:
        return False, "pcbnew module not found"


def find_kicad_python():
    """Find KiCad Python installation."""
    import platform
    
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
        # Try common Linux locations
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
        # Windows common locations
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


def main():
    """Start the web server."""
    # Check if pcbnew is available
    has_pcbnew, error_msg = check_kicad_python()
    
    if not has_pcbnew:
        print("=" * 60)
        print("WARNING: KiCad Python API (pcbnew) not found!")
        print("=" * 60)
        print(f"Error: {error_msg}")
        print("\nThe web server needs KiCad's Python to process PCB files.")
        print("\nTrying to find KiCad Python installation...")
        
        kicad_python = find_kicad_python()
        if kicad_python:
            print(f"\nFound KiCad Python at: {kicad_python}")
            print(f"\nAuto-restarting with KiCad Python...")
            print("=" * 60)
            # Restart with KiCad Python
            # Use subprocess instead of os.execv for better Windows compatibility with paths containing spaces
            import subprocess
            script_path = os.path.join(script_dir, 'web_server.py')
            try:
                # Use subprocess.Popen to start new process and exit current one
                subprocess.Popen([kicad_python, script_path] + sys.argv[1:])
                sys.exit(0)
            except Exception as e:
                print(f"Failed to restart with KiCad Python: {e}")
                print(f"\nPlease manually run:")
                print(f"  {kicad_python} web_server.py")
                print(f"\nOr use the launcher: start_bom_server.py")
                sys.exit(1)
        else:
            print("\nCould not find KiCad installation automatically.")
            print("\nPlease ensure KiCad is installed and either:")
            print("1. Use KiCad's Python to run this server:")
            print("   macOS: /Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3 web_server.py")
            print("   Linux: kicad-python3 web_server.py")
            print("   Windows: \"C:\\Program Files\\KiCad\\bin\\python.exe\" web_server.py")
            print("\n2. Or use the launcher script: start_bom_server.py")
            print("\n" + "=" * 60)
            response = input("\nContinue anyway? (y/N): ").strip().lower()
            if response != 'y':
                print("Exiting. Please use KiCad's Python to run the server.")
                sys.exit(1)
            print("\nNote: File processing will fail without pcbnew module.\n")
    
    port = find_free_port()
    server_address = ('localhost', port)
    httpd = HTTPServer(server_address, BOMHandler)
    
    # Store server URL in handler class
    BOMHandler.server_url = 'http://localhost'
    
    url = f'http://localhost:{port}/'
    
    print(f"Starting Interactive HTML BOM server...")
    print(f"Server running at {url}")
    print(f"Opening browser...")
    print(f"Press Ctrl+C to stop the server")
    
    # Open browser after a short delay
    def open_browser():
        time.sleep(1)
        webbrowser.open(url)
    
    threading.Thread(target=open_browser, daemon=True).start()
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        # Cleanup temp directories
        if BOMHandler.temp_dir and os.path.exists(BOMHandler.temp_dir):
            try:
                shutil.rmtree(BOMHandler.temp_dir)
            except:
                pass
        httpd.shutdown()


if __name__ == '__main__':
    main()

