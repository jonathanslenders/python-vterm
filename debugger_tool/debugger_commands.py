import asyncio_amp
from asyncio_amp.arguments import String, Integer

# From server to client.

class Continue(asyncio_amp.Command):
    arguments = [ ]
    response = [ ]

class Next(asyncio_amp.Command):
    arguments = [ ]
    response = [ ]

class Step(asyncio_amp.Command):
    arguments = [ ]
    response = [ ]

class GetLocals(asyncio_amp.Command):
    arguments = [ ]
    response = [ ]

# From server to client.

class Breaking(asyncio_amp.Command):
    arguments = [
            ('line', Integer()),
            ('filename', String()),
            ('func_name', String()),
        ]
    response = [ ]
