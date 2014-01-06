from collections import namedtuple
import weakref
from log import logger

Location = namedtuple('Position', 'px py sx sy')


def divide_equally(available, amount):
    result = [0] * amount
    i = 0
    for _ in range(available):
        result[i] += 1
        i = (i + 1) % amount
    return result


class Container:
    def __init__(self):
        # Undefined to start with
        self.location = None

        self.children = []
        self._get_parent = lambda:None # Weakref to parent

    @property
    def panes(self):
        for c in self.children:
            yield from c.panes

    @property
    def parent(self):
        return self._get_parent()

    def set_location(self, location):
        self.location = location
        self.resize()

    def resize(self):
        for c in self.children:
            c.set_location(self.location)

    def add(self, child):
        """ Add child container. """
        if child.parent is not None:
            raise Exception('%r already has a parent: %r' % (child, child.parent))

        self.children.append(child)

        # Create weak reference to parent
        child._get_parent = weakref.ref(self)

        # Trigger resize
        self.resize()

    def remove(self, child):
        self.children.remove(child)

        # Trigger resize
        self.resize()


class TileContainer(Container):
    """
    Base class for a container that can do horizontal and vertical splits.
    """
    def __init__(self):
        super().__init__()
        self.children = []

    def split(self, pane_container, horizontal=False, after_child=None):
        """
        Split and add pane_container.
        """
        # Create split instance
        split = HSplit() if horizontal else HSplit()

        if after_child is None:
            index = 0
        else:
            assert after_child in self.children

            index = self.children.find(after_child)
            after_child._get_parent = lambda:None
            split.add(after_child)

        split.add(pane_container)


class VSplit(TileContainer):
    """ One pane at the left, one at the right. """
    def resize(self):
        if self.location and self.children:
            # Reserve space for the borders.
            available_space = self.location.sy - (len(self.children) - 1)

            # Now device equally.
            sizes = divide_equally(available_space, len(self.children))

            offset = 0
            for c, size in zip(self.children, sizes):

                c.set_location(Location(
                        self.location.px,
                        self.location.py + offset,
                        self.location.sx,
                        size))
                offset += size + 1


class HSplit(TileContainer):
    """ One pane at the top, one at the bottom. """
    def __init__(self, sx, sy):
        super().__init__(sx, sy)
        self._split_pos = int((sy - 1) / 2) # We reserve one space for the border.

    @property
    def widths(self):
        return [ self.sx, self.sx ]

    @property
    def height(self):
        return [ self._split_pos, self.sy - self._split_pos - 1 ]
