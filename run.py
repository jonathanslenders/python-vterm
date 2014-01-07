import asyncio
import sys
import signal
import logging

from pymux.std import raw_mode
from pymux.invalidate import Redraw
from pymux.renderer import Renderer
from pymux.panes import Pane
from pymux.utils import get_size
from pymux.layout import TileContainer, VSplit, Location

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=logfile, level=logging.INFO)


def log(msg):
    logfile.write(msg + '\n')
    logfile.flush()


class Client: # TODO: rename to window.
    def __init__(self):
        self.pane_runners = [ ] # Futures
        self.active_pane = None

        self._input_parser_generator = self._input_parser()
        self._input_parser_generator.send(None)

        # Create new layout with vsplit.
        sy, sx = get_size(sys.stdout)
        log('Client created size=%s %s' % (sx, sy))

        self.layout = TileContainer()
        self.layout.set_location(Location(0, 0, sx, sy))

        self.vsplit = VSplit()
        self.layout.add(self.vsplit)

        self.renderer = Renderer(self)

    def update_size(self):
        sy, sx = get_size(sys.stdout)
        self.layout.set_location(Location(0, 0, sx, sy))
        self.renderer.invalidate(Redraw.Borders)

    def new_pane(self, vsplit=False):
        pane = Pane('/bin/bash', lambda: self.renderer.invalidate(Redraw.Panes))

        if self.active_pane:#  and self.active_pane.parent:
            parent = self.active_pane.parent
            log('parent=' + str(parent))
            assert isinstance(parent, TileContainer)
            parent.split(pane, vsplit=vsplit, after_child=self.active_pane)
        else:
            self.layout.add(pane)
            assert pane.parent

        self.active_pane = pane
        assert self.active_pane.parent, 'no active pane parent'

        self.renderer.invalidate(Redraw.All)

        #
        @asyncio.coroutine
        def run_pane():
            yield from pane.start()
            self.active_pane.parent.remove(self.active_pane)

            self.pane_runners.remove(f)
            self.renderer.invalidate(Redraw.All)
            self.focus_next()

        f = asyncio.async(run_pane())
        self.pane_runners.append(f)

    @property
    def panes(self):
        return self.layout.panes

    # Commands

    def focus_next(self):
        if self.active_pane:
            panes = list(self.layout.panes)
            if panes:
                try:
                    index = panes.index(self.active_pane) + 1
                except ValueError:
                    index = 0
                self.active_pane = panes[index % len(panes)]
                self.renderer.invalidate(Redraw.Cursor | Redraw.Borders)

    @asyncio.coroutine
    def run(self):
        """ Run until we don't have panes anymore. """
        self.new_pane()

        while self.pane_runners:
            yield from asyncio.gather(* self.pane_runners)

    def process_input(self, char):
        log('Received input: %r' % char)
        self._send_buffer = []

        for c in char:
            self._input_parser_generator.send(bytes((c,)))

        if self._send_buffer and self.active_pane:
            log('Sending %r' % b''.join(self._send_buffer))
            self.active_pane.write_input(b''.join(self._send_buffer))
            self._send_buffer = []

    def _input_parser(self):
        while True:
            char = yield

            if char == b'\x01': # Ctrl-A
                log('Received CTRL-A')

                c2 = yield

                # Twice pressed escape char
                if c2 == b'\x01':
                    self._send_buffer.append(char)

                elif c2 == b'n':
                    self.focus_next()

                elif c2 == b'"':
                    self.new_pane()

                elif c2 == b'%':
                    self.new_pane(vsplit=True)

                elif c2 == b'x':
                    if self.active_pane:
                        self.active_pane.kill_process()

                elif c2 == b'R':
                    self.renderer.invalidate(Redraw.All)
            else:
                self._send_buffer.append(char)


class InputProtocol: # TODO: inherit from protocol.
    def __init__(self, callback):
        self.callback = callback

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        @asyncio.coroutine
        def process():
            self.callback(data)
        asyncio.async(process())



@asyncio.coroutine
def run():
    with raw_mode(sys.stdin):
        client = Client()
        client.new_pane()

        def sigwinch_handler(n, frame):
            client.update_size()
            loop.call_soon(client.update_size)
        signal.signal(signal.SIGWINCH, sigwinch_handler)

        # Use a connect_read_pipe to read the input.
        input_transport, input_protocol = yield from loop.connect_read_pipe(
                            lambda:InputProtocol(client.process_input), sys.stdin)

        yield from client.run()


try:
    # Set terminal:
    sys.stdout.write('\033[?1049h') # Enter alternate screen buffer

    loop.run_until_complete(run())
    sys.stdout.write('\033[?1049l') # Quit alternate screen buffer
except Exception as e:
    log('QUIT')
    log(repr(e))
log('NORMALQUIT')
