from libpymux.renderer import Renderer, RendererSize
import asyncio


class AmpRenderer(Renderer):
    """
    Renderer which sends the stdout over AMP to the client.
    """
    def __init__(self, session_ref, amp_protocol):
        super().__init__(session_ref)
        self.amp_protocol = amp_protocol

    @asyncio.coroutine
    def _write_output(self, data):
        yield from self.amp_protocol.send_output_to_client(data)

    def get_size(self):
        return RendererSize(
                self.amp_protocol.client_width,
                self.amp_protocol.client_height)
