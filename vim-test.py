
import subprocess
import asyncio
import pyte
import sys
import os
import tty
import io

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

class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
	def __init__(self):
		self.transport = None

	def connection_made(self, transport):
		self.transport = transport

	def data_received(self, data):
		stream.feed(data.decode('utf-8'))

		# Display
		sys.stdout.write('\u001b[H')
		for lines in screen:
			for char in lines:
				sys.stdout.write('\033[0m')

				if char.fg != 'default':
					colour_code = reverse_colour_code[char.fg]
					sys.stdout.write('\033[0;%im' % colour_code)

				if char.bg != 'default':
					colour_code = reverse_bgcolour_code[char.bg]
					sys.stdout.write('\033[%im' % colour_code)

				if char.bold:
					sys.stdout.write('\033[1m')

				if char.underscore:
					sys.stdout.write('\033[4m')

				if char.reverse:
					sys.stdout.write('\033[7m')

				sys.stdout.write(char.data)
			sys.stdout.write('\r\n')

		# Now move the cursor to the right position
		sys.stdout.write('\u001b[H')
		sys.stdout.write('\033[%i;%iH' % (screen.cursor.y+1, screen.cursor.x+1))
		sys.stdout.flush()

	def input_loop(self):
		# Input loop executor.

		# Make sure stdin is unbuffered.
		sys.stdin = os.fdopen(sys.stdin.fileno(), 'rb', 0)
		tty.setraw(sys.stdin)

		while True: # TODO: use combination of select() and non blocking read here.
			try:
				c = sys.stdin.read(100)
				shell_in.write(c)
			except Exception as e:
				print (e)
				sys._exit(0)

loop = asyncio.get_event_loop()

process = subprocess.Popen('/usr/bin/vim', stdin=slave_stdin, stdout=slave_stdout, stderr=slave_stdout, bufsize=0)

@asyncio.coroutine
def run():
	read_transport, read_protocol = yield from loop.connect_read_pipe(SubProcessProtocol, shell_out)

	f2 = loop.run_in_executor(None, read_protocol.input_loop)
	yield from loop.run_in_executor(None, process.communicate)
	loop.stop()

loop.run_until_complete(run())
loop.run_forever()



