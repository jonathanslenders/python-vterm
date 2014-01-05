
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

reverse_colour_code = dict((v,k) for k,v in pyte.graphics.FG.items())
reverse_bgcolour_code = dict((v,k) for k,v in pyte.graphics.BG.items())

stream = pyte.Stream()
screen = pyte.Screen(80, 24)
stream.attach(screen)

master, slave = os.openpty()
shell_in = io.open(master, 'wb', 0)
shell_out = io.open(master, 'rb', 0)
slave_stdin = io.open(slave, 'rb', 0)
slave_stdout = io.open(slave, 'wb', 0)

# Make sure stdin is unbuffered.
sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)
log = open('/tmp/log', 'wb', 0)

sys.stdout.write('\033[?1049h')

repaint_scheduled = False

loop = asyncio.get_event_loop()

class InputProtocol:
	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		for c in data:
			shell_in.write(bytes((c,)))
				#c = sys.stdin.read(100)
				#shell_in.write(c)


class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
	def __init__(self):
		self.transport = None

	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		log.write(data)
		stream.feed(data.decode('utf-8'))

		global repaint_scheduled
		if not repaint_scheduled:
			loop.call_soon(repaint)

def repaint():
	global repaint_scheduled
	repaint_scheduled = False

	data = []
	write = data.append

	# Display
	write('\u001b[H')
	write('\u001b[2J')
	write('\033[0m'); write('─' * 80)
	write('\r\n')
	for lines in screen:
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
	write('\033[%i;%iH' % (screen.cursor.y+2, screen.cursor.x+2))
	sys.stdout.write(''.join(data))
	sys.stdout.flush()


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
	#loop.call_soon(set_size, slave_stdin, rows, cols)
	loop.call_soon(os.kill, process.pid, signal.SIGWINCH) # XXX: not necessary??
	#os.kill(process.pid, signal.SIGWINCH) # XXX: not necessary??

signal.signal(signal.SIGWINCH, sigwinch_handler)


process = subprocess.Popen('/usr/bin/top', stdin=slave_stdin, stdout=slave_stdout, stderr=slave_stdout, bufsize=0)

@asyncio.coroutine
def run():
	read_transport, read_protocol = yield from loop.connect_read_pipe(SubProcessProtocol, shell_out)

#	input_transport, input_protocol = yield from loop.connect_read_pipe(InputProtocol, sys.stdin)

		#tty.setraw(sys.stdin)
	with raw_mode(sys.stdin):
		is_running = True
		def input_loop():
			# Input loop executor.
			while is_running: # TODO: use combination of select() and non blocking read here.
				try:
					r, w, e = select.select([sys.stdin], [], [], .4)
					if sys.stdin in r:
						c = sys.stdin.read(1)
						shell_in.write(c)
				except Exception as e:
					print (e)


		f2 = loop.run_in_executor(None, input_loop)
		yield from loop.run_in_executor(None, process.communicate)
#		yield from f2
	is_running = False

loop.run_until_complete(run())
sys.stdout.write('\033[?1049l')
