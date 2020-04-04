import importlib
import logging
import pickle
import discord
import json
import traceback
import os
import asyncio
import time
import re
import shlex
from . import configfile, commands, util
from typing import Optional
from .util import BotSyntaxError, BotModuleError, BotPermissionError, MessageMetadata, DiscordPager


VERSION = "1.0.2"


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


def _fmt_channel(ch):
	"""
	Print a channel in human-readable format.

	:type ch: discord.TextChannel | discord.PrivateChannel | discord.User
	:param ch: The channel.
	:rtype: str
	:return: A string with the channel details
	"""

	try:
		return "DM " + str(ch.id) + "/" + str(ch.name) + "#" + str(ch.discriminator)
	except AttributeError:
		if ch.type == discord.ChannelType.text or ch.type == discord.ChannelType.voice:
			return str(ch.guild.id) + "/" + repr(ch.guild.name) + " #" + ch.name
		elif ch.type == discord.ChannelType.private:
			other = ch.recipient
			return "DM " + str(other.id) + "/" + other.name + "#" + other.discriminator
		else:
			return "Unknown ChannelType"


def _fmt_send(channel, message):
	return "[" + _fmt_channel(channel) + "]: sent " + repr(message)


class Timer(object):
	def __init__(self, bot_module, period):
		"""
		Creates a new timer for the given module.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module that the timer is for.
		:type period: int
		:param period: The number of seconds between fires of the timer.
		"""
		self.has_run = False
		self.next_run = 0
		self.future = None
		self.bot_module = bot_module
		self.period = period

	def tick(self, now_time, on_fire_error):
		"""
		Advances the timer by one tick and fires it asynchronously if it is ready to fire.

		:type now_time: float
		:param now_time: Monotonic current time.
		:type on_fire_error: (str) -> {__await__}
		:param on_fire_error: Accepts a message and properly reports it.
		"""
		if not self.has_run or self.next_run <= now_time:
			# make any last tasks have finished before attempting to run again:
			if self.future is None or self.future.done():
				self.future = asyncio.ensure_future(self.fire(on_fire_error))
				self.has_run = True
			if not self.has_run:
				self.next_run = now_time + self.period
			else:
				self.next_run = self.next_run + self.period

	async def fire(self, on_error):

		_log.debug("Firing timer on module " + repr(self.bot_module.name))
		# noinspection PyBroadException
		try:
			await self.bot_module.on_timer_fire()
		except Exception:
			_log.exception("Encountered error in timer-triggered function")
			msg = "Exception in firing timer of '" + self.bot_module.name + "' module:\n\n```python\n"
			msg += traceback.format_exc()
			msg += "\n```"
			await on_error


class BotContext(object):

	def __init__(self, message):
		if message is not None:
			self.source = message.channel
			self.author = message.author
			self.is_pm = isinstance(message, discord.abc.PrivateChannel) and len(self.source.recipients) == 1
		else:
			self.source = None
			self.author = None
			self.is_pm = False

	def mention(self):
		"""
		Gets a mention of the author that created the message.
		:return: The author
		"""
		return "<@!" + str(self.author.id) + ">"

	def author_name(self):
		return self.author.name + "#" + self.author.discriminator

	def channel_exists(self, ch_id):
		"""
		Check if the given channel ID is a channel located within the context. If the context is associated with a
		server, check if the id matches the id of a channel on the server. If the context is associated with a private
		channel, check if the ID matches the channel ID exactly.
		:type ch_id: str
		:param ch_id: The ID of the channel to check.
		:rtype: bool
		:return: Whether the channel exists
		"""
		if self.is_pm:
			return ch_id == self.source.id
		else:
			for ch in self.source.server.channels:
				if ch.type == discord.ChannelType.text and ch.id == ch_id:
					return True
			return False

	def get_channel_name(self, ch_id):
		"""
		Get the name of a channel located within the context. If the context is associated with a server, get the name
		of the channel on the server whose id matches the given one. If the context is associated with a private
		channel, check if the ID matches the channel ID exactly, and return the name if so. Raises an exception in all
		other cases.
		:type ch_id: str
		:param ch_id: The ID of the channel to get the name for.
		:rtype: str
		:return: The name of the channel.
		"""
		if self.is_pm:
			if ch_id != self.source.id:
				raise ValueError(str(ch_id) + " is not a channel in this context")
			return self.source.name
		else:
			ch_match = None
			for ch in self.source.server.channels:
				if ch.type == discord.ChannelType.text and ch.id == ch_id:
					ch_match = ch
					break
			if ch_match is None:
				raise ValueError(str(ch_id) + " is not a channel in this context")
			return ch_match.name

	async def to_dm_context(self):
		"""
		Create a copy of this context for sending DMs to the author.
		:return: The DM context.
		"""
		dm_context = BotContext(None)
		dm_context.author = self.author
		dm_context.source = await self.author.create_dm()
		dm_context.is_pm = True
		return dm_context

	def is_nsfw(self):
		"""
		Return whether the context allows nsfw content. This will always be true in a dm context.

		:rtype: bool
		:return: Whether NSFW content is allowed.
		"""
		if self.is_pm:
			return True
		else:
			return self.source.is_nsfw()


class MasaBot(object):

	def __init__(self, config_file):
		"""
		Initialize the bot API.
		:type config_file: str
		:param config_file: The path to the configuration file for the bot.
		"""
		self._bot_modules = {}
		""":type : dict[str, commands.BotBehaviorModule]"""
		self._invocations = {}
		self._mention_handlers = {}
		self._self_mention_handlers = []
		self._any_mention_handlers = []
		self._regex_handlers = {}
		self._operators = {}
		self._timers = []
		""":type : list[Timer]"""
		self._setup_complete = False
		self._master_timer_task = None

		# default replacements; will be overridden if present in state file
		self._invocation_replacements = {
			'“': '"',
			'”': '"'
		}

		state_dict = {}
		try:
			with open('state.p', 'rb') as fp:
				state_dict = pickle.load(fp)
		except FileNotFoundError:
			_log.warning("No state file found; default settings will be used")
		else:
			_log.info("Loading state file...")
			self._load_builtin_state(state_dict)

		_log.info("Loading config file...")
		conf = configfile.load_config(config_file)

		for m in conf['masters']:
			self._operators[m] = {'role': 'master'}
		self._api_key = conf['discord-api-key']
		self._prefix = conf['prefix']
		self._announce_channels = conf['announce-channels']

		self._client = discord.Client(status="being cute with discord.py 1.0+")

		self._sent_announcement = False
		@self._client.event
		async def on_ready():
			_log.info("Logged in as " + self._client.user.name)
			_log.info("ID: " + str(self._client.user.id))

			if self._client.user.avatar_url == '':
				_log.info("Avatar not yet set; uploading...")
				with open('avatar.png', 'rb') as avatar_fp:
					avatar_data = avatar_fp.read()
				await self._client.user.edit(avatar=avatar_data)

			_log.info("Connected to servers:")
			for g in self._client.guilds:
				_log.info("* " + str(g))
			_log.info("Bot is now online")
			clean_shutdown, reason = self._check_supervisor_unclean_shutdown()
			if clean_shutdown and not self._sent_announcement:
				await self.announce("Hello! I'm now online ^_^")
				self._sent_announcment = True
			else:
				_log.info("Back from unclean shutdown caused by: " + repr(reason))
			await self._check_supervisor_files()
			self._setup_complete = True

		@self._client.event
		async def on_message(message):
			if message.author.id == self._client.user.id:
				return  # don't answer own messages
			if message.content.startswith(self._prefix):
				if message.content.strip() == self._prefix:
					return  # don't reply to messages that are JUST the prefix
				await self._handle_invocation(message)
			else:
				if len(message.raw_mentions) > 0:
					await self._handle_mention(message)

				await self._handle_regex_scan(message)

		@self._client.event
		async def on_error(event, *args, **kwargs):
			if len(args) < 1:
				# assume that we did not come from on_message
				_log.exception("Exception in startup")
				if not self._setup_complete:
					with open('.supervisor/restart-command', 'w') as restart_command_file:
						restart_command_file.write("quit")
					await self._client.close()
			else:
				message = args[0]
				pager = DiscordPager("_(error continued)_")
				e = traceback.format_exc()
				logging.exception("Exception in main loop")
				msg_start = "I...I'm really sorry, but... um... I just had an exception :c"
				pager.add_line(msg_start)
				pager.add_line()
				pager.start_code_block()
				for line in e.splitlines():
					pager.add_line(line)
				pager.end_code_block()
				pages = pager.get_pages()
				for p in pages:
					await message.channel.send(p)
				_log.debug(_fmt_send(message.channel, msg_start + " (exc_details)"))

		self._load_modules(state_dict, conf['modules'])

	def run(self):
		"""
		Begin execution of bot. Blocks until complete.
		"""
		_log.info("Connecting...")
		# WARNING! WE REMOVED client.close() HERE.
		self._master_timer_task = self._client.loop.create_task(self._run_timer())
		self._client.run(self._api_key)

	async def announce(self, message):
		"""
		Send a message to all applicable channels on all servers. The channels are those that are set as the
		announce channels in the configuration.

		:type message: str
		:param message: The message to send.
		"""
		for g in self._client.guilds:
			for ch in g.channels:
				if ch.type == discord.ChannelType.text and ('#' + ch.name) in self._announce_channels:
					await ch.send(message)
					_log.debug(_fmt_send(ch, message))

	async def confirm(self, context, message):
		"""
		Prompt the user to select a yes-or-no option, and defaults to False if they do not answer. Times out after 60
		seconds, and returns False then.

		:type context: BotContext
		:param context: The context of the bot.
		:type message: str
		:param message: The message to show before the prompt.
		:rtype: bool
		:return: The option selected by the user, or False if the prompt times out.
		"""
		answer = await self.prompt_for_option(context, message)
		if answer is None:
			msg = "Sorry, " + context.mention() + ", but the prompt timed out! I'll assume 'no' for now; if that's not"
			msg += " what you wanted, go ahead and rerun the command again, okay?"
			await self.reply(context, msg)
			return False
		elif answer == "yes":
			return True
		elif answer == "no":
			return False

	async def prompt_for_option(self, context, message, option_1="yes", option_2="no", *additional_options):
		"""
		Prompt the user to select an option. Not case-sensitive; all options are converted to lower-case. Times out
		after 60 seconds, and returns None then.

		:type context: BotContext
		:param context: The context of the bot.
		:type message: str
		:param message: The message to show before the prompt.
		:type option_1: str
		:param option_1: The first option.
		:type option_2: str
		:param option_2: The second option.
		:type additional_options: str
		:param additional_options: Any additional options.
		:rtype: str | None
		:return: The option selected by the user, or None if the prompt times out.
		"""
		if option_1.lower() == option_2.lower():
			raise ValueError("option 1 and 2 are equal")

		all_options = {
			self._prefix + self._prefix + option_1.lower(): option_1.lower(),
			self._prefix + self._prefix + option_2.lower(): option_2.lower()
		}

		full_message = message + "\n\nSelect one of the following options: \n"
		full_message += "* `" + self._prefix + self._prefix + option_1.lower() + "`\n"
		full_message += "* `" + self._prefix + self._prefix + option_2.lower() + "`\n"
		for op in additional_options:
			if op.lower() in all_options:
				raise ValueError("Multiple equal options for '" + op.lower() + "'")
			full_message += "* `" + self._prefix + self._prefix + op + "`\n"
			all_options[self._prefix + self._prefix + op.lower()] = op.lower()

		await self.reply(context, full_message)
		_log.debug("[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " started")

		def check_option(msg):
			if msg.author != context.author:
				return False
			return msg.content in all_options

		try:
			message = await self._client.wait_for('message', timeout=60, check=check_option)
		except asyncio.TimeoutError:
			message = None
		if message is None:
			_log.debug("[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " timed out")
			return None
		else:
			log_msg = "[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " received "
			log_msg += repr(message.content)
			_log.debug(log_msg)
			return all_options[message.content]

	async def prompt(self, context, message, timeout=60, type_conv=str):
		"""
		Prompt the user for open-ended input. Returns None if the prompt times out.

		:type context: BotContext
		:param context: The context of the bot.
		:type message: str
		:param message: The message to show before the prompt.
		:type timeout: int
		:param timeout: The number of seconds to wait before timing out the prompt.
		:type type_conv: Any
		:param type_conv: The type to put the input through before returning it.
		:rtype: Any
		:return: The input given by the user, or None if the prompt times out.
		"""

		full_message = message + "\n\n(Enter `" + (self._prefix * 2) + "` followed by your answer)"
		await self.reply(context, full_message)
		_log.debug("[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " started")

		def check_option(msg):
			if msg.author != context.author:
				return False
			if not msg.content.startswith(self._prefix * 2):
				return False
			# noinspection PyBroadException
			try:
				type_conv(msg.content[len(self._prefix * 2):])
			except Exception:
				return False
			return True

		try:
			message = await self._client.wait_for('message', timeout=timeout, check=check_option)
		except asyncio.TimeoutError:
			message = None
		if message is None:
			_log.debug("[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " timed out")
			return None
		else:
			log_msg = "[" + _fmt_channel(context.source) + "]: prompt for " + context.author_name() + " received "
			log_msg += repr(message.content)
			_log.debug(log_msg)
			return type_conv(message.content[len(self._prefix * 2):])

	async def reply(self, context, message):
		"""
		Send a message in the same context as the message that caused the action to start.

		:type context: BotContext
		:param context: The context of the original message.
		:type message: str
		:param message: The message to send.
		"""
		if context.is_pm:
			dest = context.author
		else:
			dest = context.source
		await dest.send(message)
		_log.debug(_fmt_send(dest, message))

	async def reply_with_file(self, context, fp, filename=None, message=None):
		"""
		Send a file in the same context as the message that caused the action to start.

		:type context: BotContext
		:param context: The context of the original message.
		:type fp: Any
		:param fp: The file-like object to upload.
		:type filename: str
		:param filename: The name that the file will have once uploaded to the server.
		:type message: str
		:param message: A message to include before the file. Can be None to send only the file.
		"""
		if context.is_pm:
			dest = context.author
		else:
			dest = context.source

		await dest.send(content=message, file=discord.File(fp, filename=filename))
		_log.debug("[" + _fmt_channel(context.source) + "]: sent <FILE>")

	async def show_help(self, context, help_module=None):
		"""
		Display the help command in the current context.

		:type context: BotContext
		:param context: The context to show the help in.
		:type help_module: str
		:param help_module: The module to get additional info on. Can be a module or a command.
		"""
		pre = self._prefix
		if help_module is None:
			msg = "Sure! I'll tell you how to use my interface!\n\n"
			msg += "Here are my special commands:\n"
			msg += "* `" + pre + "help` - Shows this help.\n"
			msg += "* `" + pre + "version` - Shows the current version.\n"
			msg += "* `" + pre + "redeploy` - Pulls in the latest changes.\n"
			msg += "* `" + pre + "quit` - Immediately stops me from running.\n"
			msg += "* `" + pre + "op` - Gives a user operator permissions.\n"
			msg += "* `" + pre + "deop` - Takes away operator permissions from a user.\n"
			msg += "* `" + pre + "showops` - Shows all of my operators and masters.\n"
			msg += "* `" + pre + "replchars` - Shows/sets characters that are replaced before parsing.\n"
			msg += "\nHere are the modules that I'm running:\n"
			for m_name in self._bot_modules:
				m = self._bot_modules[m_name]
				invokes = ','.join('`' + pre + t.invocation + '`' for t in m.triggers if t.trigger_type == "INVOCATION")
				invokes = ' (' + invokes + ')' if invokes is not '' else ''
				msg += '* `' + m.name + "`" + invokes + " - " + m.description + "\n"

			msg += "\nFor more info, you can type `" + pre + "help` followed by the name of a module or built-in"
			msg += " command!"
		else:
			if help_module.startswith(pre):
				help_module = help_module[len(pre):]
			if help_module == "help":
				msg = "Oh, that's the command that you use to get me to give you info about other modules! You can"
				msg += " run it by itself, `" + pre + "help`, to just show the list of all commands and modules, or you"
				msg += " can you put a module name after it to find out about that module! But I guess you already know"
				msg += " that, eheheh ^_^"
			if help_module == "version":
				msg = "Oh, that's the command that tells you what version I am!"
			elif help_module == "quit":
				msg = "Mmm, `quit` is the command that will make me leave the server right away. It shuts me down"
				msg += " instantly, which is really really sad! It's a really powerful command, so only my masters and"
				msg += " operators are allowed to use it, okay?"
			elif help_module == "op":
				msg = "The `op` command turns any user into an operator. But, oh, of course, you have to already be an"
				msg += " op in order to run it! Otherwise anybody could control me!"
			elif help_module == "deop":
				msg = "The `deop` command takes away operator powers from any of my existing operators. B-but I won't"
				msg += " do that to any of my masters, so you can only do it to normal operators! Also, you have to"
				msg += " already be an operator in order to run this, just so you know!"
			elif help_module == "showops":
				msg = "Ah, that's the `showops` command! When you type this in, I'll tell you who my operators and"
				msg += " masters are, and also a little bit of info on each of them."
			elif help_module == "redeploy":
				msg = "The `redeploy` command is a really special command that will cause me to shut down, pull in the"
				msg += " latest updates from source control, and start back up again! This will only work if I was"
				msg += " started via the supervisor script `run-masabot.sh`; otherwise the command will just make me"
				msg += " shutdown, so please be careful! Oh, and remember that only my operators and masters can do"
				msg += " this!"
			elif help_module == "replchars":
				msg = "The `replchars` command shows all of the replacements that I do on text before trying to parse"
				msg += " it into a command that I understand! Oh! And also, my operators and masters can use this"
				msg += " command with an extra sub-command after it (`add` or `remove`) to change what replacements are"
				msg += " active:\n\n`replchars` by itself will list out all the replacements.\n`replchars add"
				msg += " <search> <replacement>` adds a new one.\n`replchars remove <search>` will remove an existing"
				msg += " one.\n\nNote that replacements apply to the actual command only, and not to the prefix!\n\n"
				msg += "**In order to make sure replacements don't mess up my system, replacements are never applied"
				msg += " to any invocations of the `replchars` command.** Additionally, the backslash character, the"
				msg += " non-curly double quote, and the non-curly single quote are never allowed to be replaced; also,"
				msg += " the space character can only be replaced in conjuction with other characters, and never by"
				msg += " itself. **Even if you're a master user or an operator.** I'm really sorry to restrict it like"
				msg += " that, but I have to in order to make sure I can keep running properly!"
			else:
				if help_module not in self._invocations and help_module not in self._bot_modules:
					msg = "Oh no! I'm sorry, <@!" + str(context.author.id) + ">, but I don't have any module or command"
					msg += " called '" + help_module + "'. P-please don't be mad! I'll really do my best at everything"
					msg += " else, okay?"
				else:
					m = self._bot_modules.get(help_module, None)
					if m is None:
						m = self._invocations[help_module][0]
					msg = "Oh yeah, the `" + m.name + "` module! `" + m.description + "`\n\n" + m.help_text
		await self.reply(context, msg)

	async def quit(self, context, restart_command="quit"):
		self.require_op(context, "quit", None)
		with open('.supervisor/restart-command', 'w') as fp:
			fp.write(restart_command)
		await self.reply(context, "Right away, <@!" + str(context.author.id) + ">! See you later!")
		_log.info("Shutting down...")
		self._master_timer_task.cancel()
		await self._client.logout()

	async def show_version(self, context):
		await self.reply(context, "I am Masabot v" + str(VERSION) + "!")

	async def run_replchars_command(self, context, action=None, search=None, replacement=None):
		"""
		Execute the replchars command. Depending on the action, this will either print out the info on current
		replacements, add a new replacement, or remove an existing replacement. Adding and removing require operator
		privileges.

		:type context: BotContext
		:param context: The context of the command.
		:type action: str
		:param action: The action to perform. Leave as None to just list the replacements. Set to "add" to add a new
		one, in which case both search and replacement must also be set. Set to "remove" to remove an existing
		replacement, in which case search must also be set
		:type search: str
		:param search: The sequence of characters to search for that is to be added/removed from the list of invocation
		replacements. Not used if action is None.
		:type replacement: str
		:param replacement: The sequence of characters to replace the search characters with. Only used when action is
		set to "add".
		"""
		if action is None:
			# only need to list the replacement chars, don't need privileges
			msg = "Okay, sure! Here's the list of replacements I do on commands you send me before I try to understand"
			msg += " what they say:\n\n"

			if len(self._invocation_replacements) < 1:
				msg += "...actually, now that I think about it, right now I don't do any replacements at all! I look"
				msg += " directly at anything you tell me without changing it at all.\n"
			else:
				for search in self._invocation_replacements:
					replacement = self._invocation_replacements[search]
					msg += "`" + search + "` becomes `" + replacement + "`\n"

			await self.reply(context, msg)
		elif action == "add":
			self.require_op(context, "replchars add", None)
			if search is None:
				msg = "I need to know the characters you want me to replace, and what you want to replace them with."
				raise BotSyntaxError(msg)
			if replacement is None:
				raise BotSyntaxError("I need to know what you want me to replace that string with.")

			# make sure we aren't borking masabot by setting a replacement for vital functionality
			if search == ' ':
				msg = "The single space is a core part of my command processing, so my programmers made it so I can't"
				msg += " set a replacement for just a single space by itself!"
				raise BotModuleError(msg)
			if '\\' in search or "'" in search or '"' in search:
				msg = "Non-curly single quotes, non-curly double quotes, and backslashes are a fundamental part of my"
				msg += " command processing, so my programmers made it so I can't set a replacement for any string that"
				msg += " contains even a single one of those!"
				raise BotModuleError(msg)

			cur_repl = ''
			if search in self._invocation_replacements:
				cur_repl = self._invocation_replacements[search]
				if cur_repl == replacement:
					await self.reply(context, "Well, I'm already replacing `" + search + "` with `" + cur_repl + "`.")
					return
				prompt_msg = "Right now, I'm replacing `" + search + "` with `" + cur_repl + "`. Do you want me to"
				prompt_msg += " start replacing it with `" + replacement + "` instead?"
			else:
				prompt_msg = "Just to make sure, you want me to start replacing `" + search + "` with `" + replacement
				prompt_msg += "`, right?"

			reply = await self.prompt_for_option(context, prompt_msg)
			msg = ""
			if reply is None:
				msg = "Sorry, but I didn't hear back from you on whether you wanted to add that new replacement..."
				msg += " I hope you're not just ignoring me, that'd make me really sad...\n\nLet me know if you want to"
				msg += " try adding a replacement again."
				raise BotModuleError(msg)
			elif reply == "no":
				msg = "You got it!"
				if search in self._invocation_replacements:
					msg += " I'll continue to replace `" + search + "` with `" + cur_repl + "` in commands, just like I"
					msg += " was doing before!"
				else:
					msg += " I'll keep on not replacing `" + search + "` in commands."
			elif reply == "yes":
				msg = "Okay!"
				if search in self._invocation_replacements:
					msg += " I'll start replacing `" + search + "` with `" + replacement + "` instead of `" + cur_repl
					msg += "` in commands!"
				else:
					msg += " From now on, I'll replace `" + search + "` with `" + replacement + "` in commands."
				self._invocation_replacements[search] = replacement
				_log.debug("Set new invocation replacement " + repr(search) + " -> " + repr(replacement))
				self._save_all()
			msg += "\n\nOh! But no matter what, I will never apply replacements to any invocation of the `replchars`"
			msg += " command."

			await self.reply(context, msg)

		elif action == "remove":
			self.require_op(context, "replchars remove", None)
			if search is None:
				msg = "I need to know the string you want me to stop replacing."
				raise BotSyntaxError(msg)

			if search not in self._invocation_replacements:
				msg = "Oh, okay. Actually, I was already not doing any replacements for `" + search + "`, so that works"
				msg += " out pretty well! Yay!"
				await self.reply(context, msg)
				return

			cur_repl = self._invocation_replacements[search]
			prompt_msg = "Okay, right now I'm replacing `" + search + "` with `" + cur_repl + "` in commands, and you"
			prompt_msg += " want me to stop doing that, right?"
			reply = await self.prompt_for_option(context, prompt_msg)

			msg = ""
			if reply is None:
				msg = "Sorry, but I didn't hear back from you on whether you wanted to remove that replacement..."
				msg += " Did you get busy doing something else? That's okay, it wasn't that important...\n\nLet me know"
				msg += " if you want to try removing a replacement again."
				raise BotModuleError(msg)
			elif reply == "no":
				msg = "Right! I'll continue to replace `" + search + "` with `" + cur_repl + "` in commands, just like"
				msg += " I was doing before!"
			elif reply == "yes":
				del self._invocation_replacements[search]
				_log.debug("Removed invocation replacement " + repr(search) + " -> " + repr(cur_repl))
				msg = "Sounds good! I'll stop replacing `" + search + "` with `" + cur_repl + "` in commands."
				self._save_all()
			await self.reply(context, msg)
		else:
			raise BotSyntaxError("The thing is, `" + str(action) + "` is just not a valid subcommand for `replchars`!")

	async def show_syntax_error(self, context, message=None):
		"""
		Show the standard syntax error message in the current message context.

		:type context: BotContext
		:param context: The current message context.
		:type message: str
		:param message: The message to include with the syntax error. Make it extremely brief; this function
		automatically handles setting up a sentence and apologizing to the user.
		:return:
		"""
		msg = "Um, oh no, I'm sorry <@!" + str(context.author.id) + ">, but I really have no idea what you mean..."
		if message is not None:
			msg += " " + message
		msg += "\n\nBut, oh! I know!"
		msg += " If you're having trouble, maybe the command `" + self._prefix + "help` can help you!"
		await self.reply(context, msg)

	def require_op(self, context, command, module, message="Operation requires operator status"):
		"""
		Ensure that the user that invoked a command has operator permission. If the user does not have operator
		permission, a BotPermissionError is raised.

		:type context: BotContext
		:param context: The context of the command. Must contain the author that invoked it.
		:type command: str
		:param command: A string representing the command that is attempting to be executed. This should include enough
		of the invocation to distinguish it from other potential invocations of the same command.
		:type module:  str | None
		:param module: The module that is requiring operator permissions. This can be set to None if it is a built-in
		command that is requiring op.
		:type message: str
		:param message: The message to put in the bot permission error if the check for op fails. This can be left as
		the default, as a suitable error message will be generated from the other properties if this method is called
		from within a core command function or from within one of a module's on_X methods().
		"""
		if context.author.id not in self._operators:
			raise BotPermissionError(context, command, module, message=message)

	async def show_ops(self, context):
		msg = "Okay, sure! Here's a list of all of my operators:\n\n"
		for u in self._operators:
			all_info = self._client.get_user(u)
			op_info = self._operators[u]
			msg += "* " + all_info.name + "#" + all_info.discriminator + " _(" + op_info['role'] + ")_\n"
		await self.reply(context, msg)

	async def pm_master_users(self, message):
		masters = [x for x in self._operators.keys() if self._operators[x]['role'] == 'master']
		for m in masters:
			user = self._client.get_user(m)
			await user.send(message)

	def get_user(self, snowflake_id) -> Optional[discord.User]:
		"""
		Get a user from a snowflake ID.

		:type snowflake_id: int
		:param snowflake_id: The ID.
		:return: The user.
		"""
		return self._client.get_user(snowflake_id)

	async def _run_timer(self):
		await self._client.wait_until_ready()
		_log.debug("Master timer started")
		tick_span = 60  # seconds

		while not self._client.is_closed:
			now_time = time.monotonic()
			for timer in self._timers:
				timer.tick(now_time, lambda msg: self.pm_master_users(msg))

			await asyncio.sleep(tick_span)

	async def _make_op(self, context, args):
		self.require_op(context, "op", None)

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want to turn into an op")

		user, is_bot = util.parse_user(args[0])

		if is_bot:
			msg = "Well, the thing is, <@&" + str(user) + "> is *also* a bot and I'm really afraid of having another bot"
			msg += " control me. It could be unsafe, and, Deka-nee told me I shouldn't do that!"
			await self.reply(context, msg)
			return
		if user in self._operators:
			await self.reply(context, "Oh! <@!" + str(user) + "> is already an op! So yay!")
			return
		else:
			self._operators[user] = {'role': 'operator'}
			_log.debug("Added new operator (UID " + str(user) + ")")
			self._save_all()
			await self.reply(context, "<@!" + str(user) + "> is now an op! Hooray!")

	async def _make_nonop(self, context, args):
		self.require_op(context, "deop", None)

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want to deop")

		user, is_bot = util.parse_user(args[0])
		if user not in self._operators:
			await self.reply(context, "It looks like <@!" + str(user) + "> is already not an op.")
			return
		else:
			if self._operators[user]['role'] == 'master':
				msg = "Sorry, but <@!" + str(user) + "> is one of my masters, and I could never remove their operator"
				msg += " status!"
				await self.reply(context, msg)
			else:
				del self._operators[user]
				_log.debug("Removed operator (UID " + str(user) + ")")
				self._save_all()
				await self.reply(context, "Okay. <@!" + str(user) + "> is no longer an op.")

	async def _redeploy(self, context, reason=None):
		self.require_op(context, "redeploy", None)
		if reason is not None:
			with open('.supervisor/reason', 'w') as fp:
				fp.write(reason)
		_log.info("Going down for a redeploy")
		msg = "Oh! It looks like " + context.author_name() + " has triggered a redeploy. I'll be going down now, but"
		msg += " don't worry! I'll be right back!"
		await self.announce(msg)
		await self.quit(context, "redeploy")

	# noinspection PyMethodMayBeStatic
	def _check_supervisor_unclean_shutdown(self):
		"""
		Retrieve whether the last shutdown was clean, and then clean the source data containing that information.

		Check if the last shutdown was a clean one. If it was not, give the reason as well. If the current execution is
		the first time the bot is started, or if the last shutdown of the bot was caused by an intention to quit from
		within the bot (e.g. by calling bot.quit()), the first element of the returned tuple will be True, and the
		second will always be None. If the shutdown happened by another means, the first element will be False, and the
		second will be the reason for unclean shutdown if one was provided by the supervisor invocation system.

		Note that calling this function will cause the source files where the information was read from to be removed,
		so all invocations after the first one will not contain valid information.

		:rtype: (bool, str)
		:return: A tuple containing whether the shutdown was clean and the reason for unclean shutdown
		"""
		if not os.path.exists('.supervisor/unclean-shutdown'):
			return True, None
		with open('.supervisor/unclean-shutdown') as fp:
			info = json.load(fp)
		os.remove('.supervisor/unclean-shutdown')
		reason = info.get('reason', None)
		return False, reason

	async def _check_supervisor_files(self):
		# NOTE: this function does not check for .supervisor/unclean-shutdown; that functionality is elsewhere
		if not os.path.exists('.supervisor/status'):
			return
		_log.debug("Returning from redeploy...")
		with open('.supervisor/status', 'r') as fp:
			status = json.load(fp)
		if os.path.exists('.supervisor/reason'):
			with open('.supervisor/reason', 'r') as fp:
				reason = fp.read()
			os.remove('.supervisor/reason')
		else:
			reason = None
		os.remove('.supervisor/status')
		action = status['action']
		msg = None
		if action == 'redeploy' or action == 'deploy':
			if action == 'redeploy' and status['success']:
				msg = "My redeploy completed! Yay, everything went well!\n\n"

				if len(status['packages']) < 1:
					msg += "There were no changes to my dependencies."
				else:
					msg += "Hmm, hmm? Something feels funny! Oh! My dependencies have been updated!"
					new_packs = []
					old_packs = []
					for pkg in status['packages']:
						change = status['packages'][pkg]
						if change['action'] == 'install':
							new_packs.append(pkg)
						elif change['action'] == 'uninstall':
							old_packs.append(pkg)
					if len(new_packs) > 0:
						msg += " I added these ones: " + ', '.join('`' + x + '`' for x in new_packs) + '.'
					if len(old_packs) > 0:
						msg += " I removed these ones: " + ', '.join('`' + x + '`' for x in old_packs) + '.'
					msg += " Now I feel all fresh and new ^_^"

				if reason is not None:
					msg += "\n\n--------\n\nOh! Oh! I gotta tell you! The whole reason I went down is because " + reason
				else:
					msg = None
			elif not status['success']:
				msg = "Oh no, it looks like something went wrong during my " + action + " :c\n\n"
				if not status['check_package_success']:
					msg += "Something went wrong when I was looking for new packages to install!\n\n"
				msg += "```\n" + status['message'] + "\n"
				if len(status['packages']) > 0:
					msg += '\n'
				for pkg in status['packages']:
					change = status['packages'][pkg]
					ch_status = "FAILURE" if not change['success'] else "success"
					ch_msg = "\n"
					if not change['success']:
						ch_msg = " -\n" + change['message'] + "\n"
					msg += "* " + pkg + ": " + change['action'] + " " + ch_status + ch_msg
				msg += "```"
			if msg is not None:
				await self.announce(msg)

	def _load_modules(self, state_dict, module_configs):
		names = []
		_log.debug("Loading modules...")
		for module_str in commands.__all__:
			new_invoke_handlers = _copy_handler_dict(self._invocations)
			new_regex_handlers = _copy_handler_dict(self._regex_handlers)
			new_mention_handlers = {
				'any': list(self._any_mention_handlers),
				'self': list(self._self_mention_handlers),
				'specific': _copy_handler_dict(self._mention_handlers)
			}
			new_timer_handlers = list(self._timers)
			mod = importlib.import_module("masabot.commands." + module_str)
			bot_module = mod.BOT_MODULE_CLASS(self, 'resources')
			if bot_module.name in names:
				raise BotModuleError("cannot load duplicate module '" + bot_module.name + "'")
			for t in bot_module.triggers:
				if t.trigger_type == 'INVOCATION':
					self._add_new_invocation_handler(bot_module, t, new_invoke_handlers)
				elif t.trigger_type == 'MENTION':
					self._add_new_mention_handler(bot_module, t, new_mention_handlers)
				elif t.trigger_type == 'REGEX':
					self._add_new_regex_handler(bot_module, t, new_regex_handlers)
				elif t.trigger_type == 'TIMER':
					self._add_new_timer_handler(bot_module, t, new_timer_handlers)
			if bot_module.has_state and bot_module.name in state_dict:
				if state_dict[bot_module.name] is not None:
					bot_module.set_state(state_dict[bot_module.name])

			bot_module.load_config(module_configs.get(bot_module.name, {}))

			self._bot_modules[bot_module.name] = bot_module
			self._invocations = new_invoke_handlers
			self._regex_handlers = new_regex_handlers
			self._mention_handlers = new_mention_handlers['specific']
			self._self_mention_handlers = new_mention_handlers['self']
			self._any_mention_handlers = new_mention_handlers['any']
			names.append(bot_module.name)
			_log.debug("Added module '" + bot_module.name + "'")
		_log.debug("Done loading modules")

	# noinspection PyMethodMayBeStatic
	def _add_new_timer_handler(self, bot_module, trig, current_handlers):
		"""
		Checks a timer handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as an invocation handler.
		:type trig: commands.TimerTrigger
		:param trig: The trigger that specifies the amount of time between timer firings.
		:type current_handlers: list[Timer]
		:param current_handlers: The timer handlers that already exist. The new handler will be added to the end.
		"""

		timer = Timer(bot_module, int(trig.timer_duration.total_seconds()))
		current_handlers.append(timer)

	# noinspection PyMethodMayBeStatic
	def _add_new_invocation_handler(self, bot_module, trig, current_handlers):
		"""
		Checks an invocation handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as an invocation handler.
		:type trig: commands.InvocationTrigger
		:param trig: The trigger that specifies the invocation to be handled.
		:type current_handlers: dict[str, list[commands.BotBehaviorModule]]
		:param current_handlers: The invocation handlers that already exist. The new handler will be added to the end of
		the relevant one.
		"""
		if trig.invocation in current_handlers:
			err_msg = "Duplicate invocation '" + trig.invocation + "' in module '" + bot_module.name + "';"
			err_msg += " already defined in '" + current_handlers[trig.invocation][-1].name + "' module"
			_log.warning(err_msg)
		else:
			current_handlers[trig.invocation] = []
		current_handlers[trig.invocation].append(bot_module)

	# noinspection PyMethodMayBeStatic
	def _add_new_mention_handler(self, bot_module, trig, current_handlers):
		"""
		Checks a mention handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as a mention handler.
		:type trig: commands.MentionTrigger
		:param trig: The trigger that specifies the mention type to be handled.
		:type current_handlers: dict[str, list[commands.BotBehaviorModule] | dict[str, commands.BotBehaviorModule]]
		:param current_handlers: The mention handlers that already exist. The new handler will be added to the end of
		the relevant one.
		"""

		mts = trig.mention_targets
		if mts['target_type'] == 'any':
			current_handlers['any'].append(bot_module)
		elif mts['target_type'] == 'self':
			current_handlers['self'].append(bot_module)
		elif mts['target_type'] == 'specific':
			for name in mts['names']:
				if name in current_handlers['specific']:
					err_msg = "Duplicate mention handler '" + name + "' in module '" + bot_module.name
					err_msg += "'; already defined in '" + current_handlers['specific'][name][-1].name + "'"
					err_msg += " module"
					_log.warning(err_msg)
				else:
					current_handlers['specific'][name] = []
				current_handlers['specific'][name].append(bot_module)

	# noinspection PyMethodMayBeStatic
	def _add_new_regex_handler(self, bot_module, trig, current_handlers):
		"""
		Checks a regex handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as a regex handler.
		:type trig: commands.RegexTrigger
		:param trig: The trigger that specifies the regex to look for.
		:type current_handlers: dict[typing.Pattern, BotModule]
		:param current_handlers: The regex handlers that already exist. The new handler will be added to the end of it.
		"""
		reg = trig.regex
		regex = re.compile(reg, re.DOTALL)
		if regex in current_handlers:
			err_msg = "Duplicate regex handler for '" + regex.pattern + "' in module '" + bot_module.name
			err_msg += "'; already defined in '" + current_handlers[regex][-1].name + "'"
			err_msg += " module"
			_log.warning(err_msg)
		else:
			current_handlers[regex] = []
		current_handlers[regex].append(bot_module)

	async def _handle_invocation(self, message):
		context = BotContext(message)
		meta = MessageMetadata.from_message(message)

		log_msg = "[" + _fmt_channel(context.source) + "]: received invocation " + repr(message.content)
		log_msg += " from " + str(context.author.id) + "/" + context.author_name()
		_log.debug(log_msg)

		try:
			tokens = self._message_to_tokens(message)
		except ValueError as e:
			await self.show_syntax_error(context, str(e))
			return
		cmd = tokens[0]
		args = tokens[1:]

		if cmd == 'help':
			help_cmd = None
			if len(args) > 0:
				help_cmd = args[0]
			await self._execute_action(context, self.show_help(context, help_cmd))
		elif cmd == 'quit':
			await self._execute_action(context, self.quit(context))
		elif cmd == 'op':
			await self._execute_action(context, self._make_op(context, args))
		elif cmd == 'deop':
			await self._execute_action(context, self._make_nonop(context, args))
		elif cmd == 'showops':
			await self._execute_action(context, self.show_ops(context))
		elif cmd == 'version':
			await self._execute_action(context, self.show_version(context))
		elif cmd == 'redeploy':
			if len(args) > 0:
				reason = args[0]
			else:
				reason = None
			await self._execute_action(context, self._redeploy(context, reason))
		elif cmd == 'replchars':
			action = None
			search = None
			repl = None
			if len(args) > 0:
				action = args[0]
			if len(args) > 1:
				search = args[1]
			if len(args) > 2:
				repl = args[2]
			await self._execute_action(context, self.run_replchars_command(context, action, search, repl))
		elif cmd in self._invocations:
			for handler in self._invocations[cmd]:
				await self._execute_action(context, handler.on_invocation(context, meta, cmd, *args), handler)
		else:
			_log.debug("Ignoring unknown command " + repr(cmd))

	async def _handle_mention(self, message):
		handled_already = []
		mentions = message.raw_mentions
		context = BotContext(message)
		meta = MessageMetadata.from_message(message)

		log_msg = "[" + _fmt_channel(context.source) + "]: received mentions (" + ", ".join(repr(x) for x in mentions)
		log_msg += ") " + repr(message.content) + " from " + str(context.author.id) + "/" + context.author_name()
		_log.debug(log_msg)

		if len(self._any_mention_handlers) > 0:
			for h in self._any_mention_handlers:
				if h.name not in handled_already:
					await self._execute_action(context, h.on_mention(context, meta, message.content, mentions), h)
					handled_already.append(h.name)

		if '<@' + str(self._client.user.id) + '>' in mentions or '<@!' + str(self._client.user.id) + '>' in mentions:
			for h in self._self_mention_handlers:
				if h.name not in handled_already:
					await self._execute_action(context, h.on_mention(context, meta, message.content, mentions), h)
					handled_already.append(h.name)

		for m in mentions:
			if m in self._mention_handlers:
				for h in self._mention_handlers[m]:
					if h.name not in handled_already:
						await self._execute_action(context, h.on_mention(context, meta, message.content, mentions), h)
						handled_already.append(h.name)

	async def _handle_regex_scan(self, message):
		context = BotContext(message)
		meta = MessageMetadata.from_message(message)
		for regex in self._regex_handlers:
			h_list = self._regex_handlers[regex]

			m = regex.search(message.content)
			if m is not None:
				log_msg = "[" + _fmt_channel(context.source) + "]: received regex match (" + repr(regex.pattern) + ") "
				log_msg += repr(message.content) + " from " + str(context.author.id) + "/" + context.author_name()
				_log.debug(log_msg)
				match_groups = []
				for i in range(regex.groups+1):
					match_groups.append(m.group(i))
				for h in h_list:
					await self._execute_action(context, h.on_regex_match(context, meta, *match_groups), h)

	async def _execute_action(self, context, action, mod=None):
		try:
			mod_name = repr(mod.name) if mod is not None else "core"
			_log.debug("Executing registered action in " + mod_name + " module...")
			await action
		except BotPermissionError as e:
			msg = "User " + e.author.name + "#" + e.author.discriminator + " (ID: " + str(e.author.id) + ") was denied"
			msg += " permission to execute privileged command " + repr(e.command)
			if e.module is not None:
				msg += " in module " + repr(e.module)
			msg += "."
			_log.error(msg)
			msg = "Sorry, <@!" + str(e.author.id) + ">, but only my masters and operators can do that."
			ctx = context
			if e.context is not None:
				ctx = e.context
			await self.reply(ctx, msg)
		except BotSyntaxError as e:
			_log.exception("Syntax error")
			ctx = context
			if e.context is not None:
				ctx = e.context
			await self.show_syntax_error(ctx, str(e))
		except BotModuleError as e:
			_log.exception("Module error")
			msg = "Oh no, <@!" + str(context.author.id) + ">-samaaaaa! I can't quite do that! "
			ctx = context
			if e.context is not None:
				ctx = e.context
			await self.reply(ctx, msg + str(e))

		if mod is not None and mod.has_state:
			self._save_all()

	def _message_to_tokens(self, message):
		"""
		Converts a message to a series of tokens for parsing into an invocation.

		:type message: discord.Message
		:param message: The message whose contents are to be parsed.
		:rtype: list[str]
		:return: The tokens.
		"""
		content = message.content[len(self._prefix):]
		""":type : str"""

		# special case; do NOT apply replacements if the replchars command is being invoked:
		pre_analyze = shlex.split(content)
		if pre_analyze[0] == 'replchars':
			tokens = pre_analyze
		else:
			for search in self._invocation_replacements:
				replacement = self._invocation_replacements[search]
				content = content.replace(search, replacement)

			tokens = shlex.split(content)

		return tokens

	def _load_builtin_state(self, state_dict):
		if '__BOT__' not in state_dict:
			return
		builtin_state = state_dict['__BOT__']

		if 'operators' in builtin_state:
			for op in builtin_state['operators']:
				# master roles will be loaded later during config reading
				self._operators[int(op)] = {'role': 'operator'}

		if 'invocation_replacements' in builtin_state:
			self._invocation_replacements = dict(builtin_state['invocation_replacements'])

	def _save_all(self):
		state_dict = {'__BOT__': {
			'operators': list(self._operators.keys()),
			'invocation_replacements': dict(self._invocation_replacements),
		}}

		for m_name in self._bot_modules:
			mod = self._bot_modules[m_name]
			if mod.has_state:
				state_dict[mod.name] = mod.get_state()

		with open("state.p", "wb") as fp:
			pickle.dump(state_dict, fp)

		_log.debug("Saved state to disk")


def start():
	if not os.path.exists('resources'):
		os.mkdir('resources')
	bot = MasaBot("config.json")
	try:
		bot.run()
	except KeyboardInterrupt:
		# this is a normal shutdown, so notify any supervisor by writing to the restart-command file
		with open('.supervisor/restart-command', 'w') as fp:
			fp.write("quit")
		raise


def _copy_handler_dict(dict_to_copy):
	new_dict = {}
	for k in dict_to_copy:
		v = dict_to_copy[k]
		if type(v) == list:
			new_dict[k] = list(v)
		else:
			new_dict[k] = v
	return new_dict
