#!/usr/bin/env python

from asyncio.protocols import BaseProtocol

from pymux.amp_commands import WriteOutput, SendKeyStrokes, GetSessions, SetSize, DetachClient, AttachClient
from pymux.session import Session
from pymux.std import raw_mode
from pymux.utils import get_size

import asyncio
import asyncio_amp
import os
import signal
import sys

__all__ = ('start_client', )

loop = asyncio.get_event_loop()


class ClientProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, output_transport):
        super().__init__()
        self._output_transport = output_transport
        self._write = output_transport.write

    def connection_made(self, transport):
        super().connection_made(transport)
        self.send_size()

    @WriteOutput.responder
    def _write_output(self, data):
        self._write(data)

    @DetachClient.responder
    def _detach_client(self):
        # Wait for the loop to finish all writes
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
def _run():
    output_transport, output_protocol = yield from loop.connect_write_pipe(
                    BaseProtocol, os.fdopen(0, 'wb', 0))

    # Establish server connection
    transport, protocol = yield from loop.create_connection(
                    lambda:ClientProtocol(output_transport), 'localhost', 4376)

    # Tell the server that we want to attach to the session
    yield from protocol.call_remote(AttachClient)

    # Input
    input_transport, input_protocol = yield from loop.connect_read_pipe(
                    lambda:InputProtocol(protocol.send_input), os.fdopen(0, 'rb', 0))

    # When the size changed
    def sigwinch_handler(n, frame):
        loop.call_soon(protocol.send_size)
    signal.signal(signal.SIGWINCH, sigwinch_handler)


def start_client():
    # Enter alternate screen buffer
    sys.stdout.write('\033[?1049h')
    sys.stdout.flush()

    # Run client event loop in raw mode
    with raw_mode(0):
        loop.run_until_complete(_run())
        loop.run_forever()

    # Quit alternate screen buffer. (need to reopen stdout, because it was set
    # non blocking by asynio)
    out = os.fdopen(0, 'wb', 0)
    out.write(b'\033[?25h') # Make sure the cursor is visible again.
    out.write(b'\033[?1049l') # Quit alternate screen buffer
    out.flush()


if __name__ == '__main__':
    start_client()
