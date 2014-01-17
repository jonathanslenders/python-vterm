#!/usr/bin/env python

from pymux.amp_commands import GetSessionInfo

import asyncio
import asyncio_amp

__all__ = ('session_info', )

loop = asyncio.get_event_loop()


def session_info():
    # Establish server connection
    transport, protocol = loop.run_until_complete(
            loop.create_connection(asyncio_amp.AMPProtocol, 'localhost', 4376))

    # Run GetSessionInfo
    return loop.run_until_complete(protocol.call_remote(GetSessionInfo))

