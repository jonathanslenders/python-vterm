#!/usr/bin/env python

"""
WORK IN PROGRESS:

    this debugger, together with debugger_bootstrap.py should become an interactive
    Python debugger. On the left pane, we should have the running Python application,
    on the right pane, we should have a debugger to interrupt the other application.

"""

from asyncio.protocols import BaseProtocol
from pymux.input import InputProtocol
from pymux.log import logger
from pymux.renderer import PipeRenderer
from pymux.session import Session
from pymux.std import raw_mode
from pymux.utils import alternate_screen, call_on_sigwinch
from pymux.panes import ExecPane, BashPane
from pymux.window import Window

import docopt
import asyncio
import logging
import os
import signal
import sys
import weakref

import asyncio_amp

loop = asyncio.get_event_loop()

class PyMuxDebugInputProtocol(InputProtocol):
    def get_bindings(self):
        return {
            b'\x01': lambda: self.send_input_to_current_pane(b'\x01'),
            b'H': lambda: self.session.move_focus('L'),
            b'L': lambda: self.session.move_focus('R'),
        }


class DebugProtocol(BaseProtocol):
    def data_received(self, data):
        logger.info('Got data %r' % data)


class ApplicationPane(ExecPane):
    def _exec(self):
        os.execv('/home/jonathan/env/tulip-test2/bin/python', ['python', 'debug_wrapper.py' ])

    def _in_parent(self, pid):
        pass


class DebuggerPane(ExecPane):
    def _do_exec(self):
        os.execv('/home/jonathan/env/tulip-test2/bin/python', ['python', 'debug_client.py' ])


@asyncio.coroutine
def run():
    # Output transport/protocol
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    with raw_mode(sys.stdin.fileno()):
        # Enter alternate screen buffer
        with alternate_screen(output_transport.write):
            # Create session and renderer
            session = Session()
            renderer = PipeRenderer(weakref.ref(session), output_transport.write)
            session.add_renderer(renderer)

            # Setup layout
            window = Window()
            session.add_window(window)
            application_pane = ApplicationPane()
            debugger_pane = DebuggerPane()
            window.add_pane(application_pane)
            window.add_pane(debugger_pane, vsplit=True)

            # handle resize events
            call_on_sigwinch(session.update_size)

            # Input transport/protocol
            input_transport, input_protocol = yield from loop.connect_read_pipe(
                                lambda:PyMuxDebugInputProtocol(session), sys.stdin)

            # Wait for everything to finish
            yield from asyncio.gather(
                    asyncio.async(application_pane.run()),
                    asyncio.async(debugger_pane.run()))


def start_standalone():
    loop.run_until_complete(run())


if __name__ == '__main__':
    start_standalone()
