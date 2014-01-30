#!/usr/bin/env python

from asyncio.protocols import BaseProtocol

from .amp_commands import WriteOutput, SendKeyStrokes, GetSessions, SetSize, DetachClient, AttachClient

from libpymux.session import Session
from libpymux.std import raw_mode
from libpymux.utils import get_size, alternate_screen

import asyncio
import asyncio_amp
import os
import signal
import sys

__all__ = ('start_client', )

loop = asyncio.get_event_loop()


class ClientProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, output_transport, detach_callback):
        super().__init__()
        self._output_transport = output_transport
        self._write = output_transport.write
        self._detach_callback = detach_callback

    def connection_made(self, transport):
        super().connection_made(transport)
        self.send_size()

    @WriteOutput.responder
    def _write_output(self, data):
        self._write(data)

    @DetachClient.responder
    def _detach_client(self):
        self._detach_callback()

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
    f = asyncio.Future()

    output_transport, output_protocol = yield from loop.connect_write_pipe(
                    BaseProtocol, os.fdopen(0, 'wb', 0))

    # Establish server connection
    def factory():
        return ClientProtocol(output_transport, lambda: f.set_result(None))

    transport, protocol = yield from loop.create_connection(factory, 'localhost', 4376)

    # Input
    input_transport, input_protocol = yield from loop.connect_read_pipe(
                    lambda:InputProtocol(protocol.send_input), os.fdopen(0, 'rb', 0))

    # Send terminal size to server when it changes
    def sigwinch_handler(n, frame):
        loop.call_soon(protocol.send_size)
    signal.signal(signal.SIGWINCH, sigwinch_handler)

    with alternate_screen(output_transport.write):
        with raw_mode(0):
            # Tell the server that we want to attach to the session
            yield from protocol.call_remote(AttachClient)

            # Run loop and wait for detach command
            yield from f


def start_client():
    loop.run_until_complete(_run())


if __name__ == '__main__':
    start_client()
