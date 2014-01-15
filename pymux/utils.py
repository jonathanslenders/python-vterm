import array
import fcntl
import termios

def get_size(stdout):
    # Thanks to fabric (fabfile.org), and
    # http://sqizit.bartletts.id.au/2011/02/14/pseudo-terminals-in-python/
    """
    Get the size of this pseudo terminal.

    :returns: A (rows, cols) tuple.
    """
    #assert stdout.isatty()

    # Buffer for the C call
    buf = array.array('h', [0, 0, 0, 0 ])

    # Do TIOCGWINSZ (Get)
    #fcntl.ioctl(stdout.fileno(), termios.TIOCGWINSZ, buf, True)
    fcntl.ioctl(0, termios.TIOCGWINSZ, buf, True)

    # Return rows, cols
    return buf[0], buf[1]



def set_size(stdout_fileno, rows, cols):
    """
    Set terminal size.

    (This is also mainly for internal use. Setting the terminal size
    automatically happens when the window resizes. However, sometimes the process
    that created a pseudo terminal, and the process that's attached to the output window
    are not the same, e.g. in case of a telnet connection, or unix domain socket, and then
    we have to sync the sizes by hand.)
    """
    # Buffer for the C call
    buf = array.array('h', [rows, cols, 0, 0 ])

    # Do: TIOCSWINSZ (Set)
    fcntl.ioctl(stdout_fileno, termios.TIOCSWINSZ, buf)
