import socket
import os
import threading
import time
import logging
from datetime import datetime
from urllib.parse import unquote
import email.utils

class WebServer:
    def __init__(self, host='127.0.0.1', port=8080, www_root='www'):
        self.host = host
        self.port = port
        self.www_root = www_root
        self.server_socket = None
        
        self.setup_logger()
        
        self.mime_types = {
            '.html': 'text/html',
            '.htm': 'text/html',
            '.txt': 'text/plain',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.pdf': 'application/pdf',
        }

        if not os.path.exists(self.www_root):
            os.makedirs(self.www_root)
            self.create_test_files()
    
    def setup_logger(self):
        logging.basicConfig(
            filename='server.log',
            level=logging.INFO,
            format='%(asctime)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        self.logger = logging.getLogger(__name__)
    
    def get_mime_type(self, filepath):
        ext = os.path.splitext(filepath)[1].lower()
        return self.mime_types.get(ext, 'application/octet-stream')
    
    def get_file_info(self, filepath):
        full_path = os.path.join(self.www_root, filepath)
        
        if not os.path.exists(full_path):
            return False, None, None, None
        
        stat = os.stat(full_path)
        timestamp = stat.st_mtime
        gmt_time = email.utils.formatdate(timestamp, usegmt=True)
        return True, stat.st_size, timestamp, gmt_time
    
    def parse_request(self, request_data):
        lines = request_data.split('\r\n')
        if not lines or not lines[0].strip():
            return None
        
        request_line = lines[0].strip().split()
        if len(request_line) != 3:
            return None
        
        method = request_line[0].upper()
        full_path = unquote(request_line[1])
        path = full_path.split('?')[0]
        version = request_line[2]
        
        if not version.startswith('HTTP/'):
            return None
        
        if method not in ['GET', 'HEAD']:
            return None
        
        headers = {}
        for line in lines[1:]:
            if ':' in line:
                key, value = line.split(':', 1)
                headers[key.strip().lower()] = value.strip()
            elif line.strip() == '':
                break
        
        return {
            'method': method,
            'path': path,
            'version': version,
            'headers': headers
        }
    
    def check_modified_since(self, file_timestamp, if_modified_since_header):
        if not if_modified_since_header:
            return True
        
        try:
            ims_time = email.utils.parsedate_to_datetime(if_modified_since_header)
            ims_timestamp = ims_time.timestamp()
            
            if file_timestamp <= ims_timestamp + 1:
                return False
            else:
                return True
        except (ValueError, TypeError, AttributeError):
            return True
    
    def build_response(self, status_code, headers=None, body=None, keep_alive=False):
        status_messages = {
            200: 'OK',
            304: 'Not Modified',
            400: 'Bad Request',
            403: 'Forbidden',
            404: 'Not Found'
        }
        
        status_line = f'HTTP/1.1 {status_code} {status_messages.get(status_code, "Unknown")}\r\n'
        
        response_headers = headers or {}
        response_headers['Server'] = 'MultiThreadedWebServer/1.0'
        response_headers['Date'] = email.utils.formatdate(time.time(), usegmt=True)
        
        if body is not None and status_code != 304:
            response_headers['Content-Length'] = len(body)
        
        if keep_alive:
            response_headers['Connection'] = 'keep-alive'
        else:
            response_headers['Connection'] = 'close'
        
        header_lines = status_line
        for key, value in response_headers.items():
            header_lines += f'{key}: {value}\r\n'
        header_lines += '\r\n'
        
        response = header_lines.encode('utf-8')
        if body is not None and status_code != 304:
            response += body if isinstance(body, bytes) else body.encode('utf-8')
        
        return response
    
    def handle_get(self, request, client_ip):
        filepath = request['path']
        
        forbidden_patterns = ['..', '/..', '/etc/', '/var/', '/usr/', '/bin/', '/System/', '/Library/']
        if any(pattern in filepath for pattern in forbidden_patterns):
            return 403, {'Content-Type': 'text/html'}, '<html><body><h1>403 Forbidden</h1><p>Access denied.</p></body></html>'.encode('utf-8')
        
        if filepath == '/' or filepath == '':
            filepath = '/index.html'
        
        if filepath.startswith('/'):
            filepath = filepath[1:]
        
        full_path = os.path.join(self.www_root, filepath)
        
        exists, size, file_timestamp, gmt_time = self.get_file_info(filepath)
        
        if not exists:
            error_path = os.path.join(self.www_root, '404.html')
            if os.path.exists(error_path):
                with open(error_path, 'rb') as f:
                    body = f.read()
            else:
                body = '<html><body><h1>404 Not Found</h1></body></html>'.encode('utf-8')
            return 404, {'Content-Type': 'text/html'}, body
        
        if not os.access(full_path, os.R_OK):
            return 403, {'Content-Type': 'text/html'}, '<html><body><h1>403 Forbidden</h1><p>Access denied.</p></body></html>'.encode('utf-8')
        
        original_path = request.get('original_path', '')
        if '?' in original_path:
            pass
        else:
            if_modified_since = request['headers'].get('if-modified-since')
            if not self.check_modified_since(file_timestamp, if_modified_since):
                return 304, {}, None
        
        with open(full_path, 'rb') as f:
            body = f.read()
        
        headers = {
            'Content-Type': self.get_mime_type(filepath),
            'Last-Modified': gmt_time,
            'Content-Length': size
        }
        
        return 200, headers, body
    
    def handle_head(self, request, client_ip):
        status_code, headers, body = self.handle_get(request, client_ip)
        return status_code, headers, None
    
    def log_request(self, client_ip, method, path, status_code):
        log_entry = f"{client_ip} - [{datetime.now()}] \"{method} {path}\" {status_code}"
        print(log_entry)
        self.logger.info(log_entry)
    
    def handle_client(self, client_socket, client_address):
        client_ip = client_address[0]
        
        try:
            client_socket.settimeout(5)
            
            while True:
                try:
                    request_data = client_socket.recv(4096).decode('utf-8', errors='ignore')
                    
                    if not request_data:
                        break
                    
                    request = self.parse_request(request_data)
                    if not request:
                        response = self.build_response(400, {'Content-Type': 'text/html'}, 
                                                       '<html><body><h1>400 Bad Request</h1></body></html>',
                                                       keep_alive=False)
                        client_socket.send(response)
                        self.log_request(client_ip, 'UNKNOWN', 'UNKNOWN', 400)
                        break
                    
                    method = request['method']
                    path = request['path']
                    
                    connection_header = request['headers'].get('connection', '').lower()
                    version = request['version']
                    if version == 'HTTP/1.1':
                        keep_alive = (connection_header != 'close')
                    else:
                        keep_alive = (connection_header == 'keep-alive')
                    
                    if method == 'GET':
                        status_code, headers, body = self.handle_get(request, client_ip)
                        response = self.build_response(status_code, headers, body, keep_alive)
                        client_socket.send(response)
                        
                    elif method == 'HEAD':
                        status_code, headers, body = self.handle_head(request, client_ip)
                        response = self.build_response(status_code, headers, body, keep_alive)
                        client_socket.send(response)
                        
                    else:
                        status_code = 405
                        response = self.build_response(405, {'Content-Type': 'text/html'},
                                                       '<html><body><h1>405 Method Not Allowed</h1></body></html>',
                                                       keep_alive=False)
                        client_socket.send(response)
                    
                    self.log_request(client_ip, method, path, status_code)
                    
                    if not keep_alive:
                        break
                    
                except socket.timeout:
                    break
                except socket.error:
                    break
                    
        except Exception as e:
            print(f"[ERROR] Error handling client {client_ip}: {e}")
        finally:
            client_socket.close()
    
    def create_test_files(self):
        index_path = os.path.join(self.www_root, 'index.html')
        if not os.path.exists(index_path):
            with open(index_path, 'w') as f:
                f.write("""<!DOCTYPE html>
<html>
<head><title>Web Server Test</title><link rel="stylesheet" href="style.css"></head>
<body>
<h1>Welcome to Multi-Thread Web Server</h1>
<p>This is a test page.</p>
<button id="loadImageBtn">Load Image</button>
<div id="imageContainer"></div>
<script>
document.getElementById('loadImageBtn').addEventListener('click', function() {
    const container = document.getElementById('imageContainer');
    const timestamp = new Date().getTime();
    container.innerHTML = '<img src="photo.jpg?t=' + timestamp + '" alt="Test Image" width="200">';
});
</script>
</body>
</html>""")
        
        css_path = os.path.join(self.www_root, 'style.css')
        if not os.path.exists(css_path):
            with open(css_path, 'w') as f:
                f.write("body { font-family: Arial; background: #f0f0f0; text-align: center; padding: 50px; } button { padding: 10px 20px; font-size: 16px; cursor: pointer; }")
        
        error404_path = os.path.join(self.www_root, '404.html')
        if not os.path.exists(error404_path):
            with open(error404_path, 'w') as f:
                f.write("""<!DOCTYPE html>
<html><body><h1>404 Not Found</h1><p>The requested file does not exist.</p></body></html>""")
        
        print("[INFO] Test files created in www/ directory")
        print("[INFO] Please add a photo.jpg file to the www/ directory for image testing")
    
    def start(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.server_socket.bind((self.host, self.port))
        except Exception as e:
            print(f"[ERROR] Failed to bind to {self.host}:{self.port}: {e}")
            return
        
        self.server_socket.listen(10)
        print(f"[INFO] Web server started on http://{self.host}:{self.port}")
        print(f"[INFO] Web root directory: {os.path.abspath(self.www_root)}")
        print("[INFO] Press Ctrl+C to stop the server")
        
        try:
            while True:
                client_socket, client_address = self.server_socket.accept()
                print(f"[INFO] Connection from {client_address[0]}:{client_address[1]}")
                
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
                
        except KeyboardInterrupt:
            print("\n[INFO] Shutting down server...")
        finally:
            self.server_socket.close()
            print("[INFO] Server stopped")

def main():
    HOST = '127.0.0.1'
    PORT = 8080
    WWW_ROOT = 'www'
    
    server = WebServer(HOST, PORT, WWW_ROOT)
    server.start()

if __name__ == '__main__':
    main()