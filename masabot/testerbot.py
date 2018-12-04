import discord
import asyncio
import traceback
import logging
import multiprocessing

from masabot.util import DiscordPager


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


_BOT_TESTER_SHUTDOWN_COMMAND = "BOT-TESTER-STOP"


class BotCommandExecutor(object):
	"""
	Manages the execution of the tester bot. Should always be used in preference to TesterBot directly.

	Uses a pipe to communicate with bot process. To ensure the pipe does not fill with data, output should always be
	read very quickly after a command is sent.
	"""

	def __init__(self, api_key, channel, target):
		"""
		Initializes a new Executor.
		:type api_key: str
		:param api_key: The API key to use to identify with Discord.
		:type channel: str
		:param channel: The channel that the tester should perform tests on.
		:type target: str
		:param target: The UUID (snowflake ID) of the target bot user that tests are to be performed against.
		"""
		self._pipe, bot_end = multiprocessing.Pipe()
		self._bot_process = multiprocessing.Process(target=start_tester_bot, args=(bot_end, api_key, channel, target))

	def start(self):
		"""
		Begins the tester bot in a separate process.
		"""
		self._bot_process.start()

	def stop(self, timeout=None):
		"""
		Terminates the tester bot. Blocks until the tester bot is shut down, or until the given timeout is reached.
		:type timeout: int
		:param timeout: Number of seconds to wait for bot tester to be shut down. Defaults to 'None', which is no
		timeout.
		"""
		self._pipe.send(_BOT_TESTER_SHUTDOWN_COMMAND)
		self._bot_process.join(timeout)

	def send_command(self, command):
		"""
		Sends the given bot command.
		:type command: str
		:param command: The text to send in the message.
		"""
		if command == _BOT_TESTER_SHUTDOWN_COMMAND:
			raise ValueError("Not valid to call shutdown command with send_command(); use stop() instead")
		self._pipe.send(command)

	def get_output(self, timeout=5):
		"""
		Receives output from the target bot. If no output is available after the timeout is reached, an exception is
		raised. The timeout cannot be set to None.
		:type timeout: int
		:param timeout: The number of seconds to wait for output to be produced.
		:rtype: str
		:return: The output text
		"""
		if timeout is None:
			raise ValueError("timeout cannot be None")
		if timeout < 0:
			raise ValueError("timeout cannot be less than 0")
		if not self._pipe.poll(timeout):
			raise TimeoutError("No output produced within timeout of " + repr(timeout) + " seconds")
		else:
			return self._pipe.recv()


def start_tester_bot(pipe, api_key, channel, target):
	"""
	Initialize Tester bot.
	:type pipe: multiprocessing.Connection
	:param pipe: The pipe to use for communicating between this bot and its executor.
	:type api_key: str
	:param api_key: The API key to use to identify with Discord.
	:type channel: str
	:param channel: The channel that the tester should perform tests on.
	:type target: str
	:param target: The UUID (snowflake ID) of the target bot user that tests are to be performed against.
	"""
	bot = TesterBot(pipe, api_key, channel, target)
	bot.run()


class TesterBot(object):
	"""
	DO NOT USE DIRECTLY, use BotCommandExecutor.
	"""

	def __init__(self, pipe, api_key, channel, target):
		"""
		Initialize Tester bot.
		:type pipe: multiprocessing.Connection
		:param pipe: The pipe to use for communicating between this bot and its executor.
		:type api_key: str
		:param api_key: The API key to use to identify with Discord.
		:type channel: str
		:param channel: The channel that the tester should perform tests on.
		:type target: str
		:param target: The UUID (snowflake ID) of the target bot user that tests are to be performed against.
		"""

		self._pipe = pipe
		self._running = False
		self._channels = []
		self._channel_name = channel
		self._target_id = target
		self._api_key = api_key
		self._command_reader_task = None
		self._client = discord.Client()

		@self._client.event
		async def on_ready():
			_log.info("Tester bot logged in as " + self._client.user.name)
			_log.info("Tester bot ID: " + self._client.user.id)
			self._running = True
			_log.info("Tester bot is now online")
			for server in self._client.servers:
				for ch in server.channels:
					if ch.type == discord.ChannelType.text and ('#' + ch.name) == self._channel_name:
						self._channels.append(ch)
			if len(self._channels) == 0:
				raise RuntimeError("No channels in servers that this bot is connected to match " + repr(self._channel_name))

		@self._client.event
		async def on_message(message):
			if message.author.id == self._target_id and ('#' + message.channel.name) == self._channel_name:
				await self._handle_target_message(message)

		@self._client.event
		async def on_error(event, *args, **kwargs):
			pager = DiscordPager("_(error continued)_")
			message = args[0]
			e = traceback.format_exc()
			logging.exception("Tester bot exception in main loop")
			msg_start = "Tester bot exception"
			pager.add_line(msg_start)
			pager.add_line()
			pager.start_code_block()
			for line in e.splitlines():
				pager.add_line(line)
			pager.end_code_block()
			pages = pager.get_pages()
			for p in pages:
				await self._client.send_message(message.channel, p)

	def run(self):
		"""
		Begin execution of tester bot. Blocks until complete.
		"""
		_log.info("Tester bot connecting...")
		try:
			self._command_reader_task = self._client.loop.create_task(self._read_pipe())
			self._client.run(self._api_key)
		finally:
			self._running = False
			self._client.close()

	async def _handle_target_message(self, message):
		self._pipe.send(message.content)

	async def _read_pipe(self):
		"""
		Read pipe for any commands to execute.
		"""
		wait_for_run_max = 10
		waited = 0
		while not self._running:
			if waited == wait_for_run_max:
				raise TimeoutError("Bot took too long to come online")
			await asyncio.sleep(1)
		while self._running:
			if self._client.is_logged_in and self._pipe.poll():
				command = self._pipe.recv()
				if command == _BOT_TESTER_SHUTDOWN_COMMAND:
					self._pipe.close()
					await self._client.logout()
				await self.send_to_all_servers(command)
			await asyncio.sleep(0.25)

	async def send_to_all_servers(self, message):
		"""
		Sends the given message to the room this bot is watching, in all servers that this bot is connected to.
		:type message: str
		:param message: The message to send.
		"""
		for ch in self._channels:
			await self._client.send_message(ch, message)
