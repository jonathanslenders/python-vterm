#!/usr/bin/env python

from asyncio_amp.protocol import MAX_VALUE_LENGTH

import asyncio
import asyncio_amp
import logging
import weakref
import json

from pymux.session import PyMuxSession
from pymux.amp_commands import WriteOutput, SendKeyStrokes, GetSessions, SetSize, DetachClient, AttachClient, GetSessionInfo, NewWindow
from pymux.input import PyMuxInputProtocol
from pymux.renderer import AmpRenderer

from libpymux.log import logger


loop = asyncio.get_event_loop()


class SocketServerInputProtocol(PyMuxInputProtocol):
    def __init__(self, session, server_protocol):
        super().__init__(session)
        self.server_protocol = server_protocol

    def get_bindings(self):
        bindings = super().get_bindings()
        bindings.update({
            b'd': lambda: asyncio.async(self.server_protocol.detach()),
        })
        return bindings


class ServerProtocol(asyncio_amp.AMPProtocol):
    def __init__(self, session, done_callback):
        super().__init__()
        self.session = session
        self.done_callback = done_callback

        # When the client attaches the session.
        self.renderer = None
        self.input_protocol = None
        self.client_width = 80
        self.client_height = 40

    def connection_made(self, transport):
        super().connection_made(transport)

    def connection_lost(self, exc):
        self.input_protocol = None

        # Remove renderer
        if self.renderer:
            self.session.remove_renderer(self.renderer)
            self.renderer = None
        self.done_callback()

    @AttachClient.responder
    def _attach_client(self):
        self.input_protocol = SocketServerInputProtocol(self.session, self) # TODO: pass weakref of session
        self.renderer = AmpRenderer(weakref.ref(self.session), self) # TODO: pass weakref of session
        self.session.add_renderer(self.renderer)

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

    @GetSessionInfo.responder
    def _get_sessioninfo(self):
        def get_pane_info(pane):
            return {
                    "sx": pane.sx,
                    "sy": pane.sy,
                    "process_id": pane.process_id,
            }

        def get_window_info(window):
            return {
                    "panes": { p.id: get_pane_info(p) for p in window.panes }
            }

        return {
                'text': json.dumps({
                    "windows": { w.id: get_window_info(w) for w in self.session.windows }
                    })
        }

    @NewWindow.responder
    def _new_window(self):
        self.session.create_new_window()

    @asyncio.coroutine
    def send_output_to_client(self, data):
        data = data.encode('utf-8')

        # Send in chunks of MAX_VALUE_LENGTH
        while data:
            send, data = data[:MAX_VALUE_LENGTH], data[MAX_VALUE_LENGTH:]
            result = yield from self.call_remote(WriteOutput, data=send)

    @asyncio.coroutine
    def detach(self):
        yield from self.call_remote(DetachClient)


@asyncio.coroutine
def run():
    session = PyMuxSession()
    connections = []

    def protocol_factory():
        """ Factory of ServerProtocol instances """
        def done_callback():
            connections.remove(protocol)

        protocol = ServerProtocol(session, done_callback)
        connections.append(protocol)
        return protocol

    # Start AMP Listener.
    server = yield from loop.create_server(protocol_factory, 'localhost', 4376)

    # Run the session (this is blocking untill all panes in this session are
    # finished.)
    yield from session.run()

    # Disconnect all clients.
    for c in connections:
        result = yield from c.call_remote(DetachClient)

def start_server():
    loop.run_until_complete(run())


if __name__ == '__main__':
    start_server()
