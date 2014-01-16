import sys
import os
import asyncio
import fcntl
import pyte
import datetime
from collections import namedtuple

from pymux.utils import get_size

from .log import logger
from .panes import CellPosition, BorderType
from .invalidate import Redraw

loop = asyncio.get_event_loop()

RendererSize = namedtuple('RendererSize', 'x y')

BorderSymbols = {
    BorderType.Join: '┼',
    BorderType.BottomJoin: '┴',
    BorderType.TopJoin: '┬',

    BorderType.LeftJoin: '├',
    BorderType.RightJoin: '┤',

    # In the middle of a border
    BorderType.Horizontal: '─',
    BorderType.Vertical: '│',

    BorderType.BottomRight: '┘',
    BorderType.TopRight: '┐',
    BorderType.BottomLeft: '└',
    BorderType.TopLeft: '┌',

    BorderType.Outside: 'x',
}

reverse_colour_code = dict((v, k) for k, v in pyte.graphics.FG.items())
reverse_bgcolour_code = dict((v, k) for k, v in pyte.graphics.BG.items())


class Renderer:
    def __init__(self, client_ref):
        # Invalidate state
        self.get_client = client_ref # TODO: rename to session_ref
        self._last_size = None

    def get_size(self):
        raise NotImplementedError

    @asyncio.coroutine
    def _write_output(self, data):
        raise NotImplementedError

    @asyncio.coroutine
    def repaint(self, invalidated_parts, char_buffers):
        """ Do repaint now. """
        start = datetime.datetime.now()

        # Build and write output
        data = ''.join(self._repaint(invalidated_parts, char_buffers))
        yield from self._write_output(data) # TODO: make _write_output asynchronous.

        logger.info('Bytes: %r' % data)
        logger.info('Redraw generation done in %ss, bytes=%i' %
                (datetime.datetime.now() - start, len(data)))

    def _repaint(self, invalidated_parts, char_buffers):
        data = []
        write = data.append
        client = self.get_client()

        if invalidated_parts & Redraw.ClearFirst:
            write('\u001b[2J') # Erase screen

        # Hide cursor
        write('\033[?25l')

        # Draw panes.
        if invalidated_parts & Redraw.Panes and client.active_window:
            only_dirty = not bool(invalidated_parts & Redraw.ClearFirst)
            logger.info('Redraw panes')
            for pane in client.active_window.panes:
                data += self._repaint_pane(pane, only_dirty=only_dirty, char_buffer=char_buffers[pane])

        # Draw borders
        if invalidated_parts & Redraw.Borders and client.active_window:
            logger.info('Redraw borders')
            data += self._repaint_border(client)

        # Draw background.
        if invalidated_parts & Redraw.ClearFirst or self._last_size != self.get_size():
            data += self._repaint_background(client)

        # Draw status bar
        if invalidated_parts & Redraw.StatusBar:
            data += self._repaint_status_bar(client)

        # Set cursor to right position (if visible.)
        active_pane = client.active_pane

        if active_pane and not active_pane.screen.cursor.hidden:
            ypos, xpos = active_pane.cursor_position
            write('\033[%i;%iH' % (active_pane.py + ypos+1, active_pane.px + xpos+1))

            # Make cursor visible
            write('\033[?25h')

            # Set arrows in application/cursor sequences.
            # (Applications like Vim expect an other kind of cursor sequences.
            # This mode is the way of telling the VT terminal which sequences
            # it should send.)
            if (1 << 5) in active_pane.screen.mode:
                write('\033[?1h') # Set application sequences
            else:
                write('\033[?1l') # Reset

        invalidated_parts = Redraw.Nothing

        return data

    def _repaint_border(self, client):
        data = []
        write = data.append

        for y in range(0, client.sy - 1):
            write('\033[%i;%iH' % (y+1, 0))

            for x in range(0, client.sx):
                border_type, is_active = self._check_cell(client, x, y)

                if border_type and border_type != BorderType.Inside:
                    write('\033[%i;%iH' % (y+1, x+1)) # XXX: we don't have to send this every time. Optimize.
                    write('\033[0m') # Reset colour

                    if is_active:
                        write('\033[0;%im' % 32)

                    write(BorderSymbols[border_type])

        return data

    def _repaint_background(self, client):
        data = []
        size = self.get_size()

        # Only redraw background when the size has been changed.
        write = data.append

        write('\033[37m') # white fg
        write('\033[43m') # yellow bg
        width, height = size

        sx = client.sx
        sy = client.sy

        for y in range(0, height - 1):
            for x in range(0, width):
                if x >= sx or y >= sy:
                    write('\033[%i;%iH.' % (y+1, x+1))

        self._last_size = size
        return data

    def _repaint_status_bar(self, client):
        data = []
        write = data.append

        width, height = self.get_size()

        # Go to bottom line
        write('\033[%i;0H' % height)

        # Set background
        write('\033[%im' % 43) # Brown

        # Set foreground
        write('\033[%im' % 30) # Black

        # Set bold
        write('\033[1m')

        text = client.status_bar.left_text
        rtext = client.status_bar.right_text
        space_left = width - len(text) - len(rtext)
        logger.info('WIDTH=%r ' %  width)

        text += ' ' * space_left + rtext
        text = text[:width]
        write(text)

        return data

    def _repaint_pane(self, pane, only_dirty=True, char_buffer=None): # TODO: remove only_dirty
        data = []
        write = data.append

        last_fg = 'default'
        last_bg = 'default'
        last_bold = False
        last_underscore = False
        last_reverse = False
        last_pos = (-10, -10)

        write('\033[0m')

        for line_index, line_data in char_buffer.items():
            for column_index, char in line_data.items():
                # Only send position when it it's not next to the last one.
                if (line_index, column_index + pane.px) == (last_pos[0] + 1, 0):
                    write('\r\n') # Optimization for the next line
                elif (line_index, column_index) != (last_pos[0], last_pos[1] + 1):
                    write('\033[%i;%iH' % (pane.py + line_index + 1, pane.px + column_index + 1))
                                # TODO: also optimize if the last skipped character is a space.
                last_pos = (line_index, column_index)

                # If the bold/underscore/reverse parameters are reset.
                # Always use global reset.
                if (last_bold and not char.bold) or \
                                    (last_underscore and not char.underscore) or \
                                    (last_reverse and not char.reverse):
                    write('\033[0m')

                    last_fg = 'default'
                    last_bg = 'default'
                    last_bold = False
                    last_underscore = False
                    last_reverse = False

                if char.fg != last_fg:
                    colour_code = reverse_colour_code.get(char.fg, None)
                    if colour_code:
                        write('\033[0;%im' % colour_code)
                    else: # 256 colour
                        write('\033[38;5;%im' % char.fg)
                    last_fg = char.fg

                if char.bg != last_bg:
                    colour_code = reverse_bgcolour_code.get(char.bg, None)
                    if colour_code:
                        write('\033[%im' % colour_code)
                    else: # 256 colour
                        write('\033[48;5;%im' % char.bg)
                    last_bg = char.bg

                if char.bold and not last_bold:
                    write('\033[1m')
                    last_bold = char.bold

                if char.underscore and not last_underscore:
                    write('\033[4m')
                    last_underscore = char.underscore

                if char.reverse and not last_reverse:
                    write('\033[7m')
                    last_reverse = char.reverse

                write(char.data)

        return data

    def _check_cell(self, client, x, y):
        """ For a given (x,y) cell, return the pane to which this belongs, and
        the type of border we have there.

        :returns: BorderType
        """
        # Create mask: set bits when the touching cells are borders.
        mask = 0
        is_active = False

        for pane in client.active_window.panes:
            border_type = pane._get_border_type(x, y)

            # If inside pane:
            if border_type == BorderType.Inside:
                return border_type, False

            mask |= border_type
            is_active = is_active or (border_type and pane == client.active_pane)

        return mask, is_active


class PipeRenderer(Renderer):
    def __init__(self, session_ref, write_func):
        super().__init__(session_ref)
        self._write_func = write_func

    @asyncio.coroutine
    def _write_output(self, data):
        self._write_func(data.encode('utf-8'))

    def get_size(self):
        y, x = get_size(sys.stdout)
        return RendererSize(x, y)


## class StdoutRenderer(Renderer):
##     """
##     Renderer which is connected to sys.stdout.
##     """
##     @asyncio.coroutine
##     def _write_output(self, data):
##         # Make sure that stdout is blocking when we write to it.  By calling
##         # connect_read_pipe on stdin, asyncio will mark the stdin as non
##         # blocking (in asyncio.unix_events._set_nonblocking). This causes
##         # stdout to be nonblocking as well.  That's fine, but it's never a good
##         # idea to write to a non blocking stdout, as it will often raise the
##         # "write could not complete without blocking" error and not write to
##         # stdout.
##         fd = sys.stdout.fileno()
##         flags = fcntl.fcntl(fd, fcntl.F_GETFL)
##         new_flags = flags & ~ os.O_NONBLOCK
##         fcntl.fcntl(fd, fcntl.F_SETFL, new_flags)
##
##         try:
##             sys.stdout.write(data)
##             sys.stdout.flush()
##         finally:
##             # Make blocking again
##             fcntl.fcntl(fd, fcntl.F_SETFL, flags)
##
##     def get_size(self):
##         y, x = get_size(sys.stdout)
##         return RendererSize(x, y)


class AmpRenderer(Renderer):
    """
    Renderer which sends the stdout over AMP to the client.
    """
    def __init__(self, session_ref, amp_protocol):
        super().__init__(session_ref)
        self.amp_protocol = amp_protocol

    @asyncio.coroutine
    def _write_output(self, data):
        yield from self.amp_protocol.send_output_to_client(data)

    def get_size(self):
        return RendererSize(
                self.amp_protocol.client_width,
                self.amp_protocol.client_height)
