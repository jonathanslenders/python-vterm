
import asyncio
import resource
import pyte
import os
import io

from log import logger
from utils import set_size
from pexpect_utils import pty_make_controlling_tty
from layout import Container

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
    Inside = 2048

    TopBorder = Position.Top
    RightBorder = Position.Right
    BottomBorder = Position.Bottom
    LeftBorder = Position.Left
    TopLeftBorder = Position.Top | Position.Left
    TopRightBorder = Position.Top | Position.Right
    BottomRightBorder = Position.Bottom | Position.Right
    BottomLeftBorder = Position.Bottom | Position.Left

class BorderType:
    """ Position of a cell in a window. """
    Outside = 0
    Inside = 2048

    # Cross join
    Join = Position.Left | Position.Top | Position.Bottom | Position.Right

    BottomJoin = Position.Left | Position.Right | Position.Top
    TopJoin = Position.Left | Position.Right | Position.Bottom
    LeftJoin = Position.Right | Position.Top | Position.Bottom
    RightJoin = Position.Left | Position.Top | Position.Bottom

    # In the middle of a border
    Horizontal = Position.Left | Position.Right
    Vertical = Position.Bottom | Position.Top

    BottomRight = Position.Left | Position.Top
    TopRight = Position.Left | Position.Bottom
    BottomLeft = Position.Right | Position.Top
    TopLeft = Position.Right | Position.Bottom



class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
    def __init__(self, pane):
        self.transport = None
        self.pane = pane

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self.pane.write_output(data.decode('utf-8'))


class Pane(Container):
    def __init__(self, command='/usr/bin/vim', invalidate_callback=None):
        super().__init__()

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

    @property
    def panes(self):
        yield self

    def add(self, child):
        # Pane is a leaf node.
        raise NotImplementedError

    def set_location(self, location):
        """ Set position of pane in window. """
                # TODO: The position should probably not be a property of the
                #       pane itself.  A pane can appear in several windows.
        logger.info('set_position(px=%r, py=%r, sx=%r, sy=%r)' % (location.px, location.py, location.sx, location.sy))

        self.px = location.px
        self.py = location.py
        self.sx = location.sx
        self.sy = location.sy
        self.screen.resize(self.sy, self.sx)
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

    def _get_border_type(self, x, y):
        return {
            CellPosition.TopBorder: BorderType.Horizontal,
            CellPosition.BottomBorder: BorderType.Horizontal,
            CellPosition.LeftBorder: BorderType.Vertical,
            CellPosition.RightBorder: BorderType.Vertical,

            CellPosition.TopLeftBorder: BorderType.TopLeft,
            CellPosition.TopRightBorder: BorderType.TopRight,
            CellPosition.BottomLeftBorder: BorderType.BottomLeft,
            CellPosition.BottomRightBorder: BorderType.BottomRight,

            CellPosition.Inside: BorderType.Inside,
            CellPosition.Outside: BorderType.Outside,
        }[ self._get_cell_position(x,y) ]

    def _get_cell_position(self, x, y):
        """ For a given (x,y) cell, return the CellPosition. """
        # If outside this pane, skip it.
        if x < self.px - 1 or x > self.px + self.sx or y < self.py - 1 or y > self.py + self.sy:
            return CellPosition.Outside

#        #  If inside, return that.
#        if x >= self.px and x < self.px + self.sx and y >= self.py and y < self.py + self.sy:
#            return CellPosition.Inside

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

        if mask:
            return mask
        else:
            raise IMPOSSIBLE
            #return CellPosition.Inside
