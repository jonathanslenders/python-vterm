

class Redraw:
    """ Invalidate bitmasks. """
    Nothing = 0
    Cursor = 1
    Borders = 2
    Panes = 4
    StatusBar = 8 # TODO: implement status bar.
    ClearFirst = 16

    All = Borders | Panes | StatusBar | ClearFirst
