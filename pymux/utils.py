#!/usr/bin/env python

from pymux.amp_commands import GetSessionInfo, NewWindow

import asyncio
import asyncio_amp
import json

__all__ = ('session_info', )

loop = asyncio.get_event_loop()

def _get_protocol():
    # Establish server connection
    transport, protocol = loop.run_until_complete(
            loop.create_connection(asyncio_amp.AMPProtocol, 'localhost', 4376))

    return protocol

def session_info():
    protocol = _get_protocol()

    # Run GetSessionInfo
    data = loop.run_until_complete(protocol.call_remote(GetSessionInfo))
    return json.loads(data['text'])


def new_window():
    protocol = _get_protocol()
    loop.run_until_complete(protocol.call_remote(NewWindow))
