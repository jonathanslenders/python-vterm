import sys
import os
import asyncio
import fcntl
import pyte
import datetime

from .log import logger
from .panes import CellPosition, BorderType
from .invalidate import Redraw

loop = asyncio.get_event_loop()


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

reverse_colour_code = dict((v,k) for k,v in pyte.graphics.FG.items())
reverse_bgcolour_code = dict((v,k) for k,v in pyte.graphics.BG.items())



class Renderer:
    def __init__(self, client):
        # Invalidate state
        self._invalidated = False
        self._invalidate_parts = 0
        self.client = client

    def invalidate(self, invalidate_parts=Redraw.All):
        """ Schedule repaint. """
        self._invalidate_parts |= invalidate_parts

        if not self._invalidated:
            logger.info('Scheduling repaint: %r' % self._invalidate_parts)
            self._invalidated = True
            loop.call_soon(self.repaint)

    def repaint(self):
        """ Do repaint now. """
        self._invalidated = False
        start = datetime.datetime.now()

        # Make sure that stdout is blocking when we write to it.  By calling
        # connect_read_pipe on stdin, asyncio will mark the stdin as non
        # blocking (in asyncio.unix_events._set_nonblocking). This causes
        # stdout to be nonblocking as well.  That's fine, but it's never a good
        # idea to write to a non blocking stdout, as it will often raise the
        # "write could not complete without blocking" error and not write to
        # stdout.
        fd = sys.stdout.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        new_flags = flags & ~ os.O_NONBLOCK
        fcntl.fcntl(fd, fcntl.F_SETFL, new_flags)

        try:
            data = ''.join(self._repaint())
            sys.stdout.write(data)
            sys.stdout.flush()

            logger.info('Redraw generation done in %ss, bytes=%i' %
                    (datetime.datetime.now() - start, len(data)))
        finally:
            # Make blocking again
            fcntl.fcntl(fd, fcntl.F_SETFL, flags)

    def _repaint(self):
        data = []
        write = data.append

#        if self._invalidate_parts & Redraw.ClearFirst:
#            write('\u001b[2J') # Erase screen

        # Hide cursor
        write('\033[?25l')

        # Draw panes.
        if self._invalidate_parts & Redraw.Panes:
            only_dirty = not bool(self._invalidate_parts & Redraw.ClearFirst)
            logger.info('Redraw panes')
            for pane in self.client.panes:
                data += self._repaint_pane(pane, only_dirty=only_dirty)

        # Draw borders
        if self._invalidate_parts & Redraw.Borders:
            logger.info('Redraw borders')
            data += self._repaint_border()

        # Set cursor to right position (if visible.)
        active_pane = self.client.active_pane

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

        # Draw status bar
        if self._invalidate_parts & Redraw.StatusBar:
            data += self._repaint_status_bar()

        self._invalidate_parts = Redraw.Nothing

        return data

    def _repaint_border(self):
        data = []
        write = data.append

        for y in range(0, self.client.layout.location.sy):
            write('\033[%i;%iH' % (y+1, 0))

            for x in range(0, self.client.layout.location.sx):
                border_type, is_active = self._check_cell(x, y)

                if border_type and border_type != BorderType.Inside:
                    write('\033[%i;%iH' % (y+1, x+1)) # XXX: we don't have to send this every time. Optimize.
                    write('\033[0m') # Reset colour

                    if is_active:
                        write('\033[0;%im' % 32)

                    write(BorderSymbols[border_type])

        return data

    def _repaint_status_bar(self):
        data = []
        write = data.append

        # Go to bottom line
        write('\033[%i;0H' % self.client.sy)

        # Set background
        write('\033[%im' % 43) # Brown

        # Set foreground
        write('\033[%im' % 30) # Black

        # Set bold
        write('\033[1m')

        text = self.client.status_bar.left_text
        rtext = self.client.status_bar.right_text
        space_left = self.client.sx - len(text) - len(rtext)

        text += ' ' * space_left + rtext
        text = text[:self.client.sx]
        write(text)

        return data

    def _repaint_pane(self, pane, only_dirty=True):
        data = []
        write = data.append

        #test = []
        #for idx, line in enumerate(pane.screen.display, 1):
        #    test.append("{0:2d} {1} ¶\n".format(idx, line))
        #logger.info(''.join(test))

        last_fg = 'default'
        last_bg = 'default'
        last_bold = False
        last_underscore = False
        last_reverse = False

        write('\033[0m')

        for l in range(len(pane.screen)):
            if not only_dirty or l in pane.screen.dirty:
                line = pane.screen[l]

                    # TODO: trim spaces on the right. If there is space until
                    # the right margin, ig

                # Position cursor for line.
                write('\033[%i;%iH' % (pane.py + l + 1, pane.px + 1))


                for char in line:
                    # If the bold/underscore/reverse parameters are reset. Always use global reset.
                    if (last_bold and not char.bold) or (last_underscore and not char.underscore) or (last_reverse and not char.reverse):
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
        pane.screen.dirty = set()

        return data

    def _check_cell(self, x, y):
        """ For a given (x,y) cell, return the pane to which this belongs, and
        the type of border we have there.

        :returns: BorderType
        """
        # Create mask: set bits when the touching cells are borders.
        mask = 0
        is_active = False

        for pane in self.client.panes:
            border_type = pane._get_border_type(x, y)

            # If inside pane:
            if border_type == BorderType.Inside:
                return border_type, False
            assert CellPosition.Outside == 0

            mask |= border_type

            is_active = is_active or (border_type and pane == self.client.active_pane)

        #border_type = CellPositionToBorderType[mask]

        return mask, is_active

