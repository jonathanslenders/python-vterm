#!/usr/bin/env python

import asyncio
import logging
import asyncio_amp
import weakref

from pymux.session import Session
from pymux.amp_commands import WriteOutput, SendKeyStrokes, GetSessions, SetSize, DetachClient
from pymux.input import InputProtocol
from pymux.renderer import AmpRenderer
from pymux.log import logger

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=logfile, level=logging.INFO)


class ServerProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.renderer = None
        self.input_protocol = None
        self.client_width = 80
        self.client_height = 40

    def connection_made(self, transport):
        super().connection_made(transport)
        self.input_protocol = InputProtocol(self.session) # TODO: pass weakref of session
        self.renderer = AmpRenderer(weakref.ref(self.session), self) # TODO: pass weakref of session
        self.session.add_renderer(self.renderer)

    def connection_lost(self, exc):
        super().connection_lost(exc)
        self.input_protocol = None

        # Remove renderer
        self.session.remove_renderer(self.renderer)
        self.renderer = None

    @SendKeyStrokes.responder
    def _received_keystrokes(self, data):
        if self.input_protocol:
            self.input_protocol.data_received(data)

    @SetSize.responder
    def _size_set(self, width, height):
        logger.info('Received size: %s %s' % (width, height))
        self.client_width = width
        self.client_height = height
        loop.call_soon(self.session.update_size)

    @asyncio.coroutine
    def send_output_to_client(self, data):
        result = yield from self.call_remote(WriteOutput, data=data.encode('utf-8'))


@asyncio.coroutine
def run():
    session = Session()
    connections = []

    def factory():
        protocol = ServerProtocol(session)
        connections.append(protocol)
        return protocol

    # AMP Listener.
    server = yield from loop.create_server(factory, 'localhost', 4376)

    yield from session.run()

    # Disconnect all clients.
    for c in connections:
        result = yield from c.call_remote(DetachClient)

if __name__ == '__main__':
    loop.run_until_complete(run())

