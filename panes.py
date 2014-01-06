
import asyncio
import resource
import pyte
import os
import io

from log import logger
from utils import set_size
from pexpect_utils import pty_make_controlling_tty

loop = asyncio.get_event_loop()

class Position:
    # Bit flags
    Top = 1
    Bottom = 2
    Left = 4
    Right = 8


class CellPosition:
    """ Position of a cell according to a single pane. """
    Outside = 0
    Inside = 100

    TopBorder = Position.Top
    RightBorder = Position.Right
    BottomBorder = Position.Bottom
    LeftBorder = Position.Left
    TopLeftBorder = Position.Top | Position.Left
    TopRightBorder = Position.Top | Position.Right
    BottomRightBorder = Position.Bottom | Position.Right
    BottomLeftBorder = Position.Bottom | Position.Left


class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
    def __init__(self, pane):
        self.transport = None
        self.pane = pane

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.pane.write_output(data.decode('utf-8'))


class Pane:
    def __init__(self, command='/usr/bin/vim', invalidate_callback=None):
        self.invalidate = invalidate_callback
        self.command = command

        # Pane position.
        self.px = 0
        self.py = 0

        # Pane size
        self.sx = 120
        self.sy = 24

        # Create output stream.
        self.screen = pyte.DiffScreen(self.sx, self.sy)

        self.stream = pyte.Stream()
        self.stream.attach(self.screen)

        # Create pseudo terminal for this pane.
        self.master, self.slave = os.openpty()

        # Master side -> attached to terminal emulator.
        self.shell_out = io.open(self.master, 'rb', 0)

        # Slave side -> attached to process.
        set_size(self.slave, self.sy, self.sx)

        # Finished
        self.finished = False

    def set_position(self, px, py, sx, sy):
        """ Set position of pane in window. """
                # TODO: The position should probably not be a property of the
                #       pane itself.  A pane can appear in several windows.
        logger.info('set_position(px=%r, py=%r, sx=%r, sy=%r)' % (px, py, sx, sy))

        self.px = px
        self.py = py
        self.sx = sx
        self.sy = sy
        self.screen.resize(sy, sx)
        set_size(self.slave, self.sy, self.sx) # TODO: set on stdout??

        self.invalidate()

    def _run(self):
        pid = os.fork()
        if pid == 0: # TODO: <0 is fail
            os.close(self.master)

            pty_make_controlling_tty
            pty_make_controlling_tty(self.slave)

            # In the fork, set the stdin/out/err to our slave pty.
            os.dup2(self.slave, 0)
            os.dup2(self.slave, 1)
            os.dup2(self.slave, 2)

            # Do not allow child to inherit open file descriptors from parent.
            max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[-1]
            for i in range(3, max_fd):
                try:
                    os.close(i)
                except OSError:
                    pass

            # Set environment variables for child process
            os.environ['PYMUX_PANE'] = 'TODO:Pane value'

            os.execv(self.command, ['bash'])

        elif pid > 0:
            logger.info('Forked process: %r' % pid)
            self.process_pid = pid
            # Parent
            pid, status = os.waitpid(pid, 0)
            logger.info('Process ended, status=%r' % status)
            return

    @asyncio.coroutine
    def start(self):
        try:
            # Connect read pipe to process
            read_transport, read_protocol = yield from loop.connect_read_pipe(
                                lambda:SubProcessProtocol(self), self.shell_out)

            # Run process in executor, wait for that to finish.
            yield from loop.run_in_executor(None, self._run)

            # Set finished.
            self.finished = True # TODO: close pseudo terminal.
        except Exception as e:
            logger.error('CRASH: ' + repr(e))

    def kill_process(self):
        return
        #self.process.kill()

    def write_output(self, data):
        """ Write data received from the application into the pane and rerender. """
        self.stream.feed(data)
        self.invalidate()

    def write_input(self, data):
        """    Write user key strokes to the input. """
        os.write(self.master, data)
        #self.shell_in.write(data)


    @property
    def cursor_position(self):
        return self.screen.cursor.y, self.screen.cursor.x

    def _check_cell(self, x, y):
        """ For a given (x,y) cell, return the CellPosition. """
        # If outside this pane, skip it.
        if (x < self.px - 1 or x > self.px + self.sx or y < self.py - 1or y > self.py + self.sy):
            return CellPosition.Outside

        # Use bitmask for borders:
        mask = 0

        if y == self.py - 1:
            mask |= Position.Top

        if y == self.py + self.sy:
            mask |= Position.Bottom

        if x == self.px - 1:
            mask |= Position.Left

        if x == self.px + self.sx:
            mask |= Position.Right

        return mask
