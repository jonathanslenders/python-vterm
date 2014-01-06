import sys
import os
import asyncio
import fcntl
import pyte

from log import logger
from panes import Position, CellPosition
from invalidate import Redraw

loop = asyncio.get_event_loop()

class BorderType:
    """ Position of a cell in a window. """
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

    NoBorder = 0


CellPositionToBorderType = {
    CellPosition.TopBorder: BorderType.Horizontal,
    CellPosition.BottomBorder: BorderType.Horizontal,
    CellPosition.LeftBorder: BorderType.Vertical,
    CellPosition.RightBorder: BorderType.Vertical,

    CellPosition.TopLeftBorder: BorderType.TopLeft,
    CellPosition.TopRightBorder: BorderType.TopRight,
    CellPosition.BottomLeftBorder: BorderType.BottomLeft,
    CellPosition.BottomRightBorder: BorderType.BottomRight,

    CellPosition.Outside: BorderType.NoBorder
}

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
}

reverse_colour_code = dict((v,k) for k,v in pyte.graphics.FG.items())
reverse_bgcolour_code = dict((v,k) for k,v in pyte.graphics.BG.items())



class Renderer:
    def __init__(self, layout):
        # Invalidate state
        self._invalidated = False
        self._invalidate_parts = 0
        self.layout = layout

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

        # Make sure that stdout is blocking when we write to it.
        # By calling connect_read_pipe on stdin, asyncio will mark the stdin as
        # non blocking (in asyncio.unix_events._set_nonblocking). This causes
        # stdout to be nonblocking as well.  That's fine, but it's never a good
        # idea to write to a non blocking stdout, as it will often raise the
        # "write could not complete without blocking" error and not write to
        # stdout.
        fd = sys.stdout.fileno()
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        new_flags = flags & ~ os.O_NONBLOCK
        fcntl.fcntl(fd, fcntl.F_SETFL, new_flags)

        try:
            sys.stdout.write(''.join(self._repaint()))
            sys.stdout.flush()
        except Exception as e:
            logger.error("%r" % e)
        finally:
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
            for pane in self.layout.panes:
                data += self._repaint_pane(pane, only_dirty=only_dirty)

        # Draw borders
        if self._invalidate_parts & Redraw.Borders:
            logger.info('Redraw borders')
            data += self._repaint_border()

        # Set cursor to right position (if visible.)
        active_pane = self.layout.active_pane

        if active_pane and not self.layout.active_pane.screen.cursor.hidden:
            ypos, xpos = active_pane.cursor_position
            write('\033[%i;%iH' % (active_pane.py + ypos+1, active_pane.px + xpos+1))

            # Make cursor visible
            write('\033[?25h')

        self._invalidate_parts = Redraw.Nothing

        return data

    def _repaint_border(self):
        data = []
        write = data.append

        for y in range(0, self.layout.location.sy):
            write('\033[%i;%iH' % (y+1, 0))

            for x in range(0, self.layout.location.sx):
                border_type, is_active = self._check_cell(x, y)
                if border_type:

                    write('\033[0m')
                    if is_active:
                        write('\033[0;%im' % 32)

                    write(BorderSymbols[border_type])

        return data

    def _repaint_pane(self, pane, only_dirty=True):
        data = []
        write = data.append

        ###test = []
        ###for idx, line in enumerate(pane.screen.display, 1):
        ###    test.append("{0:2d} {1} ¶\n".format(idx, line))
        ###log(''.join(test))

        for l in range(len(pane.screen)):
            if not only_dirty or l in pane.screen.dirty:
                lines = pane.screen[l]

                # Position cursor for line.
                write('\033[%i;%iH' % (pane.py + l + 1, pane.px + 1))

                for char in lines:
                    write('\033[0m')

                    if char.fg != 'default':
                        colour_code = reverse_colour_code[char.fg]
                        write('\033[0;%im' % colour_code)

                    if char.bg != 'default':
                        colour_code = reverse_bgcolour_code[char.bg]
                        write('\033[%im' % colour_code)

                    if char.bold:
                        write('\033[1m')

                    if char.underscore:
                        write('\033[4m')

                    if char.reverse:
                        write('\033[7m')

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

        for pane in self.layout.panes:
            cell_position = pane._check_cell(x, y)

            # If inside pane:
            if cell_position == CellPosition.Inside:
                return BorderType.NoBorder

            mask |= CellPositionToBorderType[cell_position]

            is_active = is_active or (cell_position and pane == self.layout.active_pane)

        return mask, is_active

