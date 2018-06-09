import importlib
import logging
import discord
import asyncio
import re
import shlex
from . import configfile, commands


_log = logging.getLogger(__name__)


class BotContext(object):

	def __init__(self, message):
		self.source = message.channel
		self.author = message.author
		self.is_pm = self.source.is_private and len(self.source.recipients) == 1


class BotApi(object):

	def __init__(self, config_file):
		"""
		Initialize the bot API.
		:type config_file: str
		:param config_file: The path to the configuration file for the bot.
		"""
		self._bot_modules = []
		self._invocations = {}
		self._mention_handlers = {}
		self._self_mention_handlers = []
		self._any_mention_handlers = []
		self._regex_handlers = {}

		conf = configfile.load_config(config_file)
		self._prefix = conf['prefix']

		self.client = discord.Client()

		@self.client.event
		async def on_ready():
			_log.info("Logged in as " + self.client.user.name)
			_log.info(self.client.user.id)

		@self.client.event
		async def on_message(message):
			if message.content.startswith(self._prefix):
				self._handle_invocation(message)
			elif len(message.raw_mentions) > 0:
				self._handle_mention(message)
			else:
				self._handle_regex_scan(message)

		names = []
		_log.debug("loading modules")
		for module_str in commands.__all__:
			mod = importlib.import_module("commands." + module_str)
			bot_module = mod.Module().BOT_MODULE_CLASS(self)
			if bot_module.names in names:
				raise commands.BotModuleError("cannot load duplicate module '" + bot_module.name + "'")
			# TODO: don't add module ANYWHERE until all triggers are verified
			for t in bot_module.triggers:
				if t.trigger_type == 'INVOCATION':
					if t.invocation in self._invocations:
						err_msg = "Duplicate invocation '" + t.invocation + "' in module '" + bot_module.name + "';"
						err_msg += " already defined in '" + self._invocations[t.invocation][-1].name + "' module"
						_log.warning(err_msg)
					else:
						self._invocations[t.invocation] = []
					self._invocations[t.invocation].append(bot_module)
				elif t.trigger_type == 'MENTION':
					mts = t.mention_targets
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
				elif t.trigger_type == 'REGEX':
					reg = t.regex
					regex = re.compile(reg, re.DOTALL)
					self._regex_handlers[regex] = bot_module
			self._bot_modules.append(bot_module)
			names.append(bot_module.name)

		self._api_key = conf['discord-api-key']

	def run(self):
		self.client.run(self._api_key)

	def reply(self, context, message):
		if context.is_pm:
			self.client.send_message(context.author, message)
		else:
			self.client.send_message(context.source, message)

	def show_help(self, context):
		pre = self._prefix
		msg = "Sure! I'll tell you how to use my interface!\n\n"
		msg += "Here are my special commands:\n"
		msg += "`" + pre + "help` - Shows this help. You can give me a module after 'help' and I'll tell you how to use"
		msg += "it!\n\n"
		msg += "Here are the modules that I'm running:\n"
		for m in self._bot_modules:
			invokes = ','.join('`' + pre + t.invocation + '`' for t in m.triggers if t.trigger_type == "INVOCATION")
			invokes = ' (' + invokes + ')' if invokes is not '' else ''
			msg += '`' + m.name + "`" + invokes + " - " + m.description + "\n"
		self.client.send_message(context.source, msg)

	def _handle_invocation(self, message):
		tokens = shlex.split(message.content[len(self._prefix):])
		cmd = tokens[0]
		args = tokens[1:]

		if cmd == 'help':
			context = BotContext(message)
			self.show_help(context)
		elif cmd in self._invocations:
			context = BotContext(message)
			for handler in self._invocations[cmd]:
				handler.on_invocation(context, cmd, *args)

	def _handle_mention(self, message):
		handled_already = []
		mentions = message.raw_mentions
		context = BotContext(message)

		if len(self._any_mention_handlers) > 0:
			for h in self._any_mention_handlers:
				if h.name not in handled_already:
					h.on_mention(context, message.content, mentions)
					handled_already.append(h.name)

		if '<@' + self.client.user.id + '>' in mentions or '<@!' + self.client.user.id + '>' in mentions:
			for h in self._self_mention_handlers:
				if h.name not in handled_already:
					h.on_mention(context, message.content, mentions)
					handled_already.append(h.name)

		for m in mentions:
			if m in self._mention_handlers:
				for h in self._mention_handlers[m]:
					if h.name not in handled_already:
						h.on_mention(context, message.content, mentions)
						handled_already.append(h.name)

	def _handle_regex_scan(self, message):
		context = BotContext(message)
		for regex, h in self._regex_handlers:
			m = regex.search(message.content)
			if m is not None:
				match_groups = []
				for i in range(regex.groups):
					match_groups.append(m.group(i))
				h.on_regex_match(context, *match_groups)


def start():
	bot = BotApi("config.json")
	bot.run()
