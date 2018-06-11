import importlib
import logging
import pickle
import discord
import traceback
import sys
import asyncio
import re
import shlex
from . import configfile, commands


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


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
		self._invocations = {}
		self._mention_handlers = {}
		self._self_mention_handlers = []
		self._any_mention_handlers = []
		self._regex_handlers = {}
		self._operators = {}

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
				self._handle_invocation(message)
			else:
				if len(message.raw_mentions) > 0:
					self._handle_mention(message)

				self._handle_regex_scan(message)

		@self.client.event
		async def on_error(event, *args, **kwargs):
			message = args[0]
			exc_info = sys.exc_info()
			e = str(exc_info[1])
			logging.exception("Exception in main loop")
			msg = "Oh my goodness! I just had an exception :c\n\n```\n" + e + "\n```"
			await self.client.send_message(message.channel, msg)

		self._load_modules(state_dict)

	def run(self):
		self.client.run(self._api_key)

	async def reply(self, context, message):
		if context.is_pm:
			await self.client.send_message(context.author, message)
		else:
			await self.client.send_message(context.source, message)

	async def show_help(self, context, help_module=None):
		pre = self._prefix
		if help_module is None:
			msg = "Sure! I'll tell you how to use my interface!\n\n"
			msg += "Here are my special commands:\n"
			msg += "`" + pre + "help` - Shows this help. You can give me a module after 'help' and I'll tell you how to"
			msg += " use it!\n"
			msg += "`" + pre + "quit` - Immediately stops me from running.\n"
			msg += "\nHere are the modules that I'm running:\n"
			for m_name in self._bot_modules:
				m = self._bot_modules[m_name]
				invokes = ','.join('`' + pre + t.invocation + '`' for t in m.triggers if t.trigger_type == "INVOCATION")
				invokes = ' (' + invokes + ')' if invokes is not '' else ''
				msg += '`' + m.name + "`" + invokes + " - " + m.description + "\n"
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
		if context.author.id not in self._operators:
			msg = "Unprivileged user " + context.author.id + " attempted a privileged quit"
			_log.warning(msg)
			msg = "Sorry, <@!" + context.author.id + ">, but only my masters and operators can do that."
			await self.reply(context, msg)
			return
		await self.reply(context, "Right away, <@!" + context.author.id + ">! See you later!")
		await self.client.logout()

	async def show_syntax_error(self, context, message=None):
		msg = "Um, oh no, I'm sorry <@!" + context.author.id + ">, but I really have no idea what you mean..."
		if message is not None:
			msg += " " + message
		msg += "But, oh! I know!"
		msg += " If you're having trouble, maybe the command `" + self._prefix + "help` can help you!"
		await self.reply(context, msg)

	async def make_op(self, context, user):
		pass

	def _load_modules(self, state_dict):
		names = []
		_log.debug("loading modules")
		for module_str in commands.__all__:
			mod = importlib.import_module("masabot.commands." + module_str)
			bot_module = mod.BOT_MODULE_CLASS(self)
			if bot_module.name in names:
				raise commands.BotModuleError("cannot load duplicate module '" + bot_module.name + "'")
			# TODO: don't add module ANYWHERE until all triggers are verified
			for t in bot_module.triggers:
				if t.trigger_type == 'INVOCATION':
					self._add_new_invocation_handler(bot_module, t)
				elif t.trigger_type == 'MENTION':
					self._add_new_mention_handler(bot_module, t)
				elif t.trigger_type == 'REGEX':
					self._add_new_regex_handler(bot_module, t)
			if bot_module.has_state and bot_module.name in state_dict:
				bot_module.set_state(state_dict[bot_module.name])
			self._bot_modules[bot_module.name] = bot_module
			names.append(bot_module.name)

	def _add_new_invocation_handler(self, bot_module, trig):
		"""
		Checks an invocation handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as an invocation handler.
		:type trig: commands.InvocationTrigger
		:param trig: The trigger that specifies the invocation to be handled.
		"""
		if trig.invocation in self._invocations:
			err_msg = "Duplicate invocation '" + trig.invocation + "' in module '" + bot_module.name + "';"
			err_msg += " already defined in '" + self._invocations[trig.invocation][-1].name + "' module"
			_log.warning(err_msg)
		else:
			self._invocations[trig.invocation] = []
		self._invocations[trig.invocation].append(bot_module)

	def _add_new_mention_handler(self, bot_module, trig):
		"""
		Checks a mention handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as a mention handler.
		:type trig: commands.MentionTrigger
		:param trig: The trigger that specifies the mention type to be handled.
		"""
		mts = trig.mention_targets
		if mts['target_type'] == 'any':
			self._any_mention_handlers.append(bot_module)
		elif mts['target_type'] == 'self':
			self._self_mention_handlers.append(bot_module)
		elif mts['target_type'] == 'specific':
			for name in mts['names']:
				if name in self._mention_handlers:
					err_msg = "Duplicate mention handler '" + name + "' in module '" + bot_module.name
					err_msg += "'; already defined in '" + self._mention_handlers[name][-1].name + "'"
					err_msg += " module"
					_log.warning(err_msg)
				else:
					self._mention_handlers[name] = []
				self._mention_handlers[name].append(bot_module)

	def _add_new_regex_handler(self, bot_module, trig):
		"""
		Checks a regex handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module to be used as a regex handler.
		:type trig: commands.RegexTrigger
		:param trig: The trigger that specifies the regex to look for.
		"""
		reg = trig.regex
		regex = re.compile(reg, re.DOTALL)
		self._regex_handlers[regex] = bot_module

	def _handle_invocation(self, message):
		tokens = shlex.split(message.content[len(self._prefix):])
		cmd = tokens[0]
		args = tokens[1:]

		if cmd == 'help':
			context = BotContext(message)
			help_cmd = None
			if len(args) > 0:
				help_cmd = args[0]
			asyncio.ensure_future(self.show_help(context, help_cmd))
		if cmd == 'quit':
			context = BotContext(message)
			asyncio.ensure_future(self.quit(context))
		if cmd == 'op':
			context = BotContext(message)
			if len(args) < 1:
				asyncio.ensure_future(self.show_syntax_error(context, "I need to know who you want to turn into an op."))
			asyncio.ensure_future(self.make_op(context, args[0]))
		elif cmd in self._invocations:
			context = BotContext(message)
			for handler in self._invocations[cmd]:
				self._execute_action(context, handler, lambda h: h.on_invocation(context, cmd, *args))

	def _handle_mention(self, message):
		handled_already = []
		mentions = message.raw_mentions
		context = BotContext(message)

		if len(self._any_mention_handlers) > 0:
			for h in self._any_mention_handlers:
				if h.name not in handled_already:
					self._execute_action(context, h, lambda h: h.on_mention(context, message.content, mentions))
					handled_already.append(h.name)

		if '<@' + self.client.user.id + '>' in mentions or '<@!' + self.client.user.id + '>' in mentions:
			for h in self._self_mention_handlers:
				if h.name not in handled_already:
					self._execute_action(context, h, lambda h: h.on_mention(context, message.content, mentions))
					handled_already.append(h.name)

		for m in mentions:
			if m in self._mention_handlers:
				for h in self._mention_handlers[m]:
					if h.name not in handled_already:
						self._execute_action(context, h, lambda h: h.on_mention(context, message.content, mentions))
						handled_already.append(h.name)

	def _handle_regex_scan(self, message):
		context = BotContext(message)
		for regex in self._regex_handlers:
			h = self._regex_handlers[regex]

			m = regex.search(message.content)
			if m is not None:
				match_groups = []
				for i in range(regex.groups+1):
					match_groups.append(m.group(i))
				self._execute_action(context, h, lambda h: h.on_regex_match(context, *match_groups))

	def _execute_action(self, context, mod, action):
		if mod.requires_op and context.author.id not in self._operators:
			msg = "Unprivileged user " + context.author.id + " attempted a privileged action in '" + mod.name + "'"
			_log.warning(msg)
			msg = "Sorry, <@!" + context.author.id + ">, but only my masters and operators can do that."
			asyncio.ensure_future(self.reply(context, msg))
			return
		asyncio.ensure_future(action(mod))
		if mod.has_state:
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
