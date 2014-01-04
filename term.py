class GridCell:
    def __init__(self, char):
        self.attr = ''
        self.flags = ''
        self.fg = '0'
        self.bg = '0'
        self.xstate = (1 << 4) | 1 # Top 4 bits width, bottom 4 bits size.
        self.xdata = char # The character

    def set(self, utf8_data): # See: grid-cell.c
        self.xstate = (utf8_data.width << 4) | utf8_data.size

class GridLine:
    cellsize = 0
    celldata = []

class Grid:
    def __init__(self, sx, sy):
        self.sx = sx
        self.sy = sy
        self.hsize = 0
        self.hlimit = 0
        self.linedata = []


class Screen:
    def __init__(self, sx, sy, hlimit):
        self.cx = 0 # Cursor x
        self.cy = 0 # Cursor y

        self.title = None
        self.grid = Grid(sx, sy, hlimit)
        self.cstyle  = 0 # Cursor style
        self.ccolour = '' # Cursor colour string
        self.rupper = 0 # Scroll region top
        self.rlower = self.grid.sy - 1 # Scroll region bottom
        self.mode = MODE_CURSOR | MODE_WRAP

    def set_cursor_style(self, style):
        if style <= 6:
            self.cstyle = style

    def set_cursor_colour(self, colour_string):
        self.ccolour = colour_string

    def resize(self, sx, sy, reflow=True):
        if sx < 1:
            sx = 1
        if sy < 1:
            sy = 1

        if sx != self.grid.sx:
            self.resize_x(sx) # screen_resize_x in tmux

        if sy != self.grid.sy:
            self.resize_y(sy) # screen_resize_y in tmux

        if reflow:
            self.reflow(sx)

class ScreenWriteCtx:
    def __init__(self):
        pass

    def write_putc(self, grid_cell):
        self.write_cell(grid_cell)

    #def write_puts(self, screen_write_ctx, grid_cell, format

    def write_backspace(self):
        pass

    def write_insertcharacter(self, nx):
        """ Insert nx characters """
        pass

    def write_deletecharacter(self, nx):
        """ Delete nx characters """
        pass

    def write_clearcharacter(self, nx):
        """ Clear nx characters """
        pass

    def write_insertline(self, ny):
        """ Insert ny lines """
        pass

    def write_deleteline(self, ny):
        """ Delete ny lines """
        pass

    def write_clearline(self):
        """ Clear line at cursor """
        pass

    def write_clearendofline(self):
        """ Clear to end of line from cursor """
        pass

    def write_clearstartofline(self):
        """ Clear to start of line from cursor. """
        pass

    def write_cursormove(self, px, py):
        """ Move cursor to px,py """
        pass

    def write_reverseindex(self, px, py):
        """ Reverse index (up with scroll """
        pass

    def write_scrollregion(self, rupper, rlower):
        """ Reverse index (up with scroll """
        pass

    def write_linefeed(self, wrapped):
        """ Line feed. """
        pass

    def write_carriagereturn(self, wrapped):
        """ Carriage return (cursor to start of line). """
        pass

    def write_clearendofscreen(self):
        """ Clear to end of screen from cursor. """
        pass

    def write_clearstartofscreen(self):
        """ Clear to start of screen from cursor. """
        pass

    def write_clearscreen(self):
        """ Clear entire screen. """
        pass

    def write_clearhistory(self):
        """ Clear entire history. """
        pass

    def write_cell(self, grid_cell):
        """ Clear entire history. """
        # ...
        pass
