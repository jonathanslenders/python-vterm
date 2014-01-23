#!/usr/bin/env python

from asyncio.protocols import BaseProtocol
from pymux.input import InputProtocol
from pymux.log import logger
from pymux.renderer import PipeRenderer
from pymux.session import PyMuxSession
from pymux.std import raw_mode
from pymux.utils import alternate_screen, call_on_sigwinch

import asyncio
import logging
import os
import signal
import sys
import weakref

loop = asyncio.get_event_loop()


@asyncio.coroutine
def run():
    # Output transport/protocol
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    with raw_mode(sys.stdin.fileno()):
        # Enter alternate screen buffer
        with alternate_screen(output_transport.write):
            # Create session and renderer
            session = PyMuxSession()
            renderer = PipeRenderer(weakref.ref(session), output_transport.write)
            session.add_renderer(renderer)

            # handle resize events
            call_on_sigwinch(session.update_size)

            # Input transport/protocol
            input_transport, input_protocol = yield from loop.connect_read_pipe(
                                lambda:InputProtocol(session), sys.stdin)

            yield from session.run()


def start_standalone():
    loop.run_until_complete(run())


if __name__ == '__main__':
    start_standalone()
