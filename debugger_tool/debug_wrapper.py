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

class DebuggerPipeProtocol(BaseProtocol):
    """
    Protocol for receiving JSON packets from the pipe which is connected to the
    debuggable child process.
    """
    def __init__(self, debugger):
        self.debugger = debugger
        self._buffer = ''

    def data_received(self, data):
        self._buffer += data.decode('utf-8')

        lines = self._buffer.split('\n')
        self._buffer = lines.pop()

        for line in lines:
            self.debugger.handle_packet_from_process(json.loads(line))


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
    def _continue(self):
        self.debugger.send_to_process({ 'action': 'continue' })

    @Next.responder
    def _next(self):
        self.debugger.send_to_process({ 'action': 'next' })

    @Step.responder
    def _step(self):
        self.debugger.send_to_process({ 'action': 'step' })

    def handle_packet_from_process(self, data):
        if data['action'] == 'breaking':
            asyncio.async(self.call_remote(Breaking,
                    line=data['data']['line'],
                    filename=data['data']['filename'],
                    func_name=data['data']['func_name']))


class Debugger:
    def __init__(self, pythonfile):
        self.pythonfile = pythonfile

        # Open pipes for extra communication with child process.
        self.from_child_read, self.from_child_write = os.pipe()
        self.from_debugger_read, self.from_debugger_write = os.pipe()
        self._connected_protocols = []

    @asyncio.coroutine
    def run(self):
        """
        The main coroutine.
        """
        # Open read and write pipes
        from_child_transport, from_child_protocol = yield from loop.connect_read_pipe(
                        lambda: DebuggerPipeProtocol(self),
                        os.fdopen(self.from_child_read, 'rb'))

        self.from_debugger_transport, self.from_debugger_protocol = yield from loop.connect_write_pipe(BaseProtocol,
                        os.fdopen(self.from_debugger_write, 'wb'))

        # Start AMP server
        def amp_factory():
            protocol = DebuggerAMPServerProtocol(self, lambda: self._connected_protocols.remove(protocol))
            self._connected_protocols.append(protocol)
            return protocol

        try:
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind('/tmp/python-debugger')
            self.amp_server = yield from loop.create_server(amp_factory, sock=server)

            # Start subprocess in fork
            pid = os.fork()
            if pid == 0:
                os.execv('/usr/bin/python', ['python', 'debugger_bootstrap.py',
                                    str(self.from_child_write), str(self.from_debugger_read), self.pythonfile ])
            else:
                pid, status = yield from loop.run_in_executor(None, lambda:os.waitpid(pid, 0))

        finally:
            # Close socket
            server.close()
            os.remove('/tmp/python-debugger')

    def send_to_process(self, data):
        """
        Send packet to child process through pipe, serialized as JSON.
        """
        self.from_debugger_transport.write(json.dumps(data).encode('utf-8') + b'\n')

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
