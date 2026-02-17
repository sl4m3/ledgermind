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
from typing import List, Optional, Callable

class PTYDriver:
    def __init__(self, cmd: List[str]):
        self.cmd = cmd
        self.master_fd = None
        self.pid = None
        self.old_tty_attrs = None
        self._on_exit_callback = None

    def run(self, 
            on_output: Callable[[bytes], None],
            on_exit: Callable[[], None],
            on_input: Optional[Callable[[bytes], bytes]] = None,
            initial_input: Optional[bytes] = None):
        
        self._on_exit_callback = on_exit
        atexit.register(self._cleanup)
        
        try:
            self.old_tty_attrs = termios.tcgetattr(sys.stdin.fileno())
        except: pass

        self.pid, self.master_fd = pty.fork()

        if self.pid == 0:
            try:
                os.execvp(self.cmd[0], self.cmd)
            except Exception as e:
                sys.stderr.write(f"Fatal: {e}\n")
                sys.exit(1)
        else:
            signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
            
            try:
                if self.old_tty_attrs:
                    tty.setraw(sys.stdin.fileno())

                if initial_input:
                    os.write(self.master_fd, initial_input)

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
                            if e.errno == errno.EIO: break
                            raise

                    if sys.stdin.fileno() in r:
                        try:
                            data = os.read(sys.stdin.fileno(), 10240)
                            if not data: break
                            
                            if on_input:
                                # Накапливаем буфер до нажатия Enter
                                user_input_buffer += data
                                if b'\r' in data or b'\n' in data:
                                    # Трансформируем ввод через хук (инъекция памяти)
                                    processed_input = on_input(user_input_buffer)
                                    os.write(self.master_fd, processed_input)
                                    user_input_buffer = b""
                                else:
                                    # Пока просто копируем в stdout пользователя (echo), 
                                    # чтобы он видел, что печатает (в raw mode это нужно)
                                    os.write(sys.stdout.fileno(), data)
                            else:
                                os.write(self.master_fd, data)
                        except: break

            except Exception:
                pass
            finally:
                # Финальный захват остатков
                try:
                    time.sleep(0.2)
                    final_data = os.read(self.master_fd, 10240)
                    if final_data: on_output(final_data)
                except: pass
                self._cleanup()

    def _cleanup(self):
        if self.old_tty_attrs:
            try:
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, self.old_tty_attrs)
            except: pass
        
        if self._on_exit_callback:
            try: self._on_exit_callback()
            except: pass
            self._on_exit_callback = None
            
        try:
            if self.master_fd: os.close(self.master_fd)
        except: pass
