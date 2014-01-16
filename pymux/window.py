from pymux.layout import TileContainer
from pymux.invalidate import Redraw
from pymux.panes import Pane


class Window:
    _counter = 0

    def __init__(self, pane_executor, invalidate_func):
        self.layout = TileContainer()
        self.active_pane = None
        self.invalidate = invalidate_func
        self.pane_executor = pane_executor
        self.name = '' # TODO
        self.panes = []
        self.id = self._next_id()

    @classmethod
    def _next_id(cls):
        cls._counter += 1
        return cls._counter

    def create_new_pane(self, command='/bin/bash', vsplit=False):
        """
        Split the current window and create a new Pane instance.
        """
        pane = Pane(self.pane_executor, command,
                        lambda: self.invalidate(Redraw.Panes))

        if self.active_pane:
            parent = self.active_pane.parent
            assert isinstance(parent, TileContainer)
            parent.split(pane, vsplit=vsplit, after_child=self.active_pane)
        else:
            self.layout.add(pane)
            assert pane.parent

        self.active_pane = pane
        self.panes.append(pane)
        assert self.active_pane.parent, 'no active pane parent'
        self.invalidate(Redraw.All)

        return pane

    def focus_next(self):
        if self.active_pane:
            panes = list(self.panes)
            if panes:
                try:
                    index = panes.index(self.active_pane) + 1
                except ValueError:
                    index = 0
                self.active_pane = panes[index % len(panes)]
                self.invalidate(Redraw.Cursor | Redraw.Borders)

    def move_focus(self, direction):
        """
        Move the focus to another pane in this window.
        This changes `active_pane`.
        """
        assert direction in ('U', 'D', 'L', 'R')
        pos = self.active_pane.location

        if direction == 'U':
            x = pos.px
            y = pos.py - 2
        elif direction == 'D':
            x = pos.px
            y = pos.py + pos.sy + 2
        elif direction == 'L':
            x = pos.px - 2
            y = pos.py
        elif direction == 'R':
            x = pos.px + pos.sx + 2
            y = pos.py

        # Now find the pane at this location.
        for p in self.panes:
            if p.is_inside(x, y):
                self.active_pane = p
