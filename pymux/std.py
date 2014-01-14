import termios
import tty


class raw_mode(object):
    """
    with raw_mode(stdin):
        ''' the pseudo-terminal stdin is now used in raw mode '''
    """
    def __init__(self, stdin):
        self.stdin = stdin

        if self.stdin.isatty():
            self.attrs_before = termios.tcgetattr(self.stdin)

    def __enter__(self):
        if self.stdin.isatty():
            # NOTE: On os X systems, using pty.setraw() fails. Therefor we are using this:
            newattr = termios.tcgetattr(self.stdin.fileno())
            newattr[tty.LFLAG] = newattr[tty.LFLAG] & ~(termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
            termios.tcsetattr(self.stdin.fileno(), termios.TCSANOW, newattr)

    def __exit__(self, *a, **kw):
        if self.stdin.isatty():
            termios.tcsetattr(self.stdin.fileno(), termios.TCSANOW, self.attrs_before)
