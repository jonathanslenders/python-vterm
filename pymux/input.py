from .log import logger


class InputProtocol:
    def __init__(self, client):
        self.client = client

        self._input_parser_generator = self._input_parser()
        self._input_parser_generator.send(None)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self._process_input(data)

    def _process_input(self, char):
        logger.info('Received input: %r' % char)
        self._send_buffer = []

        for c in char:
            self._input_parser_generator.send(bytes((c,)))

        if self._send_buffer:
            self.client.send_input_to_current_pane(self._send_buffer)

        self._send_buffer = []

    def _input_parser(self):
        while True:
            char = yield

            if char == b'\x01': # Ctrl-A
                logger.info('Received CTRL-A')

                c2 = yield

                bindings = {
                    b'\x01': lambda: self._send_buffer.append(b'\x01'),
                    b'n': self.client.focus_next_window,
                    b'"': lambda: self.client.split_pane(vsplit=False),
                    b'%': lambda: self.client.split_pane(vsplit=True),
                    b'x': self.client.kill_current_pane,
                    b'c': self.client.create_new_window,
                    b'h': lambda: self.client.resize_current_tile('L', 4),
                    b'k': lambda: self.client.resize_current_tile('U', 4),
                    b'l': lambda: self.client.resize_current_tile('R', 4),
                    b'j': lambda: self.client.resize_current_tile('D', 4),
                    b'H': lambda: self.client.move_focus('L'),
                    b'K': lambda: self.client.move_focus('U'),
                    b'L': lambda: self.client.move_focus('R'),
                    b'J': lambda: self.client.move_focus('D'),
                    b'R': lambda: self.client.invalidate(Redraw.All),
                    #b':': lambda: self.client.focus_status(),
                }
                handler = bindings.get(c2, None)
                if handler:
                    handler()
            else:
                self._send_buffer.append(char)
