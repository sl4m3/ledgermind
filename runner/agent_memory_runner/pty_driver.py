import os
import pty
import tty
import termios
import fcntl
import struct
import signal
import select
import sys
import errno
import atexit
import time
import threading
from typing import List, Optional, Callable

class PTYDriver:
    def __init__(self, cmd: List[str]):
        self.cmd = cmd
        self.master_fd = None
        self.pid = None
        self.old_tty_attrs = None
        self._on_exit_callback = None

    def _set_winsize(self, fd, row, col, xpix=0, ypix=0):
        winsize = struct.pack("HHHH", row, col, xpix, ypix)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _resize_handler(self, signum, frame):
        if self.master_fd is None: return
        try:
            parent_fd = sys.stdout.fileno()
            winsize = fcntl.ioctl(parent_fd, termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except Exception: pass

    def run(self, 
            on_output: Callable[[bytes], None],
            on_exit: Callable[[], None],
            on_input: Optional[Callable[[bytes], bytes]] = None):
        
        self._on_exit_callback = on_exit
        atexit.register(self._cleanup)
        try: self.old_tty_attrs = termios.tcgetattr(sys.stdin.fileno())
        except: pass

        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            try: os.execvp(self.cmd[0], self.cmd)
            except Exception as e: sys.stderr.write(f"Fatal: {e}\n"); sys.exit(1)
        else:
            # Only set signals if main thread
            if threading.current_thread() is threading.main_thread():
                signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
                signal.signal(signal.SIGWINCH, self._resize_handler)
                self._resize_handler(None, None)
            
            try:
                if self.old_tty_attrs: tty.setraw(sys.stdin.fileno())

                fds = [sys.stdin.fileno(), self.master_fd]
                user_input_buffer = bytearray()
                MAX_BUF_SIZE = 8192

                while True:
                    r, _, _ = select.select(fds, [], [], 0.05)
                    
                    if self.master_fd in r:
                        try:
                            data = os.read(self.master_fd, 16384)
                            if not data: break
                            on_output(data)
                            os.write(sys.stdout.fileno(), data)
                        except OSError as e:
                            if e.errno == errno.EIO: break
                            raise

                    if sys.stdin.fileno() in r:
                        try:
                            data = os.read(sys.stdin.fileno(), 16384)
                            if not data: break
                            
                            if on_input:
                                user_input_buffer.extend(data)
                                if len(user_input_buffer) > MAX_BUF_SIZE:
                                    user_input_buffer = user_input_buffer[-MAX_BUF_SIZE:]

                                if b'\r' in data or b'\n' in data:
                                    payload = on_input(bytes(user_input_buffer))
                                    if payload:
                                        os.write(self.master_fd, payload)
                                        time.sleep(0.02)
                                    os.write(self.master_fd, data)
                                    user_input_buffer = bytearray()
                                else:
                                    os.write(self.master_fd, data)
                            else:
                                os.write(self.master_fd, data)
                        except: break
            except Exception: pass
            finally:
                self._cleanup()

    def _cleanup(self):
        if self.old_tty_attrs:
            try: termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_tty_attrs)
            except: pass
        if self._on_exit_callback:
            try: self._on_exit_callback()
            except: pass
            self._on_exit_callback = None
        try:
            if self.master_fd: os.close(self.master_fd)
        except: pass
