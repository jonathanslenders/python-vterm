
import subprocess
import asyncio
import pyte
import sys
import os
import tty
import io
import signal
import fcntl
import array
import termios
import time
import select

from std import raw_mode

class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
	def __init__(self, pane):
		self.transport = None
		self.pane = pane

	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		self.pane.write(data.decode('utf-8'))


class Pane:
	def __init__(self, command='/usr/bin/vim'):
		self._repaint_scheduled = False

		# Create output stream.
		self.screen = pyte.Screen(80, 24)

		self.stream = pyte.Stream()
		self.stream.attach(self.screen)

		# Create pseudo terminal for this pane.
		self.master, self.slave = os.openpty()

		# Master side -> attached to terminal emulator.
		self.shell_in = io.open(self.master, 'wb', 0)
		self.shell_out = io.open(self.master, 'rb', 0)

		# Slave side -> attached to process.
		self.slave_stdin = io.open(self.slave, 'rb', 0)
		self.slave_stdout = io.open(self.slave, 'wb', 0)

		self.process = subprocess.Popen(command, stdin=self.slave_stdin,
					stdout=self.slave_stdout, stderr=self.slave_stdout, bufsize=0)


	@asyncio.coroutine
	def start_reader(self):
		read_transport, read_protocol = yield from loop.connect_read_pipe(
							lambda:SubProcessProtocol(self), self.shell_out)

	def write(self, data):
		""" Write data received from the application into the pane and rerender. """
		self.stream.feed(data)

		if not self._repaint_scheduled:
			self._repaint_scheduled = True
			loop.call_soon(self.repaint)

	def repaint(self):
		self._repaint_scheduled = False

		data = []
		write = data.append

		# Display
		write('\u001b[H')
		write('\u001b[2J')
		write('\033[0m'); write('─' * 80)
		write('\r\n')
		for lines in self.screen:
			write('\033[0m'); write('│')
			for char in lines:
				write('\033[0m')

				if char.fg != 'default':
					colour_code = reverse_colour_code[char.fg]
					write('\033[0;%im' % colour_code)

				if char.bg != 'default':
					colour_code = reverse_bgcolour_code[char.bg]
					write('\033[%im' % colour_code)

				if char.bold:
					write('\033[1m')

				if char.underscore:
					write('\033[4m')

				if char.reverse:
					write('\033[7m')

				write(char.data)
			write('\033[0m'); write('│\r\n')
		write('\033[0m'); write('─' * 80)

		# Now move the cursor to the right position
		write('\u001b[H')
		write('\033[%i;%iH' % (self.screen.cursor.y+2, self.screen.cursor.x+2))
		sys.stdout.write(''.join(data))
		sys.stdout.flush()


reverse_colour_code = dict((v,k) for k,v in pyte.graphics.FG.items())
reverse_bgcolour_code = dict((v,k) for k,v in pyte.graphics.BG.items())

# Make sure stdin is unbuffered.
sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)

# Set terminal:
# 1: Set cursor key to application
# 0: ???
# 4: Set smooth scrolling
# 9: Set interlacing mode
sys.stdout.write('\033[?1049h')

loop = asyncio.get_event_loop()

#class InputProtocol:
#	def connection_made(self, transport):
#		self.transport = transport
#
#	def data_received(self, data):
#		for c in data:
#			shell_in.write(bytes((c,)))
#	---> input_transport, input_protocol = yield from loop.connect_read_pipe(InputProtocol, sys.stdin)


def get_size(stdout):
	# Thanks to fabric (fabfile.org), and
	# http://sqizit.bartletts.id.au/2011/02/14/pseudo-terminals-in-python/
	"""
	Get the size of this pseudo terminal.

	:returns: A (rows, cols) tuple.
	"""
	if stdout.isatty():
		# Buffer for the C call
		buf = array.array('h', [0, 0, 0, 0 ])

		# Do TIOCGWINSZ (Get)
		fcntl.ioctl(stdout.fileno(), termios.TIOCGWINSZ, buf, True)

		# Return rows, cols
		return buf[0], buf[1]
	else:
		# Default value
		return 24, 80

def set_size(stdout, rows, cols):
	"""
	Set terminal size.

	(This is also mainly for internal use. Setting the terminal size
	automatically happens when the window resizes. However, sometimes the process
	that created a pseudo terminal, and the process that's attached to the output window
	are not the same, e.g. in case of a telnet connection, or unix domain socket, and then
	we have to sync the sizes by hand.)
	"""
	if stdout.isatty():
		# Buffer for the C call
		buf = array.array('h', [rows, cols, 0, 0 ])

		# Do: TIOCSWINSZ (Set)
		fcntl.ioctl(stdout.fileno(), termios.TIOCSWINSZ, buf)



# Signal handler for resize events.
def sigwinch_handler(n, frame):
	rows, cols = get_size(sys.stdin)
	rows -= 3
	cols -= 3
	screen.resize(rows, cols)
	set_size(slave_stdin, rows, cols)
	loop.call_soon(os.kill, process.pid, signal.SIGWINCH) # XXX: not necessary??

# signal.signal(signal.SIGWINCH, sigwinch_handler)


@asyncio.coroutine
def run():
	pane = Pane()
	yield from pane.start_reader()

	with raw_mode(sys.stdin):
		is_running = True
		def input_loop():
			# Input loop executor.
			while is_running:
				try:
					r, w, e = select.select([sys.stdin], [], [], .4)
					if sys.stdin in r:
						c = sys.stdin.read(1)
						pane.shell_in.write(c)
				except Exception as e:
					print (e)


		f1 = loop.run_in_executor(None, input_loop)
		f2 = loop.run_in_executor(None, pane.process.communicate)
		yield from f2
		is_running = False
		yield from f1

loop.run_until_complete(run())
sys.stdout.write('\033[?1049l')
