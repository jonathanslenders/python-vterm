from asyncio.protocols import BaseProtocol
from cmdline import CommandLine
from debugger_commands import Next, Continue, Step, Breaking
from pymux.std import raw_mode

import asyncio
import asyncio_amp
import os
import socket
import sys
import termcolor

loop = asyncio.get_event_loop()


class DebugClientProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, debugger_client):
        super().__init__()
        self._debugger_client = debugger_client

    def connection_lost(self, exc):
        super().connection_lost(exc)
        self._debugger_client.process_done_callback()

    def next(self):
        """ Tell process to go to the next line. """
        asyncio.async(self.call_remote(Next))

    def step(self):
        asyncio.async(self.call_remote(Step))

    def continue_(self):
        asyncio.async(self.call_remote(Continue))

    @Breaking.responder
    def _breaking(self, line, filename, func_name):
        # Set line/file information in debugger, and redraw prompt.
        self._debugger_client.line = line
        self._debugger_client.filename = filename
        self._debugger_client.func_name = func_name
        self._debugger_client.commandline.print()


class InputProtocol(BaseProtocol):
    """
    Redirect input to command line (or other listener.)
    """
    def __init__(self, commandline):
        super().__init__()
        self.commandline = commandline
        self.commandline.print()

    def data_received(self, data):
        self.commandline.feed_data(data.decode('utf-8'))
        self.commandline.print()


class DebugPrompt(CommandLine):
    def __init__(self, debugger_client, output_transport):
        super().__init__()
        self.debugger_client = debugger_client
        self.output_transport = output_transport

    @property
    def prompt(self):
        return 'debug [%(state)s] %(file)s %(line)r > ' % {
                'state': termcolor.colored(self.debugger_client.state or '', 'green'),
                'line': self.debugger_client.line or '',
                'file': self.debugger_client.filename or '',
            }

    def print(self):
        self.output_transport.write(self.render_to_string().encode('utf-8'))

    def handle_command(self, command):
        self.output_transport.write(b'\r\n')
        if command == 'continue':
            self.output_transport.write(b'Continue!')
            self.debugger_client.amp_protocol.continue_()

        elif command == 'next':
            self.output_transport.write(b'Next!')
            self.debugger_client.amp_protocol.next()

        elif command == 'step':
            self.output_transport.write(b'Step!')
            self.debugger_client.amp_protocol.step()

        elif command == 'quit':
            self.ctrl_c()

        else:
            self.output_transport.write(b'Unknown command...')
        self.output_transport.write(b'\r\n')

    def ctrl_c(self):
        self.debugger_client.done_f.set_result(None)


class DebuggerClient:
    def __init__(self):
        self.state = 'RUNNING'
        self.line = None
        self.filename = None
        self.func_name = None
        self.amp_protocol = None

        # Create process-done future.
        self.done_f = asyncio.Future()

    def process_done_callback(self):
        self.state = 'DONE'
        self.commandline.print()

    @asyncio.coroutine
    def _run(self):
        with raw_mode(0):
            # Open stdout
            output_transport, output_protocol = yield from loop.connect_write_pipe(
                            BaseProtocol, os.fdopen(0, 'wb', 0))

            # Establish server AMP connection
            def factory():
                return DebugClientProtocol(self)

            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect('/tmp/python-debugger')
            transport, self.amp_protocol = yield from loop.create_connection(factory, sock=client)

            # Create command line
            self.commandline = DebugPrompt(self, output_transport)

            # Input
            input_transport, input_protocol = yield from loop.connect_read_pipe(
                            lambda:InputProtocol(self.commandline), os.fdopen(0, 'rb', 0))

            # Run loop and wait until we are completed.
            yield from self.done_f


def start_client():
    d = DebuggerClient()
    loop.run_until_complete(d._run())


if __name__ == '__main__':
    start_client()
