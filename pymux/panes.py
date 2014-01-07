
import asyncio
import resource
import pyte
import os
import io

from .log import logger
from .utils import set_size
from .pexpect_utils import pty_make_controlling_tty
from .layout import Container, Location

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

# Patch pyte.graphics to accept High intensity colours as well.
from pyte.graphics import FG, BG

FG.update({
    90: "hi_fg_1",
    91: "hi_fg_2",
    92: "hi_fg_3",
    93: "hi_fg_4",
    94: "hi_fg_5",
    95: "hi_fg_6",
    96: "hi_fg_7",
    97: "hi_fg_8",
    98: "hi_fg_9",
    99: "hi_fg_10",
})

BG.update({
    100: "hi_bg_1",
    101: "hi_bg_2",
    102: "hi_bg_3",
    103: "hi_bg_4",
    104: "hi_bg_5",
    105: "hi_bg_6",
    106: "hi_bg_7",
    107: "hi_bg_8",
    108: "hi_bg_9",
    109: "hi_bg_10",
})


class AlternateScreen(pyte.DiffScreen):
    """
    DiffScreen which also implements the alternate screen buffer like Xterm.
    """
    swap_variables = [
            'mode',
            'margins',
            'charset',
            'g0_charset',
            'g1_charset',
            'tabstops',
            'cursor', ]

    def __init__(self, *args):
        super().__init__(*args)
        self._original_screen = None

    def set_mode(self, *modes, **kwargs):
        # On "\e[?1049h", enter alternate screen mode. Backup the current state,
        if 1049 in modes:
            self._original_screen = self[:]
            self._original_screen_vars = \
                { v:getattr(self, v) for v in self.swap_variables }
            self.reset()

        super().set_mode(*modes, **kwargs)

    def reset_mode(self, *modes, **kwargs):
        # On "\e[?1049l", restore from alternate screen mode.
        if 1049 in modes and self._original_screen:
            for k, v in self._original_screen_vars.items():
                setattr(self, k, v)
            self[:] = self._original_screen

            self._original_screen = None
            self._original_screen_vars = {}
            self.dirty.update(range(self.lines))

        super().reset_mode(*modes, **kwargs)

    def select_graphic_rendition(self, *attrs):
        """ Support 256 colours """
        g = pyte.graphics
        replace = {}

        if not attrs:
            attrs = [0]
        else:
            attrs = list(attrs[::-1])

        while attrs:
            attr = attrs.pop()

            if attr in g.FG:
                replace["fg"] = g.FG[attr]
            elif attr in g.BG:
                replace["bg"] = g.BG[attr]
            elif attr in g.TEXT:
                attr = g.TEXT[attr]
                replace[attr[1:]] = attr.startswith("+")
            elif not attr:
                replace = self.default_char._asdict()

            elif attr in (38, 48):
                n = attrs.pop()
                if n != 5:
                    continue

                if attr == 38:
                    m = attrs.pop()
                    replace["fg"] = 1024 + m
                elif attr == 48:
                    m = attrs.pop()
                    replace["bg"] = 1024 + m

        self.cursor.attrs = self.cursor.attrs._replace(**replace)

        # See tmux/input.c, line: 1388


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

        self.location = Location(self.py, self.py, self.sx, self.sy)

        # Create output stream.
        #self.screen = pyte.DiffScreen(self.sx, self.sy)
        self.screen = AlternateScreen(self.sx, self.sy)

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
        self.location = location

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
        """ Write user key strokes to the input. """
        os.write(self.master, data)

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

    def is_inside(self, x, y):
        """ True when this coordinate appears inside this pane. """
        return (x >= self.px and x < self.px + self.sx and
                y >= self.py and y < self.py + self.sy)

    def _get_cell_position(self, x, y):
        """ For a given (x,y) cell, return the CellPosition. """
        # If outside this pane, skip it.
        if x < self.px - 1 or x > self.px + self.sx or y < self.py - 1 or y > self.py + self.sy:
            return CellPosition.Outside

#        #  If inside, return that.
#        if self.is_inside(x, y):
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
