#!/usr/bin/env python

from asyncio.protocols import BaseProtocol
from asyncio.protocols import BaseProtocol
from pymux.amp_commands import WriteOutput, SendKeyStrokes, GetSessions, SetSize, DetachClient
from pymux.session import Session
from pymux.utils import get_size

import asyncio
import signal
import asyncio_amp
import os
from pymux.std import raw_mode
import sys

loop = asyncio.get_event_loop()


class ClientProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, write_func):
        super().__init__()
        self._write = write_func

    def connection_made(self, transport):
        super().connection_made(transport)
        self.send_size()

    @WriteOutput.responder
    def _write_output(self, data):
        self._write(data)

    @DetachClient.responder
    def _detach_client(self):
        loop.stop()

    def send_input(self, data):
        asyncio.async(self.call_remote(SendKeyStrokes, data=data))

    def send_size(self):
        rows, cols = get_size(sys.stdout)
        asyncio.async(self.call_remote(SetSize, height=rows, width=cols))


class InputProtocol(BaseProtocol):
    def __init__(self, send_input_func):
        self._send_input = send_input_func

    def data_received(self, data):
        self._send_input(data)


@asyncio.coroutine
def run():
    output_transport, output_protocol = yield from loop.connect_write_pipe(
                    BaseProtocol, os.fdopen(0, 'wb', 0))

    # Establish server connection
    transport, protocol = yield from loop.create_connection(
                    lambda:ClientProtocol(output_transport.write), 'localhost', 4376)

    # Input
    input_transport, input_protocol = yield from loop.connect_read_pipe(
                    lambda:InputProtocol(protocol.send_input), os.fdopen(0, 'rb', 0))

    # When the size changed
    def sigwinch_handler(n, frame):
        loop.call_soon(protocol.send_size)
    signal.signal(signal.SIGWINCH, sigwinch_handler)


if __name__ == '__main__':
    with raw_mode(0):
        sys.stdout.write('\033[?1049h') # Enter alternate screen buffer
        loop.run_until_complete(run())
        loop.run_forever()
        sys.stdout.write('\033[?1049l') # Quit alternate screen buffer
        sys.stdout.write('\033[?25h') # Make sure the cursor is visible again.
