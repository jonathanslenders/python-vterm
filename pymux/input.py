from libpymux.input import InputProtocol
from libpymux.invalidate import Redraw


class PyMuxInputProtocol(InputProtocol):
    def get_bindings(self):
        return {
            b'\x01': lambda: self.send_input_to_current_pane(b'\x01'),
            b'n': self.session.focus_next_window,
            b'"': lambda: self.session.split_pane(vsplit=False),
            b'%': lambda: self.session.split_pane(vsplit=True),
            b'x': self.session.kill_current_pane,
            b'c': self.session.create_new_window,
            b'h': lambda: self.session.resize_current_tile('L', 4),
            b'k': lambda: self.session.resize_current_tile('U', 4),
            b'l': lambda: self.session.resize_current_tile('R', 4),
            b'j': lambda: self.session.resize_current_tile('D', 4),
            b'H': lambda: self.session.move_focus('L'),
            b'K': lambda: self.session.move_focus('U'),
            b'L': lambda: self.session.move_focus('R'),
            b'J': lambda: self.session.move_focus('D'),
            b'R': lambda: self.session.invalidate(Redraw.All),
            #b':': lambda: self.session.focus_status(),
        }
