#!/usr/bin/env python

import asyncio
import weakref
import sys
import signal
import logging

from pymux.std import raw_mode
from pymux.invalidate import Redraw
from pymux.renderer import StdoutRenderer
from pymux.layout import Location
from pymux.statusbar import StatusBar
from pymux.window import Window

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=logfile, level=logging.INFO)


def log(msg):
    logfile.write(msg + '\n')
    logfile.flush()


class Client: # TODO: rename to Session
    def __init__(self):
        self.renderers = []
        self.windows = [ ]
        self.active_window = None

        self.pane_runners = [ ] # Futures

        self.status_bar = StatusBar(weakref.ref(self))
        self.create_new_window()

    def add_renderer(self, renderer):
        """ Create a renderer for this client. """
        self.renderers.append(renderer)
        self.update_size()
        return renderer

    @property
    def active_pane(self):
        if self.active_window:
            return self.active_window.active_pane
        else:
            return None

    def create_new_window(self):
        def invalidate_func(*a):
            if window == self.active_window:
                self.invalidate(*a)

        window = Window(invalidate_func)
        pane = window.create_new_pane()
        self.active_window = window
        self.windows.append(window)

        self._run_pane(self.active_window, pane)
        self.update_size()

        self.invalidate(Redraw.All)

    def invalidate(self, *a):
        for r in self.renderers:
            r.invalidate(*a)

    def update_size(self):
        """
        Take the sizes of all the renderers, and scale the layout according to
        the smallest client.
        """
        sizes = [ r.get_size() for r in self.renderers ]
        if sizes:
            self.sx = min(s.x for s in sizes)
            self.sy = min(s.y for s in sizes)
        else:
            self.sx = 80
            self.sy = 40

        # Honor minimal size. TODO: show "Too small" in that case.
        if self.sx < 10:
            self.sx = 10
        if self.sy < 3:
            self.sy = 3

        for window in self.windows:
            # Resize windows. (keep one line for the status bar.)
            window.layout.set_location(Location(0, 0, self.sx, self.sy - 1))

        self.invalidate(Redraw.All)

    # Commands

    def _run_pane(self, window, pane):
        # Create coroutine which handles the creation/deletion of this pane in
        # the session.
        f = None

        @asyncio.coroutine
        def run_pane():
            yield from pane.run()
            self.pane_runners.remove(f)

            # Focus next pane in this window when this one was focussed.
            if len(window.panes) > 1 and window.active_pane == pane:
                window.focus_next()

            pane.parent.remove(pane)
            window.panes.remove(pane)

            # When this window doesn't contain any panes anymore. Remove window
            # from session.
            if len(window.panes) == 0:
                self.windows.remove(window)
                if window == self.active_window:
                    if self.windows:
                        self.active_window = self.windows[0]
                    else:
                        self.active_window = None

            self.invalidate(Redraw.All)

        f = asyncio.async(run_pane())
        self.pane_runners.append(f)

    @asyncio.coroutine
    def run(self):
        """ Run until we don't have panes anymore. """
        while True:
            runners = self.pane_runners
            if runners:
                #yield from asyncio.gather(* runners)

                # Wait until one pane is ready
                done, pending = yield from asyncio.wait(
                        runners, return_when=asyncio.tasks.FIRST_COMPLETED)

            else:
                break

    def send_input_to_current_pane(self, data):
        if self.active_pane:
            log('Sending %r' % b''.join(data))
            self.active_pane.write_input(b''.join(data))

    def focus_next_window(self):
        if self.active_window and self.windows:
            try:
                index = self.windows.index(self.active_window) + 1
            except ValueError:
                index = 0
            self.active_window = self.windows[index % len(self.windows)]
            self.invalidate(Redraw.All)

    def split_pane(self, vsplit):
        pane = self.active_window.create_new_pane(vsplit=vsplit)
        self._run_pane(self.active_window, pane)

    def kill_current_pane(self):
        if self.active_pane:
            self.active_pane.kill_process()

    def resize_current_tile(self, direction='R', amount=1):
        self.active_pane.parent.resize_tile(direction, amount)
        self.invalidate(Redraw.All)

    def move_focus(self, direction='R'):
        self.active_window.move_focus(direction)
        self.invalidate(Redraw.Cursor | Redraw.Borders)


class InputProtocol: # TODO: inherit from protocol.
    def __init__(self, client):
        self.client = client

        self._input_parser_generator = self._input_parser()
        self._input_parser_generator.send(None)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self._process_input(data)

    def _process_input(self, char):
        log('Received input: %r' % char)
        self._send_buffer = []

        for c in char:
            self._input_parser_generator.send(bytes((c,)))

        if self._send_buffer:
            self.client.send_input_to_current_pane(self._send_buffer)

        self._send_buffer = []

    def _input_parser(self):
        while True:
            char = yield

            if char == b'\x01': # Ctrl-A
                log('Received CTRL-A')

                c2 = yield

                bindings = {
                    b'\x01': lambda: self._send_buffer.append(b'\x01'),
                    b'n': self.client.focus_next_window,
                    b'"': lambda: self.client.split_pane(vsplit=False),
                    b'%': lambda: self.client.split_pane(vsplit=True),
                    b'x': self.client.kill_current_pane,
                    b'c': self.client.create_new_window,
                    b'h': lambda: self.client.resize_current_tile('L', 4),
                    b'k': lambda: self.client.resize_current_tile('U', 4),
                    b'l': lambda: self.client.resize_current_tile('R', 4),
                    b'j': lambda: self.client.resize_current_tile('D', 4),
                    b'H': lambda: self.client.move_focus('L'),
                    b'K': lambda: self.client.move_focus('U'),
                    b'L': lambda: self.client.move_focus('R'),
                    b'J': lambda: self.client.move_focus('D'),
                    b'R': lambda: self.client.invalidate(Redraw.All),
                }
                handler = bindings.get(c2, None)
                if handler:
                    handler()
            else:
                self._send_buffer.append(char)


@asyncio.coroutine
def run():
    with raw_mode(sys.stdin):
        client = Client()
        renderer = StdoutRenderer(weakref.ref(client))
        client.add_renderer(renderer)

        def sigwinch_handler(n, frame):
            client.update_size()
            loop.call_soon(client.update_size)
        signal.signal(signal.SIGWINCH, sigwinch_handler)

        # Use a connect_read_pipe to read the input.
        input_transport, input_protocol = yield from loop.connect_read_pipe(
                            lambda:InputProtocol(client), sys.stdin)

        yield from client.run()


try:
    # Set terminal:
    sys.stdout.write('\033[?1049h') # Enter alternate screen buffer

    loop.run_until_complete(run())
    sys.stdout.write('\033[?1049l') # Quit alternate screen buffer
    sys.stdout.write('\033[?25h') # Make sure the cursor is visible again.
except Exception as e:
    log('QUIT')
    log(repr(e))
log('NORMALQUIT')
