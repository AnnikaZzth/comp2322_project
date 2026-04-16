COMP2322 Computer Networking - Project 1
Multi-Thread Web Server

Student Name: ZHANG Tianhui
Student ID: 24121039D
Date: 16th April 2026

How to Run

1. Open terminal in project directory

2. Start server:
   python web_server.py

3. Open browser and go to:
   http://127.0.0.1:8080

How to Compile

Python is an interpreted language, no compilation needed.
Python version required: 3.6 or higher

Test Commands
GET (text):
   curl http://127.0.0.1:8080/
   curl http://127.0.0.1:8080/index.html
   curl http://127.0.0.1:8080/about.html

GET (image):
   curl http://127.0.0.1:8080/photo.jpg -o test.jpg

HEAD:
   curl -I http://127.0.0.1:8080/

404:
   curl http://127.0.0.1:8080/nonexistent.html

403:
   curl http://127.0.0.1:8080/../etc/passwd

304:
   curl http://127.0.0.1:8080/photo.jpg
   curl http://127.0.0.1:8080/photo.jpg   (second time returns 304)

File Structure
comp2322_project/
   web_server.py      - main server program
   server.log         - log file (auto-generated)
   README.txt         - this file
   www/
      index.html
      about.html
      test.html
      style.css
      photo.jpg
      test.txt
      secret.txt
      403.html
      404.html

Dependencies

No external dependencies. Uses only Python standard library.

Notes
- Server runs on http://127.0.0.1:8080
- Press Ctrl+C to stop server
- All web files must be in www/ directory
