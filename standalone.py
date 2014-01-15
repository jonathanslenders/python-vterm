#!/usr/bin/env python

from asyncio.protocols import BaseProtocol
from pymux.input import InputProtocol
from pymux.log import logger
from pymux.renderer import StdoutRenderer, PipeRenderer
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
    # Create output transport
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    session = Session()
    #renderer = StdoutRenderer(weakref.ref(session))
    renderer = PipeRenderer(weakref.ref(session), output_transport.write)
    session.add_renderer(renderer)

    def sigwinch_handler(n, frame):
        session.update_size()
        loop.call_soon(session.update_size)
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    # Use a connect_read_pipe to read the input.
    input_transport, input_protocol = yield from loop.connect_read_pipe(
                        lambda:InputProtocol(session), sys.stdin)

    yield from session.run()

if __name__ == '__main__':
    with raw_mode(sys.stdin.fileno()):
        try:
            # Set terminal:
            sys.stdout.write('\033[?1049h') # Enter alternate screen buffer
            loop.run_until_complete(run())
            sys.stdout.write('\033[?1049l') # Quit alternate screen buffer
            sys.stdout.write('\033[?25h') # Make sure the cursor is visible again.
        except Exception as e:
            logger.error('Error')
            logger.error(repr(e))
        logger.info('Normal Quit')
