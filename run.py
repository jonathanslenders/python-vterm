#!/usr/bin/env python

import asyncio
import weakref
import sys
import signal
import logging

from pymux.std import raw_mode
from pymux.invalidate import Redraw
from pymux.renderer import StdoutRenderer
from pymux.session import Session
from pymux.input import InputProtocol
from pymux.log import logger

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=logfile, level=logging.INFO)


@asyncio.coroutine
def run():
    with raw_mode(sys.stdin):
        client = Session()
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


if __name__ == '__main__':
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
