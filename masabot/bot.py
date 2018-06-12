import importlib
import logging
import pickle
import discord
import traceback
import os
import asyncio
import time
import re
import shlex
from . import configfile, commands, util


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class BotSyntaxError(Exception):
	def __init__(self, message):
		super().__init__(message)


class BotPermissionError(Exception):
	def __init__(self, message):
		super().__init__(message)


class BotModuleError(RuntimeError):
	def __init__(self, message):
		super().__init__(message)


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

		# noinspection PyBroadException
		try:
			await self.bot_module.on_timer_fire()
		except Exception as e:
			_log.exception("Encountered error in timer-triggered function")
			msg = "Exception in firing timer of '" + self.bot_module.name + "' module:\n\n```python\n"
			msg += traceback.format_exc()
			msg += "\n```"
			await on_error


class BotContext(object):

	def __init__(self, message):
		self.source = message.channel
		self.author = message.author
		self.is_pm = self.source.is_private and len(self.source.recipients) == 1


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
		self._master_timer_task = None

		state_dict = {}
		try:
			with open('state.p', 'rb') as fp:
				state_dict = pickle.load(fp)
		except FileNotFoundError:
			pass
		else:
			for op in state_dict['__BOT__']['operators']:
				self._operators[op] = {'role': 'operator'}

		conf = configfile.load_config(config_file)

		for m in conf['masters']:
			self._operators[m] = {'role': 'master'}
		self._api_key = conf['discord-api-key']
		self._prefix = conf['prefix']
		self._announce_channels = conf['announce-channels']

		self.client = discord.Client()

		@self.client.event
		async def on_ready():
			_log.info("Logged in as " + self.client.user.name)
			_log.info("ID: " + self.client.user.id)

			if self.client.user.avatar_url == '':
				with open('avatar.png', 'rb') as fp:
					avatar_data = fp.read()
				await self.client.edit_profile(avatar=avatar_data)

			_log.info("Connected to servers:")
			for c in self.client.servers:
				_log.info("* " + str(c))
				for ch in c.channels:
					if ch.type == discord.ChannelType.text and ('#' + ch.name) in self._announce_channels:
						await self.client.send_message(ch, "Hello! I'm now online ^_^")

		@self.client.event
		async def on_message(message):
			if message.author.id == self.client.user.id:
				return  # don't answer own messages
			if message.content.startswith(self._prefix):
				await self._handle_invocation(message)
			else:
				if len(message.raw_mentions) > 0:
					await self._handle_mention(message)

				await self._handle_regex_scan(message)

		@self.client.event
		async def on_error(event, *args, **kwargs):
			message = args[0]
			e = traceback.format_exc()
			logging.exception("Exception in main loop")
			msg = "I...I'm really sorry, but... um... I just had an exception :c\n\n```\n" + e + "\n```"
			await self.client.send_message(message.channel, msg)

		self._load_modules(state_dict, conf['modules'])

	def run(self):
		self._master_timer_task = self.client.loop.create_task(self._run_timer())
		self.client.run(self._api_key)

	async def reply_typing(self, context):
		"""
		Sends to the correct reply context that MasaBot has started typing.

		:param context: The context to reply with.
		"""
		if context.is_pm:
			await self.client.send_typing(context.author)
		else:
			await self.client.send_typing(context.source)

	async def prompt_for_option(self, context, message, option_1="yes", option_2="no", *additional_options):
		"""
		Prompts the user to select an option. Not case-sensitive; all options are converted to lower-case. Times out
		after 60 seconds, and returns None then.

		:param context: The context of the bot.
		:param message: The message to show before the prompt.
		:param option_1: The first option.
		:param option_2: The second option.
		:param additional_options: Any additional options.
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

		def check_option(msg):
			return msg.content in all_options

		message = await self.client.wait_for_message(timeout=60, author=context.author, check=check_option)
		if message is None:
			return None
		else:
			return all_options[message.content]

	async def reply(self, context, message):
		if context.is_pm:
			await self.client.send_message(context.author, message)
		else:
			await self.client.send_message(context.source, message)

	async def reply_with_file(self, context, fp, filename=None, message=None):
		if context.is_pm:
			await self.client.send_file(context.author, fp, filename=filename, content=message)
		else:
			await self.client.send_file(context.source, fp, filename=filename, content=message)

	async def show_help(self, context, help_module=None):
		pre = self._prefix
		if help_module is None:
			msg = "Sure! I'll tell you how to use my interface!\n\n"
			msg += "Here are my special commands:\n"
			msg += "* `" + pre + "help` - Shows this help.\n"
			msg += "* `" + pre + "redeploy` - Pulls in the latest changes.\n"
			msg += "* `" + pre + "quit` - Immediately stops me from running.\n"
			msg += "* `" + pre + "op` - Gives a user operator permissions.\n"
			msg += "* `" + pre + "deop` - Takes away operator permissions from a user.\n"
			msg += "* `" + pre + "showops` - Shows all of my operators and masters.\n"
			msg += "\nHere are the modules that I'm running:\n"
			for m_name in self._bot_modules:
				m = self._bot_modules[m_name]
				invokes = ','.join('`' + pre + t.invocation + '`' for t in m.triggers if t.trigger_type == "INVOCATION")
				invokes = ' (' + invokes + ')' if invokes is not '' else ''
				msg += '* `' + m.name + "`" + invokes + " - " + m.description + "\n"

			msg += "\nFor more info, you can type `" + pre + "help` followed by the name of a module or built-in"
			msg += " command!"
			await self.reply(context, msg)
		else:
			if help_module.startswith(pre):
				help_module = help_module[len(pre):]
			if help_module == "help":
				msg = "Oh, that's the command that you use to get me to give you info about other modules! You can"
				msg += " run it by itself, `" + pre + "help`, to just show the list of all commands and modules, or you"
				msg += " can you put a module name after it to find out about that module! But I guess you already know"
				msg += " that, eheheh ^_^"
				await self.reply(context, msg)
			elif help_module == "quit":
				msg = "Mmm, `quit` is the command that will make me leave the server right away. It shuts me down"
				msg += " instantly, which is really really sad! It's a really powerful command, so only my masters and"
				msg += " operators are allowed to use it, okay?"
				await self.reply(context, msg)
			elif help_module == "op":
				msg = "The `op` command turns any user into an operator. But, oh, of course, you have to already be an"
				msg += " op in order to run it! Otherwise anybody could control me!"
				await self.reply(context, msg)
			elif help_module == "deop":
				msg = "The `deop` command takes away operator powers from any of my existing operators. B-but I won't"
				msg += " do that to any of my masters, so you can only do it to normal operators! Also, you have to"
				msg += " already be an operator in order to run this, just so you know!"
				await self.reply(context, msg)
			elif help_module == "showops":
				msg = "Ah, that's the `showops` command! When you type this in, I'll tell you who my operators and"
				msg += " masters are, and also a little bit of info on each of them."
				await self.reply(context, msg)
			elif help_module == "redeploy":
				msg = "The `redeploy` command is a really special command that will cause me to shut down, pull in the"
				msg += " latest updates from source control, and start back up again! This will only work if I was"
				msg += " started via the supervisor script `run-masabot.sh`; otherwise the command will just make me"
				msg += " shutdown, so please be careful! Oh, and remember that only my operators and masters can do"
				msg += " this!"
				await self.reply(context, msg)
			else:
				if help_module not in self._bot_modules:
					msg = "Oh no! I'm sorry, <@!" + context.author.id + ">, but I don't have any module called '"
					msg += help_module + "'. P-please don't be mad! I'll really do my best at everything else, okay?"
					await self.reply(context, msg)
				else:
					m = self._bot_modules[help_module]
					msg = "Oh yeah, the `" + help_module + "` module! " + m.description + "\n\n" + m.help_text
					await self.reply(context, msg)

	async def quit(self, context):
		self.require_op(context, "Unprivileged user " + context.author.id + " attempted to execute `quit`")
		await self.reply(context, "Right away, <@!" + context.author.id + ">! See you later!")
		self._master_timer_task.cancel()
		await self.client.logout()

	async def show_syntax_error(self, context, message=None):
		msg = "Um, oh no, I'm sorry <@!" + context.author.id + ">, but I really have no idea what you mean..."
		if message is not None:
			msg += " " + message
		msg += "\n\nBut, oh! I know!"
		msg += " If you're having trouble, maybe the command `" + self._prefix + "help` can help you!"
		await self.reply(context, msg)

	def require_op(self, context, message="Operation requires operator status"):
		if context.author.id not in self._operators:
			raise BotPermissionError(message)

	async def show_ops(self, context):
		msg = "Okay, sure! Here's a list of all of my operators:\n\n"
		for u in self._operators:
			all_info = await self.client.get_user_info(u)
			op_info = self._operators[u]
			msg += "* " + all_info.name + "#" + all_info.discriminator + " _(" + op_info['role'] + ")_\n"
		await self.reply(context, msg)

	async def pm_master_users(self, message):
		masters = [x for x in self._operators.keys() if self._operators[x]['role'] == 'master']
		for m in masters:
			user = await self.client.get_user_info(m)
			await self.client.send_message(user, message)

	async def _run_timer(self):
		await self.client.wait_until_ready()
		_log.debug("Master timer started")
		tick_span = 60  # seconds

		while not self.client.is_closed:
			now_time = time.monotonic()
			for timer in self._timers:
				timer.tick(now_time, lambda msg: self.pm_master_users(msg))

			await asyncio.sleep(tick_span)

	async def _make_op(self, context, args):
		self.require_op(context, "Unprivileged user " + context.author.id + " attempted to execute `op`")

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want to turn into an op")

		try:
			user = util.get_uid_from_mention(args[0])
		except ValueError:
			raise BotSyntaxError("'" + args[0] + "' is not a valid user")

		if user in self._operators:
			await self.reply(context, "Oh! <@!" + user + "> is already an op! So yay!")
			return
		else:
			self._operators[user] = {'role': 'operator'}
			self._save_all()
			await self.reply(context, "<@!" + user + "> is now an op! Hooray!")

	async def _make_nonop(self, context, args):
		self.require_op(context, "Unprivileged user " + context.author.id + " attempted to execute `unop`")

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you don't want to be an op")

		try:
			user = util.get_uid_from_mention(args[0])
		except ValueError:
			raise BotSyntaxError("'" + args[0] + "' is not a valid user")

		if user not in self._operators:
			await self.reply(context, "It looks like <@!" + user + "> is already not an op.")
			return
		else:
			if self._operators[user]['role'] == 'master':
				msg = "Sorry, but <@!" + user + "> is one of my masters, and I could never remove their operator"
				msg += " status!"
				await self.reply(context, msg)
			else:
				del self._operators[user]
				self._save_all()
				await self.reply(context, "Okay. <@!" + user + "> is no longer an op.")

	async def _redeploy(self, context):
		self.require_op(context)
		with open('.supervisor-redeploy', 'w') as fp:
			os.utime('.supervisor-redeploy', None)
		_log.info("Going down for a redeploy")
		await self.quit(context)

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
			bot_module = mod.BOT_MODULE_CLASS(self)
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

		try:
			tokens = shlex.split(message.content[len(self._prefix):])
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
		elif cmd == 'redeploy':
			await self._execute_action(context, self._redeploy(context))
		elif cmd in self._invocations:
			for handler in self._invocations[cmd]:
				await self._execute_action(context, handler.on_invocation(context, cmd, *args), handler)

	async def _handle_mention(self, message):
		handled_already = []
		mentions = message.raw_mentions
		context = BotContext(message)

		if len(self._any_mention_handlers) > 0:
			for h in self._any_mention_handlers:
				if h.name not in handled_already:
					await self._execute_action(context, h.on_mention(context, message.content, mentions), h)
					handled_already.append(h.name)

		if '<@' + self.client.user.id + '>' in mentions or '<@!' + self.client.user.id + '>' in mentions:
			for h in self._self_mention_handlers:
				if h.name not in handled_already:
					await self._execute_action(context, h.on_mention(context, message.content, mentions), h)
					handled_already.append(h.name)

		for m in mentions:
			if m in self._mention_handlers:
				for h in self._mention_handlers[m]:
					if h.name not in handled_already:
						await self._execute_action(context, h.on_mention(context, message.content, mentions), h)
						handled_already.append(h.name)

	async def _handle_regex_scan(self, message):
		context = BotContext(message)
		for regex in self._regex_handlers:
			h_list = self._regex_handlers[regex]

			m = regex.search(message.content)
			if m is not None:
				match_groups = []
				for i in range(regex.groups+1):
					match_groups.append(m.group(i))
				for h in h_list:
					await self._execute_action(context, h.on_regex_match(context, *match_groups), h)

	async def _execute_action(self, context, action, mod=None):
		try:
			if mod is not None and mod.requires_op:
				msg = "Unprivileged user " + context.author.id + " attempted a privileged action in '" + mod.name + "'"
				raise BotPermissionError(msg)

			await action
		except BotPermissionError as e:
			_log.warning(str(e))
			_log.exception("Permission error")
			msg = "Sorry, <@!" + context.author.id + ">, but only my masters and operators can do that."
			await self.reply(context, msg)
		except BotSyntaxError as e:
			await self.show_syntax_error(context, str(e))
		except BotModuleError as e:
			_log.exception("Module error")
			msg = "Oh no, <@!" + context.author.id + ">-samaaaaa! I can't quite do that! "
			await self.reply(context, msg + str(e))

		if mod is not None and mod.has_state:
			self._save_all()

	def _save_all(self):
		state_dict = {'__BOT__': {
			'operators': list(self._operators.keys())
		}}
		for m_name in self._bot_modules:
			mod = self._bot_modules[m_name]
			if mod.has_state:
				state_dict[mod.name] = mod.get_state()

		with open("state.p", "wb") as fp:
			pickle.dump(state_dict, fp)


def start():
	bot = MasaBot("config.json")
	bot.run()


def _copy_handler_dict(dict_to_copy):
	new_dict = {}
	for k in dict_to_copy:
		v = dict_to_copy[k]
		if type(v) == list:
			new_dict[k] = list(v)
		else:
			new_dict[k] = v
	return new_dict
