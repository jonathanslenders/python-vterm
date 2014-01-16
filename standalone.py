#!/usr/bin/env python

from asyncio.protocols import BaseProtocol
from pymux.input import InputProtocol
from pymux.log import logger
from pymux.renderer import PipeRenderer
from pymux.session import Session
from pymux.std import raw_mode

import asyncio
import logging
import os
import signal
import sys
import weakref

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=logfile, level=logging.INFO)


@asyncio.coroutine
def run():
    # Output transport/protocol
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    # Enter alternate screen buffer
    output_transport.write(b'\033[?1049h')

    # Create session and renderer
    session = Session()
    renderer = PipeRenderer(weakref.ref(session), output_transport.write)
    session.add_renderer(renderer)

    # handle resize events
    def sigwinch_handler(n, frame):
        session.update_size()
        loop.call_soon(session.update_size)
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    # Input transport/protocol
    input_transport, input_protocol = yield from loop.connect_read_pipe(
                        lambda:InputProtocol(session), sys.stdin)

    yield from session.run()

    # Exit alternate screen buffer and make cursor visible again.
    output_transport.write(b'\033[?1049l')
    output_transport.write(b'\033[?25h')


if __name__ == '__main__':
    with raw_mode(sys.stdin.fileno()):
        try:
            loop.run_until_complete(run())
        except Exception as e:
            logger.error('Error')
            logger.error(repr(e))
        logger.info('Normal Quit')
