import asyncio_amp


# From server to client.

class WriteOutput(asyncio_amp.Command):
    arguments = [
        ('data', asyncio_amp.Bytes()),
    ]
    response = [ ]

class DetachClient(asyncio_amp.Command):
    """ Ask the client to detach himself. """
    pass


# from client to server.

class AttachClient(asyncio_amp.Command):
    arguments = [ ]
    response = [ ]

class SendKeyStrokes(asyncio_amp.Command):
    arguments = [
        ('data', asyncio_amp.Bytes()),
    ]
    response = [ ]

class GetSessions(asyncio_amp.Command):
    arguments = [ ]
    response = [
        ('text', asyncio_amp.String()),
    ]

class SetSize(asyncio_amp.Command):
    arguments = [
        ('width', asyncio_amp.Integer()),
        ('height', asyncio_amp.Integer()),
    ]
    response = [ ]

class GetSessionInfo(asyncio_amp.Command):
    arguments = [ ]
    response = [
        ('text', asyncio_amp.String()),
    ]

class NewWindow(asyncio_amp.Command):
    pass
