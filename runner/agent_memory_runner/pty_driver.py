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

    def _send_enter_later(self):
        """Sends an Enter keystroke after a tiny delay to ensure the shell registers it."""
        try:
            time.sleep(0.05)
            if self.master_fd:
                os.write(self.master_fd, b'\r')
        except: pass

    def run(self, 
            on_output: Callable[[bytes], None],
            on_exit: Callable[[], None],
            on_input: Optional[Callable[[bytes], bytes]] = None,
            initial_input: Optional[bytes] = None):
        
        self._on_exit_callback = on_exit
        atexit.register(self._cleanup)
        try: self.old_tty_attrs = termios.tcgetattr(sys.stdin.fileno())
        except: pass

        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            try: os.execvp(self.cmd[0], self.cmd)
            except Exception as e: sys.stderr.write(f"Fatal: {e}\n"); sys.exit(1)
        else:
            signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
            signal.signal(signal.SIGWINCH, self._resize_handler)
            self._resize_handler(None, None)
            
            try:
                if self.old_tty_attrs: tty.setraw(sys.stdin.fileno())
                if initial_input: os.write(self.master_fd, initial_input)

                fds = [sys.stdin.fileno(), self.master_fd]
                user_input_buffer = b""

                while True:
                    r, _, _ = select.select(fds, [], [], 0.1)
                    
                    if self.master_fd in r:
                        try:
                            data = os.read(self.master_fd, 10240)
                            if not data: break
                            on_output(data)
                            os.write(sys.stdout.fileno(), data)
                        except OSError as e:
                            # EIO is normal on some systems when child exits
                            if e.errno == errno.EIO: break
                            raise

                    if sys.stdin.fileno() in r:
                        try:
                            data = os.read(sys.stdin.fileno(), 10240)
                            if not data: break
                            
                            if on_input:
                                for char in data:
                                    c = bytes([char])
                                    if c in (b'\r', b'\n'):
                                        clean_query = "".join(chr(b) for b in user_input_buffer if 31 < b < 127).strip()
                                        if len(clean_query) >= 4:
                                            processed_payload = on_input(user_input_buffer)
                                            if processed_payload:
                                                os.write(self.master_fd, processed_payload)
                                                threading.Thread(target=self._send_enter_later, daemon=True).start()
                                            else:
                                                os.write(self.master_fd, b'\r')
                                        else:
                                            os.write(self.master_fd, b'\r')
                                        user_input_buffer = b""
                                    elif char in (8, 127):
                                        os.write(self.master_fd, c)
                                        if user_input_buffer: user_input_buffer = user_input_buffer[:-1]
                                    else:
                                        os.write(self.master_fd, c)
                                        if char >= 32: user_input_buffer += c
                            else:
                                os.write(self.master_fd, data)
                        except: break
            except Exception: pass
            finally:
                # DRAIN remaining output before closing
                try:
                    time.sleep(0.1)
                    final_data = os.read(self.master_fd, 10240)
                    if final_data: on_output(final_data)
                except: pass
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
