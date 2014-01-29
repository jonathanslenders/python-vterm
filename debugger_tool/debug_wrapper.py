#!/usr/bin/env python
"""
Wrapper around process to make it debuggable through AMP commands.

This will do several things:
- create read and write pipes for communication with the Process.
- fork itself, and call execv to spawn the child process
- run an AMP server to control the child process.

This wrapper should always run in Python3.3, but the child can be a Python2
process.
"""

from asyncio.protocols import BaseProtocol
from asyncio.streams import open_connection
from debugger_commands import Continue, Next, Step, Breaking

import asyncio
import asyncio_amp
import docopt
import json
import os
import socket

doc = \
"""Usage:
  debug_wrapper.py debug PYTHONFILE
  debug_wrapper.py -h | --help
"""


class DebuggerAMPServerProtocol(asyncio_amp.AMPProtocol):
    """
    AMP Debug server.
    Exposes some AMP commands for controlling the process.
    """
    def __init__(self, debugger, done_callback):
        super().__init__()
        self.debugger = debugger
        self.done_callback = done_callback

    def connection_lost(self, exc):
        super().connection_lost(exc)
        self.done_callback()

    @Continue.responder
    @asyncio.coroutine
    def _continue(self):
        yield from self.debugger.send_to_process({ 'action': 'continue' })

    @Next.responder
    @asyncio.coroutine
    def _next(self):
        yield from self.debugger.send_to_process({ 'action': 'next' })

    @Step.responder
    @asyncio.coroutine
    def _step(self):
        yield from self.debugger.send_to_process({ 'action': 'step' })

    def handle_packet_from_process(self, data):
        if data['action'] == 'breaking':
            asyncio.async(self.call_remote(Breaking,
                    line=data['data']['line'],
                    filename=data['data']['filename'],
                    func_name=data['data']['func_name']))


class Debugger:
    def __init__(self, pythonfile):
        self.pythonfile = pythonfile

        # Open socketpair for communication with child process.
        self.parent_socket, self.child_socket = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        self._connected_protocols = []

    @asyncio.coroutine
    def run(self):
        """
        The main coroutine.
        """
        # Open parent socket.
        stream_reader, self._stream_writer = yield from open_connection(sock=self.parent_socket)

        # Run receiver loop.
        @asyncio.coroutine
        def receiver_loop():
            while True:
                line = yield from stream_reader.readline()
                self.handle_packet_from_process(json.loads(line.decode('utf-8')))
        asyncio.async(receiver_loop())

        try:
            # Start AMP server
            def amp_factory():
                protocol = DebuggerAMPServerProtocol(self, lambda: self._connected_protocols.remove(protocol))
                self._connected_protocols.append(protocol)
                return protocol

            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind('/tmp/python-debugger')
            self.amp_server = yield from loop.create_server(amp_factory, sock=server)

            # Start subprocess in fork
            pid = os.fork()
            if pid == 0:
                os.execv('/usr/bin/python', ['python', 'debugger_bootstrap.py',
                                    str(self.child_socket.fileno()), self.pythonfile ])
            else:
                self.child_socket.close()
                pid, status = yield from loop.run_in_executor(None, lambda:os.waitpid(pid, 0))

        finally:
            # Close socket
            server.close()
            print('removing socket')
            os.remove('/tmp/python-debugger')

    @asyncio.coroutine
    def send_to_process(self, data):
        """
        Send packet to child process through pipe, serialized as JSON.
        """
        self._stream_writer.write(json.dumps(data).encode('utf-8') + b'\n')
        yield from self._stream_writer.drain()

    def handle_packet_from_process(self, data):
        """
        Got packet from process.
        Handle and broadcast to all connected debugger clients.
        """
        for protocol in self._connected_protocols:
            protocol.handle_packet_from_process(data)


if __name__ == '__main__':
    a = docopt.docopt(doc)
    if a['PYTHONFILE']:
        loop = asyncio.get_event_loop()
        loop.run_until_complete(Debugger(a['PYTHONFILE']).run())
