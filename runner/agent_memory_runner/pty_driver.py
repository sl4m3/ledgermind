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
import time
from typing import List, Optional, Callable

class PTYDriver:
    def __init__(self, cmd: List[str], env: Optional[dict] = None):
        self.cmd = cmd
        self.env = env if env else os.environ.copy()
        self.master_fd = None
        self.pid = None
        self.old_tty_attrs = None

    def _set_winsize(self, fd, row, col, xpix=0, ypix=0):
        winsize = struct.pack("HHHH", row, col, xpix, ypix)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)

    def _resize_handler(self, signum, frame):
        """Propagate window size changes from parent to child PTY."""
        try:
            rows, cols, xpix, ypix = struct.unpack(
                "HHHH", 
                fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            )
            if self.master_fd is not None:
                self._set_winsize(self.master_fd, rows, cols, xpix, ypix)
        except Exception:
            pass

    def run(self, 
            on_output: Optional[Callable[[bytes], None]] = None,
            initial_input: Optional[bytes] = None):
        
        try:
            self.old_tty_attrs = termios.tcgetattr(sys.stdin.fileno())
        except Exception:
            pass

        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            try:
                os.execvpe(self.cmd[0], self.cmd, self.env)
            except Exception as e:
                sys.stderr.write(f"Error: {e}\n")
                sys.exit(1)
        else:
            signal.signal(signal.SIGWINCH, self._resize_handler)
            self._resize_handler(None, None)

            try:
                if self.old_tty_attrs:
                    tty.setraw(sys.stdin.fileno())

                if initial_input:
                    os.write(self.master_fd, initial_input)

                while True:
                    r, w, x = select.select([sys.stdin, self.master_fd], [], [])
                    
                    if self.master_fd in r:
                        try:
                            data = os.read(self.master_fd, 10240)
                        except OSError as e:
                            if e.errno == errno.EIO:
                                break
                            raise
                        
                        if not data:
                            break
                        
                        if on_output:
                            on_output(data)
                        
                        os.write(sys.stdout.fileno(), data)

                    if sys.stdin in r:
                        data = os.read(sys.stdin.fileno(), 10240)
                        if not data:
                            break
                        os.write(self.master_fd, data)

            except OSError as e:
                if e.errno == errno.EIO:
                    pass
            finally:
                if self.old_tty_attrs:
                    termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_tty_attrs)
                
                try:
                    os.close(self.master_fd)
                except:
                    pass
                os.waitpid(self.pid, 0)
