
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

# Make sure stdin is unbuffered.
#sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)

# Set terminal:
# 1: Set cursor key to application
# 0: ???
# 4: Set smooth scrolling
# 9: Set interlacing mode
sys.stdout.write('\033[?1049h')

loop = asyncio.get_event_loop()

logfile = open('/tmp/pymux-log', 'w')

def log(msg, *a):
	logfile.write(msg % a + '\n')
	logfile.flush()


class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
	def __init__(self, pane):
		self.transport = None
		self.pane = pane

	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		self.pane.write_output(data.decode('utf-8'))


class Position:
	# Bit flags
	Top = 1
	Bottom = 2
	Left = 4
	Right = 8


class CellPosition:
	""" Position of a cell according to a single pane. """
	Outside = 0
	Inside = 100

	TopBorder = Position.Top
	RightBorder = Position.Right
	BottomBorder = Position.Bottom
	LeftBorder = Position.Left
	TopLeftBorder = Position.Top | Position.Left
	TopRightBorder = Position.Top | Position.Right
	BottomRightBorder = Position.Bottom | Position.Right
	BottomLeftBorder = Position.Bottom | Position.Left


class BorderType:
	""" Position of a cell in a window. """
	# Cross join
	Join = Position.Left | Position.Top | Position.Bottom | Position.Right

	BottomJoin = Position.Left | Position.Right | Position.Top
	TopJoin = Position.Left | Position.Right | Position.Bottom
	LeftJoin = Position.Right | Position.Top | Position.Bottom
	RightJoin = Position.Left | Position.Top | Position.Bottom

	# In the middle of a border
	Horizontal = Position.Left | Position.Right
	Vertical = Position.Bottom | Position.Top

	BottomRight = Position.Left | Position.Top
	TopRight = Position.Left | Position.Bottom
	BottomLeft = Position.Right | Position.Top
	TopLeft = Position.Right | Position.Bottom

	NoBorder = 0

CellPositionToBorderType = {
	CellPosition.TopBorder: BorderType.Horizontal,
	CellPosition.BottomBorder: BorderType.Horizontal,
	CellPosition.LeftBorder: BorderType.Vertical,
	CellPosition.RightBorder: BorderType.Vertical,

	CellPosition.TopLeftBorder: BorderType.TopLeft,
	CellPosition.TopRightBorder: BorderType.TopRight,
	CellPosition.BottomLeftBorder: BorderType.BottomLeft,
	CellPosition.BottomRightBorder: BorderType.BottomRight,

	CellPosition.Outside: BorderType.NoBorder
}

BorderSymbols = {
	BorderType.Join: '┼',
	BorderType.BottomJoin: '┴',
	BorderType.TopJoin: '┬',

	BorderType.LeftJoin: '├',
	BorderType.RightJoin: '┤',

	# In the middle of a border
	BorderType.Horizontal: '─',
	BorderType.Vertical: '│',

	BorderType.BottomRight: '┘',
	BorderType.TopRight: '┐',
	BorderType.BottomLeft: '└',
	BorderType.TopLeft: '┌',
}

class Pane:
	def __init__(self, command='/usr/bin/vim', invalidate_callback=None):
		self._invalidate_callback = invalidate_callback

		# Pane position.
		self.px = 0
		self.py = 0

		# Pane size
		self.sx = 80
		self.sy = 24

		# Create output stream.
		self.screen = pyte.Screen(self.sx, self.sy)

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
	def start(self):
		# Connect read pipe to process
		read_transport, read_protocol = yield from loop.connect_read_pipe(
							lambda:SubProcessProtocol(self), self.shell_out)

		# Run process in executor, wait for that to finish.
		yield from loop.run_in_executor(None, self.process.communicate)

	def write_output(self, data):
		""" Write data received from the application into the pane and rerender. """
		self.stream.feed(data)
		self._invalidate_callback()

	def write_input(self, data):
		"""	Write user key strokes to the input. """
		self.shell_in.write(data)

	def repaint(self):
		data = []
		write = data.append

		# Display
		for l, lines in enumerate(self.screen):
			# Position cursor for line.
			write('\033[%i;%iH' % (self.py + l+1, self.px+1))

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
		return data

	@property
	def cursor_position(self):
		return self.screen.cursor.y, self.screen.cursor.x

	def _check_cell(self, x, y):
		""" For a given (x,y) cell, return the CellPosition. """
		# If outside this pane, skip it.
		if (x < self.px or x > self.px + self.sx + 1 or y < self.py or y > self.py + self.sy + 1):
			return CellPosition.Outside

		# Use bitmask for borders:
		mask = 0

		if y == self.py:
			mask |= Position.Top

		if y == self.py + self.sy + 1:
			mask |= Position.Bottom

		if x == self.px:
			mask |= Position.Left

		if x == self.px + self.sx + 1:
			mask |= Position.Right

		return mask


class Window:
	def __init__(self):
		self.panes = []
		self.active_pane = None
		self.sx = 80
		self.sy = 24

		# Invalidate state
		self._invalidated = False

	def invalidate(self):
		""" Schedule repaint. """
		if not self._invalidated:
			log('Scheduling repaint')
			self._invalidated = True
			loop.call_soon(self.repaint)

	def write_input(self, data):
		"""	Write user key strokes to the input of the active pane. """
		self.active_pane.write_input(data)

	def repaint(self):
		""" Do repaint now. """
		self._invalidated = False
		log('Repainting')

		# Make sure that stdout is blocking when we write to it.
		# By calling connect_read_pipe on stdin, asyncio will mark the stdin as
		# non blocking (in asyncio.unix_events._set_nonblocking). This causes
		# stdout to be nonblocking as well.  That's fine, but it's never a good
		# idea to write to a non blocking stdout, as it will often raise the
		# "write could not complete without blocking" error and not write to
		# stdout.
		fd = sys.stdout.fileno()
		flags = fcntl.fcntl(fd, fcntl.F_GETFL)
		new_flags = flags & ~ os.O_NONBLOCK
		fcntl.fcntl(fd, fcntl.F_SETFL, new_flags)

		try:
			sys.stdout.write(''.join(self._repaint()))
			sys.stdout.flush()
		except Exception as e:
			log("%r", e)
		finally:
			fcntl.fcntl(fd, fcntl.F_SETFL, flags)

	def _repaint(self):
		data = []
		write = data.append

		write('\u001b[2J') # Erase screen

		# Draw panes.
		for pane in self.panes:
			data += pane.repaint()

		# Draw borders
		data += self._repaint_border()

		# Set cursor to right position
		#write('\u001b[H') # Home
		if self.active_pane:
			ypos, xpos = self.active_pane.cursor_position
			write('\033[%i;%iH' % (self.active_pane.py + ypos+1, self.active_pane.px + xpos+1))
		return data

	def _repaint_border(self):
		data = []
		write = data.append

		for x in range(0, self.sx):
			for y in range(0, self.sy):
				border_type, is_active = self._check_cell(x, y)
				if border_type:
					write('\u001b[H') # Home
					write('\033[%i;%iH' % (y, x))

					write('\033[0m')
					if is_active:
						write('\033[0;%im' % 32)

					write(BorderSymbols[border_type])

		return data

	def _check_cell(self, x, y):
		""" For a given (x,y) cell, return the pane to which this belongs, and
		the type of border we have there.

		:returns: BorderType
		"""
		# Create mask: set bits when the touching cells are borders.
		mask = 0
		is_active = False

		for pane in self.panes:
			cell_position = pane._check_cell(x, y)

			# If inside pane:
			if cell_position == CellPosition.Inside:
				return BorderType.NoBorder

			mask |= CellPositionToBorderType[cell_position]

			is_active = is_active or (cell_position and pane == self.active_pane)

		return mask, is_active

	@asyncio.coroutine
	def run_pane(self, pane):
		""" Run pane inside this window.
		Returns when the process is finished.  """
		# Add pane
		self.panes.append(pane)
		if not self.active_pane:
			self.active_pane = pane

		# Run it
		yield from pane.start()

		# Remove pane
		self.panes.remove(pane)

		if self.active_pane == pane:
			if self.panes:
				self.active_pane = self.panes[0]
			else:
				self.active_pane = None

		# Reschedule redraw
		self.invalidate()

	# Commands
	def focus_next(self):
		log('focus next pane')

		if self.active_pane:
			index = self.panes.index(self.active_pane) + 1
			self.active_pane = self.panes[index % len(self.panes)]
			self.invalidate()


class Client:
	def __init__(self, window):
		self.window = window
		self._input_parser_generator = self._input_parser()
		self._input_parser_generator.send(None)

	def process_input(self, char):
		log('Received char: %r', char)
		self._input_parser_generator.send(char)

	def _input_parser(self):
		while True:
			char = yield

			if char == b'\x01': # Ctrl-A
				log('Received CTRL-A')

				c2 = yield

				# Twice pressed escape char
				if c2 == b'\x01':
					self.window.write_input(char)

				elif c2 == b'n':
					self.window.focus_next()
			else:
				self.window.write_input(char)


class InputProtocol:
	def __init__(self, callback):
		self.callback = callback

	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		@asyncio.coroutine
		def process():
			for c in data:
				self.callback(bytes((c,)))
		asyncio.async(process())


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
	with raw_mode(sys.stdin):
		window = Window()
		window.sy, window.sx = get_size(sys.stdout)

		pane = Pane('/usr/bin/vim', window.invalidate)
		pane.px = 1
		pane.py = 1

		pane2 = Pane('/bin/bash', window.invalidate)
		pane2.px = 1
		pane2.py = 26

		client = Client(window)

		# Use a connect_read_pipe to read the input.
		input_transport, input_protocol = yield from loop.connect_read_pipe(lambda:InputProtocol(client.process_input), sys.stdin)

		f1 = asyncio.async(window.run_pane(pane))
		f2 = asyncio.async(window.run_pane(pane2))
		yield from asyncio.gather(f1, f2)

loop.run_until_complete(run())
sys.stdout.write('\033[?1049l')
