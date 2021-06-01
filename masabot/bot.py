import importlib
import logging
import pickle
# noinspection PyPackageRequirements
import discord
import traceback
import os
import asyncio
import sys
import time
import random
import re
import shlex

from . import configfile, commands, util, version, settings, timer
from typing import Optional, Dict, Any, List, Sequence

from .messagecache import MessageHistoryCache
from .util import BotSyntaxError, BotModuleError, BotPermissionError, MessageMetadata, DiscordPager
from .context import BotContext
from .pluginapi import PluginAPI


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


random_status_list = [
			"with her internal systems",
			"looking at the world!",
			"with the new Discord API",
			"Turing test practice",
			"with YouTube",
			"Epic Bot Adventure!",
			"Botting About",
			"My blood type is B!",
			"World domination planning",
			"Looking for more glitter",
			"being cute ^_^",
			"VNs with sketchy covers",
			"at pranxis",
			"with clown friends",
			"outside",
			"in the road",
			"THREAT SCAN",
			"lunch! ^_^",
			"anime",
			"Sword Art Online",
			"DDR",
			"Bugsnax",
			"GameCube",
			"ACNH",
			"yuru camp",
			"Friday Night Funkin'",
			"the stalk market",
			"Halo",
			"the stock market 📈",
			"with Springtop",
			"with clowny data",
			"with Percy the 🐴",
			"eat the rich",
			"doge. wow.",
			"secretary of jape",
			"with Mizzlebip",
			"reading",
			"schedule-making",
			"culling asdf3w",
			"<ALL IS WELL>",
			"Twitter",
			"Metal Gear",
			"Metal GEAR",
			"METAL GEAR!!!!",
			"omg it's metal gear O.O",
			"Psycholonials",
			"Namco High",
			"Hiveswap",
			"Hades",
			"Homestuck Collection",
			"<SEARCHING>",
			"with SHODAN",
			"with HELIOS",
			"with DAEDALUS",
			"with ICARUS",
			"System Shock 3: IRL Edition"
		]


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

class _TimerInfo:
	def __init__(self, t: timer.Timer, repeat: bool = False, is_module_trigger: bool = True):
		self.timer = t
		self.repeat = repeat
		self.is_mod_trigger = is_module_trigger


class MasaBot(object):

	def __init__(self, config_file, logdir, state_file):
		"""
		Initialize the bot API.
		:type config_file: str
		:param config_file: The path to the configuration file for the bot.
		:type logdir: str
		:param logdir: The path to a directory to store bot-defined logs in. Not currently used.
		"""
		_log.debug("Initializing MasaBot")
		self._state_file = state_file
		self._bot_modules = {}
		""":type : dict[str, commands.BotBehaviorModule]"""
		self._invocations: Dict[str, Sequence[commands.BotBehaviorModule]] = {}
		self._mention_handlers = {'users': {}, 'channels': {}, 'roles': {}}
		self._self_mention_handlers = []
		self._any_mention_handlers = []
		self._reaction_add_handlers = {'unicode': {}, 'custom': {}, 'any': []}
		self._reaction_remove_handlers = {'unicode': {}, 'custom': {}, 'any': []}
		self._reaction_subscriptions = {}
		self._regex_handlers = {}
		self._operators: Dict[int, Dict[str, Any]] = {}
		self.module_settings: Dict[str, settings.SettingsStore] = {}
		self._module_settings_context_limitations: Dict[str, Dict[str, str]] = {}
		self.core_settings = settings.SettingsStore()
		self.core_settings.register_key(
			settings.Key(settings.key_type_percent, 'mimic-reaction-chance', default=0.05)
		)
		self.core_settings.register_key(
			settings.Key(settings.key_type_percent, 'presence-chance', default=0.001)
		)
		self.core_settings.register_key(
			settings.Key(settings.key_type_int, 'history-limit', default=1000)
		)
		self.core_settings.register_key(
			settings.Key(settings.key_type_toggle, 'announce-startup', default=False)
		)
		self._return_code = 0
		self._timers = {}
		""":type : dict[str, dict[str, timerInfo]]"""
		"""above is module name (None is core) -> timer name -> timerInfo"""
		self._setup_complete = False
		self._main_timer_task = None

		# default replacements; will be overridden if present in state file
		self._invocation_replacements = {
			'“': '"',
			'”': '"'
		}

		_log.info("Loading config file...")
		conf = configfile.load_config(config_file)
		if 'masters' in conf:
			conf['superops'] = conf['masters']  # convert configs with outdated terminology. remove after all configs updated
		for m in conf['superops']:
			self._operators[m] = {'role': 'superop'}
		self._api_key = conf['discord-api-key']
		"""[Server_id, Dict[Channel_id, List[message]]]"""

		self.prefix = conf['prefix']
		# TODO: could announce_channels be removed from the bot and put into the API instead?
		self.announce_channels = conf['announce-channels']

		# ensure we load modules prior to state setting so we can get the keys each module expects and build up its
		# state dict
		self._load_modules()

		# initialize module settings stores here. Core settings are already initialized in this init function.
		self._initialize_module_settings()

		state_dict = {}
		# noinspection PyBroadException
		try:
			with open(self._state_file, 'rb') as fp:
				state_dict = pickle.load(fp)
		except FileNotFoundError:
			_log.warning("No state file found; default settings will be used")
		except Exception:
			_log.exception("Could not read state file; skipping")
		else:
			_log.info("Loading state file...")
			# noinspection PyBroadException
			try:
				self._load_builtin_state(state_dict)
			except Exception:
				_log.exception("Could not load state file contents; skipping")

		def get_limit():
			return self.core_settings.get_global('history-limit')
		self._message_history_cache = MessageHistoryCache(get_limit)

		intents = discord.Intents.default()
		intents.dm_typing = False
		intents.typing = False
		intents.bans = False
		intents.voice_states = False
		intents.members = True
		self.client = discord.Client(status="being cute with discord.py 1.x", intents=intents)
		self._sent_announcement = False

		@self.client.event
		async def on_ready():
			_log.info("Logged in as " + self.client.user.name)
			_log.info("ID: " + str(self.client.user.id))

			if self.client.user.avatar_url == '':
				_log.info("Avatar not yet set; uploading...")
				with open('avatar.png', 'rb') as avatar_fp:
					avatar_data = avatar_fp.read()
				await self.client.user.edit(avatar=avatar_data)

			await self.randomize_presence()

			_log.info("Connected to servers:")
			for g in self.client.guilds:
				_log.info("* " + str(g))

			_log.info("Bot is now online")

			# announce only in the channels where they've turned on that function
			for g in self.connected_guilds:
				if self.core_settings.get(g.id, 'announce-startup'):
					for ch in g.channels:
						if ch.type == discord.ChannelType.text and ('#' + ch.name) in self.announce_channels:
							msg = "Hello! I'm now online ^_^"
							try:
								await ch.send(msg)
							except discord.Forbidden:
								pass
							_log.debug(util.add_context(ch, "sent: {!r} as startup message", msg))
			self._sent_announcement = True

			await self._check_last_command()
			self._setup_complete = True

		@self.client.event
		async def on_message(message):
			self._message_history_cache.save(message)
			if message.author.id == self.client.user.id:
				return  # don't answer own messages
			if message.content.startswith(self.prefix):
				if message.content.strip() == self.prefix:
					return  # don't reply to messages that are JUST the prefix
				await self._handle_invocation(message)
			else:
				if len(message.raw_mentions) > 0:
					await self._handle_mention(message)

				await self._handle_regex_scan(message)

		@self.client.event
		async def on_guild_join(guild: discord.Guild):
			_log.info("joined guild {:s} (ID {:d})".format(guild.name, guild.id))
			self._save_all()
			await self.randomize_presence(self.core_settings.get_global('presence-chance'))

		@self.client.event
		async def on_guild_remove(guild: discord.Guild):
			_log.info("left guild {:s} (ID {:d})".format(guild.name, guild.id))
			self._save_all()
			await self.randomize_presence(self.core_settings.get_global('presence-chance'))

		# noinspection PyUnusedLocal
		@self.client.event
		async def on_raw_reaction_add(evt: discord.RawReactionActionEvent):
			rct = util.Reaction.from_raw(evt)
			await rct.fetch(self.client)
			ctx = BotContext(rct.source_message)
			# TODO: make reaction triggers work in DMs
			if ctx.is_pm:
				return

			meta = util.MessageMetadata.from_message(rct.source_message)

			emoji = ''
			if rct.is_custom:
				emoji = repr(rct.custom_name) + " (custom)"
			else:
				emoji = repr(rct.emoji)

			# first, check if it is a subscribed message. no other actions will occur if so
			if rct.message_id in self._reaction_subscriptions:
				log_msg = util.add_context(
					ctx,
					"Received reaction addition of " + emoji + " on subscribe-mode MID " + repr(rct.message_id)
				)
				_log.debug(log_msg)
				for mod in self._reaction_subscriptions[rct.message_id]:
					handler = self._bot_modules[mod]
					api = PluginAPI(self, mod, ctx, self._message_history_cache)
					await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

				# NO MORE HANDLING; immediately return
				log_msg = util.add_context(
					ctx,
					"Message is in subscribe mode, so not passing event to other reaction listeners"
				)
				_log.debug(log_msg)
				return

			# only log it if we care
			# TODO: race condition between awaits and the time we actually check for reaction handlers
			# shouldn't be an issue unless we wish to load/unload modules at runtime
			if (
					len(self._reaction_add_handlers['any']) > 0 or
					(rct.is_custom and rct.custom_name in self._reaction_add_handlers['custom']) or
					(not rct.is_custom and rct.emoji in self._reaction_add_handlers['unicode'])
			):
				log_msg = util.add_context(ctx, "received reaction " + emoji + " on MID " + repr(rct.message_id))
				_log.debug(log_msg)

			if rct.is_custom:
				if rct.custom_guild == ctx.get_guild().id:
					if rct.custom_name in self._reaction_add_handlers['custom']:
						for handler in self._reaction_add_handlers['custom'][rct.custom_name]:
							api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
							# dont assign directly so handled stays true
							await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)
			else:
				if rct.emoji in self._reaction_add_handlers['unicode']:
					for handler in self._reaction_add_handlers['unicode'][rct.emoji]:
						api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
						await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

			for handler in self._reaction_add_handlers['any']:
				api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
				await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

			await self._mimic_reaction(ctx, rct)

		# noinspection PyUnusedLocal
		@self.client.event
		async def on_raw_reaction_remove(evt: discord.RawReactionActionEvent):
			rct = util.Reaction.from_raw(evt)
			await rct.fetch(self.client)
			ctx = BotContext(rct.source_message)
			# TODO: make reaction triggers work in DMs
			if ctx.is_pm:
				return

			meta = util.MessageMetadata.from_message(rct.source_message)

			emoji = ''
			if rct.is_custom:
				emoji = repr(rct.custom_name) + " (custom)"
			else:
				emoji = repr(rct.emoji)

			# first, check if it is a subscribed message. no other actions will occur if so
			if rct.message_id in self._reaction_subscriptions:
				log_msg = util.add_context(
					ctx,
					"Received reaction removal of " + emoji + " on subscribe-mode MID " + repr(rct.message_id)
				)
				_log.debug(log_msg)
				for mod in self._reaction_subscriptions[rct.message_id]:
					handler = self._bot_modules[mod]
					api = PluginAPI(self, mod, ctx, self._message_history_cache)
					await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

				# NO MORE HANDLING; immediately return
				log_msg = util.add_context(
					ctx,
					"Message is in subscribe mode, so not passing event to other reaction listeners"
				)
				_log.debug(log_msg)
				return

			# only log it if we care
			# TODO: race condition between awaits and the time we actually check for reaction handlers
			# shouldn't be an issue unless we wish to load/unload modules at runtime
			if (
					len(self._reaction_remove_handlers['any']) > 0 or
					(rct.is_custom and rct.custom_name in self._reaction_remove_handlers['custom']) or
					(not rct.is_custom and rct.emoji in self._reaction_remove_handlers['unicode'])
			):
				log_msg = util.add_context(ctx, "received reaction removal of " + emoji + " on MID " + repr(rct.message_id))
				_log.debug(log_msg)

			if rct.is_custom:
				if rct.custom_guild == ctx.get_guild().id:
					if rct.custom_name in self._reaction_remove_handlers['custom']:
						for handler in self._reaction_remove_handlers['custom'][rct.custom_name]:
							api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
							# dont assign directly so handled stays true
							await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)
			else:
				if rct.emoji in self._reaction_remove_handlers['unicode']:
					for handler in self._reaction_remove_handlers['unicode'][rct.emoji]:
						api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
						await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

			for handler in self._reaction_remove_handlers['any']:
				api = PluginAPI(self, handler.name, ctx, self._message_history_cache)
				await self._execute_action(api, handler.on_reaction(api, meta, rct), handler)

		# noinspection PyUnusedLocal
		@self.client.event
		async def on_error(event, *args, **kwargs):
			if len(args) < 1:
				# assume that we did not come from on_message
				_log.exception("Exception in startup")
				if not self._setup_complete:
					with open('ipc/lastcmd.p', 'wb') as restart_command_file:
						pickle.dump({'command': 'quit'}, restart_command_file)
					await self.client.close()
			else:
				if isinstance(args[0], discord.RawReactionActionEvent):
					message = None
				else:
					message = args[0]
				pager = DiscordPager("_(error continued)_")
				e = traceback.format_exc()
				logging.exception("Exception in main loop")

				# is it an access issue?
				if isinstance(e, discord.errors.Forbidden):
					msg = "**Permissions Error?** What is that? I don't know, but Discord told me that when I tried to"
					msg += " do something! Do I need special permissions on my role to do that?"
					if message is not None:
						await message.channel.send(msg)
					_log.debug(_fmt_send(message.channel, msg))
				else:
					msg_start = "I...I'm really sorry, but... um... I just had an exception :c"
					pager.add_line(msg_start)
					pager.add_line()
					pager.start_code_block()
					for line in e.splitlines():
						pager.add_line(line)
					pager.end_code_block()
					pages = pager.get_pages()
					if message is not None:
						for p in pages:
							await message.channel.send(p)
					_log.debug(_fmt_send(message.channel, msg_start + " (exc_details)"))

		_log.info("Loading module config and state...")
		self._configure_loaded_modules(conf['modules'])

		# noinspection PyBroadException
		try:
			if '__BOT__' in state_dict:
				self._set_settings_in_loaded_modules(state_dict['__BOT__']['settings']['modules'])
		except Exception:
			_log.exception("could not set module settings from state file; defaults will be used")

		# noinspection PyBroadException
		try:
			self._set_state_in_loaded_modules(state_dict)
		except Exception:
			_log.exception("could not set module state from state file; defaults will be used")

		_log.info("Modules are now ready")

	async def _mimic_reaction(self, ctx: BotContext, rct: util.Reaction):
		# don't mimic own reactions
		if self.client.user.id in rct.reactors:
			return
		if random.random() < self.core_settings.get(ctx.source.guild.id, 'mimic-reaction-chance'):
			# give a slight delay
			delay = 1 + (random.random() * 3)  # random amount from 1 to 4 seconds
			await asyncio.sleep(delay)
			await rct.source_message.add_reaction(rct.emoji_value)

	async def randomize_presence(self, chance=1.0):
		if random.random() < chance:
			await self.client.change_presence(activity=discord.Game(name=random.choice(random_status_list)))

	def run(self):
		"""
		Begin execution of bot. Blocks until complete.
		"""
		_log.info("Connecting...")
		# WARNING! WE REMOVED client.close() HERE.
		self._main_timer_task = self.client.loop.create_task(self._run_timer())
		self.client.run(self._api_key)
		return self._return_code

	@property
	def connected_guilds(self) -> Sequence[discord.Guild]:
		guilds: List[discord.Guild] = []
		for g in self.client.guilds:
			guild: discord.Guild = g
			guilds.append(guild)
		return guilds

	async def show_help(self, api: 'PluginAPI', help_module=None):
		"""
		Display the help command in the current context.

		:param api: Context-sensitive methods for reacting to the message.
		:type help_module: str
		:param help_module: The module to get additional info on. Can be a module or a command.
		"""
		pre = self.prefix
		if help_module is None:
			msg = "Sure! I'll tell you how to use my interface!\n\n"
			msg += "Here are my special commands:\n"
			msg += "* `" + pre + "help` - Shows this help.\n"
			msg += "* `" + pre + "version` - Shows the current version.\n"
			msg += "* `" + pre + "restart` - Restarts masabot with an optional message.\n"
			msg += "* `" + pre + "quit` - Immediately stops me from running.\n"
			msg += "* `" + pre + "op` - Gives a user operator permissions.\n"
			msg += "* `" + pre + "deop` - Takes away operator permissions from a user.\n"
			msg += "* `" + pre + "showops` - Shows all of my operators and superops.\n"
			msg += "* `" + pre + "replchars` - Shows/sets characters that are replaced before parsing.\n"
			msg += "* `" + pre + "settings` - Shows and sets core module settings.\n"
			msg += "* `" + pre + "msgsubs` - Shows and sets the current emoji message subscription IDs.\n"
			msg += "\nHere are the modules that I'm running:\n"
			for m_name in self._bot_modules:
				m = self._bot_modules[m_name]
				invokes = ','.join('`' + pre + t.invocation + '`' for t in m.triggers if t.trigger_type == "INVOCATION")
				invokes = ' (' + invokes + ')' if invokes != '' else ''
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
			elif help_module == "settings":
				msg = "Ara! That's the command that controls the settings of various features in my system! There"
				msg += " are four different ways to use this command:\n\n"
				msg += " * `" + pre + "settings` by itself will list all of the modules that I have settings for so you"
				msg += " can pick the module to look at.\n"
				msg += " * `" + pre + "settings <module>` will list all of the settings that are available in that"
				msg += " module.\n"
				msg += " * `" + pre + "settings <module> <key>` will show what that setting in particular is set to "
				msg += " right now.\n"
				msg += " * Finally, `" + pre + "settings <module> <key> <new_value>` will set that setting to a new"
				msg += " value! But you do gotta be an operator (or even a superop for some settings!) to do that one,"
				msg += " because otherwise someone could"
				msg += " accidentally set it to values that don't work very well, which is really scary!"
			elif help_module == "version":
				msg = "Oh, that's the command that tells you what version I am!"
			elif help_module == "quit":
				msg = "Mmm, `quit` is the command that will make me leave the server right away. It shuts me down"
				msg += " instantly, which is really really sad! It's a really powerful command, so only my superops"
				msg += " are allowed to use it, okay?"
			elif help_module == "op":
				msg = "The `op` command turns any user into an operator. But, oh, of course, you have to already be an"
				msg += " op in order to run it! Otherwise anybody could control me!"
			elif help_module == "deop":
				msg = "The `deop` command takes away operator powers from any of my existing operators. B-but I won't"
				msg += " do that to any of my superops, so you can only do it to normal operators! Also, you have to"
				msg += " already be an operator in order to run this, just so you know!"
			elif help_module == "showops":
				msg = "Ah, that's the `showops` command! When you type this in, I'll tell you who my operators and"
				msg += " superops are, and also a little bit of info on each of them."
			elif help_module == "restart":
				msg = "The `restart` command is a really special command that will cause me to shut down and start back"
				msg += " up again! If it's done with a message, I'll say that message on startup in my announcement"
				msg += " channels, and if you give \"announcedown\" after that message, I'll announce that I'm going"
				msg += " down! The message only works if I am dockerized in my special masabot image; otherwise the"
				msg += " command will just make me shutdown, so please be careful! Oh, and remember that only my"
				msg += " superops can do this!"
			elif help_module == "replchars":
				msg = "The `replchars` command shows all of the replacements that I do on text before trying to parse"
				msg += " it into a command that I understand! Oh! And also, my superops can use this"
				msg += " command with an extra sub-command after it (`add` or `remove`) to change what replacements are"
				msg += " active:\n\n`replchars` by itself will list out all the replacements.\n`replchars add"
				msg += " <search> <replacement>` adds a new one.\n`replchars remove <search>` will remove an existing"
				msg += " one.\n\nNote that replacements apply to the actual command only, and not to the prefix!\n\n"
				msg += "**In order to make sure replacements don't mess up my system, replacements are never applied"
				msg += " to any invocations of the `replchars` command.** Additionally, the backslash character, the"
				msg += " non-curly double quote, and the non-curly single quote are never allowed to be replaced; also,"
				msg += " the space character can only be replaced in conjuction with other characters, and never by"
				msg += " itself. **Even if you're a superop user or an operator.** I'm really sorry to restrict it like"
				msg += " that, but I have to in order to make sure I can keep running properly!"
			elif help_module == "msgsubs":
				msg = "The `msgsubs` command is shows all message emoji subscriptions that exist! It's an experimental"
				msg += " feature that may need operator intervention, so I have this command.\n\n`msgsubs` by itself"
				msg += " will show a list of all message subscriptions in the current server.\n\n`msgsubs remove <id>`"
				msg += " will delete the subscription. This could break modules, so be careful!\n\nAll of these"
				msg += " combinations could make me break really fast, so only superops can execute them."
			else:
				if help_module not in self._invocations and help_module not in self._bot_modules:
					msg = "Oh no! I'm sorry, " + api.mention_user() + ", but I don't have any module or command"
					msg += " called '" + help_module + "'. P-please don't be mad! I'll really do my best at everything"
					msg += " else, okay?"
				else:
					m = self._bot_modules.get(help_module, None)
					if m is None:
						m = self._invocations[help_module][0]
					msg = "Oh yeah, the `" + m.name + "` module! `" + m.description + "`\n\n" + m.help_text
		pager = util.DiscordPager()
		for x in msg.split('\n'):
			pager.add_line(x)
		for p in pager.get_pages():
			await api.reply(p)

	async def quit(self, api: 'PluginAPI', restart_command="quit", data=None):
		api.require_superop("quit", None)
		with open('ipc/lastcmd.p', 'wb') as fp:
			pickle.dump({'command': restart_command, 'data': data}, fp)
		await api.reply("Right away, " + api.mention_user() + "! See you later!")
		_log.info("Shutting down...")
		# TODO: might need to do shutdown of each individual task if it is mid-run
		self._main_timer_task.cancel()
		await self.client.logout()

	# noinspection PyMethodMayBeStatic
	async def show_version(self, api: 'PluginAPI'):
		await api.reply("I am Masabot v" + str(version.get_version()) + "!")

	async def _run_msgsubs_command(self, api: 'PluginAPI', args):
		if len(args) == 0:
			api.require_superop('msgsubs', None)
			if len(self._reaction_subscriptions) == 0:
				await api.reply("There are currently no emoji reaction subscriptions!")
				return
			pages = DiscordPager()
			msg = "Sure! Here's the messages where reaction event subscription is turned on for, and the modules"
			msg += " that requested it!"
			pages.add_line(msg)
			pages.start_code_block()
			for s in self._reaction_subscriptions:
				msg = "* MID " + str(s) + " by " + ', '.join(list(self._reaction_subscriptions[s].keys()))
				msg += '\n'
				pages.add_line(msg)
			pages.end_code_block()
			for p in pages.get_pages():
				await api.reply(p)
		else:
			mode = args[0].lower()
			if mode == 'remove':
				api.require_superop('msgsubs remove <id>', None)
				if len(args) < 2:
					err_msg = "I can do that, but I need you to tell me the ID of the message"
					err_msg += " to remove reaction subscriptions from!"
					raise BotSyntaxError(err_msg)
				try:
					mid = int(args[1])
				except TypeError:
					raise BotSyntaxError("The message ID needs to be an integer.")
				if mid not in self._reaction_subscriptions:
					raise BotSyntaxError("That message ID does not have any subscriptions on it.")
				del self._reaction_subscriptions[mid]
				_log.debug(util.add_context(api.context, "Wiped all msgsubs on MID {:d} by superop request", mid))
				self._save_all()
				await api.reply("Done! All subscriptions have been wiped.")
			else:
				raise BotSyntaxError("That isn't a subcommand of msgsubs!")

	async def _run_settings_command(
			self,
			api: 'PluginAPI',
			args):
		"""
		Execute the settings command. Depending on the action, this will either be to list all existing keys, to get
		the value of a particular key, or to set the value of the key. Setting the value requires op permissions.

		:param api: Methods for performing things in discord.
		:param args: The arguments.
		"""
		if len(args) == 0:
			modules_list = ["core"]
			modules_list += list(self._bot_modules.keys())

			if len(modules_list) < 2:
				module_name = None
			else:
				msg = "What module do you want to see the settings for?"
				opt = await api.prompt_for_option(msg, modules_list[0], modules_list[1], *modules_list[2:])
				if opt is None:
					raise BotSyntaxError("I have a lot of settings so I need to know which module you want to look at")
				if opt == "core":
					module_name = None
				else:
					module_name = opt
		else:
			module_name = args[0]
			if module_name.lower() == "core":
				module_name = None

			# modify args to pull out the module name so we dont have to worry about detecting the name
			args = args[1:]

		if module_name is None:
			module_name_str = "core"
			store = self.core_settings
		else:
			module_name_str = "`" + module_name + "`"
			if module_name not in self.module_settings:
				raise BotSyntaxError(module_name_str + " is not `core` or a module that I have loaded!")
			store = self.module_settings[module_name]

		pager = DiscordPager("_(settings continued)_")
		if len(args) == 0:
			# we are doing a list, no need for privileges
			pager.add_line("Okay, you got it! Here's a list of settings in my " + module_name_str + " module:")
			pager.add_line()
			if len(store) < 1:
				pager.add_line("...oh no. This doesn't seem right at all! I can't seem to see any settings at all!")
			else:
				for k in store:
					pager.add_line("`" + str(k) + "`, with type `" + store.get_key(k).type.name + "`")
		elif len(args) == 1:
			key = args[0]
			context_restriction = self.get_setting_restrictions(module_name, key)
			if key not in store:
				msg = "Let me take a look... Uh-oh! `" + key + "` isn't a setting I have on file! Um, really quick,"
				msg += " just in case you forgot, you can check which settings I have by using this command by itself,"
				msg += " if you need to."
			else:
				if context_restriction is None:
					if api.context.is_pm:
						server_id = None
					else:
						server_id = api.context.source.guild.id
				elif context_restriction == 'global':
					server_id = None
				elif context_restriction == 'server':
					server_id = await api.require_server()
				else:
					raise BotSyntaxError("bad context restriction: " + repr(context_restriction))

				if server_id is None:
					val = store.get_global(key)
				else:
					val = store.get(server_id, key)
				msg = "Let me take a look... Okay, it looks like `" + key + "` is currently set to " + repr(val) + "."
			pager.add_line(msg)
		elif len(args) >= 2:
			key = args[0]
			context_restriction = self.get_setting_restrictions(module_name, key)
			new_value = args[1]
			if module_name is None:
				module_name = "(core module)"

			if key not in store:
				msg = "Uh-oh! `" + key + "` isn't a setting I have on file! Um, really quick,"
				msg += " just in case you forgot, you can check which settings I have by using this command by itself,"
				msg += " if you need to."
			else:
				store_key = store.get_key(key)
				if context_restriction is None:
					if api.context.is_pm:
						server_id = None
					else:
						server_id = api.context.source.guild.id
				elif context_restriction == 'global':
					server_id = None
				elif context_restriction == 'server':
					server_id = await api.require_server()
				else:
					raise BotSyntaxError("bad context restriction: " + repr(context_restriction))

				if server_id is None:
					api.require_superop(module_name + " settings set " + repr(key), None)
					if store_key.prompt_before:
						if not await api.confirm(store_key.prompt_before):
							await api.reply("Okay! I'll leave that setting alone, then.")
							return
					try:
						old_value = store.get_global(key)
						store.set_global(key, new_value)
						updated_value = store.get_global(key)
					except ValueError as e:
						raise BotSyntaxError(str(e))
				else:
					await api.require_op(module_name + " settings set " + repr(key))
					if store_key.prompt_before:
						if not await api.confirm(store_key.prompt_before):
							await api.reply("Okay! I'll leave that setting alone, then.")
							return
					try:
						old_value = store.get(server_id, key)
						store.set(server_id, key, new_value)
						updated_value = store.get(server_id, key)
					except ValueError as e:
						raise BotSyntaxError(str(e))
				log_message = "User " + str(api.get_user().id) + "/" + str(api.get_user().name) + " updated setting "
				if module_name is None:
					log_message += "<CORE>:"
				else:
					log_message += module_name + ":"
				log_message += repr(key) + " from " + repr(old_value) + " to new value " + repr(updated_value)
				_log.debug(log_message)
				# TODO: BAD. genericize this! this is working around not having mutation hooks
				self._save_all()
				await api.reply("Certainly! `" + key + "` has been updated to " + repr(updated_value) + "!")
				if store_key.call_module_on_alter:
					if module_name is None:
						raise ValueError("core module cannot hook into setting mutations")
					bot_module = self._bot_modules[module_name]
					# noinspection PyBroadException
					try:
						await bot_module.on_setting_change(api, key, old_value, updated_value)
					except Exception:
						_log.debug("got exception while running on_settings hook; reverting change")
						if server_id is None:
							store.set_global(key, old_value)
						else:
							store.set(server_id, key, old_value)
						raise
				return
			pager.add_line(msg)

		for page in pager.get_pages():
			await api.reply(page)

	async def _run_replchars_command(self, api: 'PluginAPI', action=None, search=None, replacement=None):
		"""
		Execute the replchars command. Depending on the action, this will either print out the info on current
		replacements, add a new replacement, or remove an existing replacement. Adding and removing require operator
		privileges.

		:param api: Context-sensitive API commands.
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

			await api.reply(msg)
		elif action == "add":
			api.require_superop("replchars add", None)
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
					await api.reply("Well, I'm already replacing `" + search + "` with `" + cur_repl + "`.")
					return
				prompt_msg = "Right now, I'm replacing `" + search + "` with `" + cur_repl + "`. Do you want me to"
				prompt_msg += " start replacing it with `" + replacement + "` instead?"
			else:
				prompt_msg = "Just to make sure, you want me to start replacing `" + search + "` with `" + replacement
				prompt_msg += "`, right?"

			reply = await api.prompt_for_option(prompt_msg)
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

			await api.reply(msg)

		elif action == "remove":
			api.require_superop("replchars remove", None)
			if search is None:
				msg = "I need to know the string you want me to stop replacing."
				raise BotSyntaxError(msg)

			if search not in self._invocation_replacements:
				msg = "Oh, okay. Actually, I was already not doing any replacements for `" + search + "`, so that works"
				msg += " out pretty well! Yay!"
				await api.reply(msg)
				return

			cur_repl = self._invocation_replacements[search]
			prompt_msg = "Okay, right now I'm replacing `" + search + "` with `" + cur_repl + "` in commands, and you"
			prompt_msg += " want me to stop doing that, right?"
			reply = await api.prompt_for_option(prompt_msg)

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
			await api.reply(msg)
		else:
			raise BotSyntaxError("The thing is, `" + str(action) + "` is just not a valid subcommand for `replchars`!")

	async def show_syntax_error(self, api: 'PluginAPI', message=None):
		"""
		Show the standard syntax error message in the current message context.

		:param api: The current message context.
		:type message: str
		:param message: The message to include with the syntax error. Make it extremely brief; this function
		automatically handles setting up a sentence and apologizing to the user.
		:return:
		"""
		msg = "Um, oh no, I'm sorry " + api.mention_user() + ", but I really have no idea what you mean..."
		if message is not None:
			msg += " " + message
		msg += "\n\nBut, oh! I know!"
		msg += " If you're having trouble, maybe the command `" + self.prefix + "help` can help you!"
		await api.reply(msg)

	async def show_ops(self, api: 'PluginAPI'):
		server_id = await api.require_server()
		msg = "Okay, sure! Here's a list of all of my operators:\n\n"
		with api.typing():
			matching_ops = []

			for u in self._operators:
				op_profile = self._operators[u]
				if op_profile['role'] == 'superop':
					matching_ops.append(u)
				elif op_profile['role'] == 'operator':
					if server_id in op_profile['servers']:
						matching_ops.append(u)

			for u in matching_ops:
				all_info = self.client.get_user(u)
				if all_info is None:
					all_info = await self.client.fetch_user(u)
				op_info = self._operators[u]
				op_name = '(UID ' + str(u) + ')'
				if all_info is not None:
					op_name = "`" + all_info.name + "#" + all_info.discriminator + "`"
				msg += "* " + op_name + " _(" + op_info['role'] + ")_\n"
		await api.reply(msg)

	async def pm_superop_users(self, message):
		superops = [x for x in self._operators.keys() if self._operators[x]['role'] == 'superop']
		for so in superops:
			user = self.client.get_user(so)
			await user.send(message)

	async def _run_timer(self):
		await self.client.wait_until_ready()
		_log.debug("Main timer started")
		tick_span = 60  # seconds
		
		async def report_error(msg):
			long_message = "Problem running timer "
			long_message += repr(timer_name)
			long_message += " for "
			if mod_name is None:
				long_message += "core module"
			else:
				long_message += "module " + repr(mod_name)
			long_message += ":\n\n"
			await self.pm_superop_users(msg)
			
		while not self.client.is_closed:
			now_time = time.monotonic()

			to_clear = dict()
			for mod_name in self._timers:
				for timer_name in self._timers[mod_name]:
					tinfo = self._timers[mod_name][timer_name]
					fired = tinfo.timer.tick(now_time, report_error)

					# clean up any once-off timers
					if fired and not tinfo.repeat:
						if mod_name not in to_clear:
							to_clear[mod_name] = list()
						to_clear[mod_name].append(timer_name)
			
			# clear all timers that are no longer repeating
			for mod_name in to_clear:
				for timer_name in to_clear[mod_name]:
					if mod_name not in self._timers:
						msg = "while clearing timer {!r}/{!r}: "
						msg += "module {!r} does not exist in timer list"
						_log.warning(msg, mod_name, timer_name, mod_name)
					elif timer_name not in self._timers[mod_name]:
						msg = "while clearing timer {!r}/{!r}: "
						msg += "timer {!r} does not exist in timers for module {!r}"
						_log.warning(msg, mod_name, timer_name, timer_name, mod_name)
					else:
						# possible race condition if co-modified but nobody else
						# should be modifying this
						del self._timers[mod_name][timer_name]
						if len(self._timers[mod_name]) == 0:
							del self._timers[mod_name]

			await asyncio.sleep(tick_span)

	def get_setting_restrictions(self, module: Optional[str], key: str) -> Optional[str]:
		if module is None:
			return None
		if module not in self._module_settings_context_limitations:
			return None
		lim = self._module_settings_context_limitations[module]
		if key not in lim:
			return None
		return lim[key]

	def is_op(self, uid: int, in_server: int) -> bool:
		if uid not in self._operators:
			return False
		if self._operators[uid]['role'] == 'superop':
			return True
		if self._operators[uid]['role'] == 'operator':
			if in_server in self._operators[uid]['servers']:
				return True
		return False

	def is_superop(self, uid: int) -> bool:
		if uid not in self._operators:
			return False
		return self._operators[uid]['role'] == 'superop'

	async def _make_op(self, api: 'PluginAPI', args):
		server_id = await api.require_server()
		server = self.client.get_guild(server_id).name
		await api.require_op("op")

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want to turn into an op")

		mention = util.parse_mention(args[0])

		if not mention.is_user():
			msg = "Well, the thing is, " + str(mention) + " is not a user and I'm really afraid of having non-users"
			msg += " control me. It could be unsafe, and, Deka-nee told me I shouldn't do that!"
			await api.reply(msg)
			return
		if self.is_op(mention.id, server_id):
			await api.reply("Oh! " + str(mention) + " is already an op! So yay!")
			return
		else:
			if mention.id not in self._operators:
				self._operators[mention.id] = {'role': 'operator', 'servers': []}
			self._operators[mention.id]['servers'].append(server_id)
			_log.debug("Added new operator (UID " + str(mention.id) + ") in server " + server + " (ID " + str(server_id) + ")")
			self._save_all()
			await api.reply(str(mention) + " is now an op! Hooray!")

	async def _make_nonop(self, api: 'PluginAPI', args):
		server_id = await api.require_server()
		server = api.get_guild(server_id).name
		await api.require_op("deop")

		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want to deop")

		mention = util.parse_mention(args[0])

		if not mention.is_user():
			raise BotSyntaxError(args[0] + " just isn't something that can be an operator.")

		if not self.is_op(mention.id, server_id):
			await api.reply("It looks like " + str(mention) + " is already not an op.")
			return
		else:
			if self._operators[mention.id]['role'] == 'superop':
				msg = "Sorry, but " + str(mention) + " is one of my superops, and I could never remove their operator"
				msg += " status!"
				await api.reply(msg)
			else:
				self._operators[mention.id]['servers'].remove(server_id)
				if len(self._operators[mention.id]['servers']) == 0:
					del self._operators[mention.id]
				_log.debug("Removed operator (UID " + str(mention.id) + ") from server " + server + " (ID " + str(server_id) + ")")
				self._save_all()
				await api.reply("Okay. " + str(mention) + " is no longer an op.")

	async def _restart(self, api: 'PluginAPI', args):
		api.require_superop("restart <reason> <announce-down>", None)

		reason = None
		announce = False
		if len(args) > 0:
			reason = args[0]
		if len(args) > 1:
			if args[1].lower() == 'announcedown':
				announce = True
			else:
				msg = "Um, I'm sorry, but I don't understand what you mean with the option `" + str(args[1]) + "`..."
				msg += " I only know about \"announcedown\", is that what you meant?"
				raise BotSyntaxError(msg, api.context)
		_log.info("Going down for a restart")
		if announce:
			msg = "Oh! It looks like " + api.context.author_name() + " has triggered a restart. I'll be going down now, but"
			msg += " don't worry! I'll be right back!"
			await api.announce(msg)
		await self.quit(api, "restart", data={'reason': reason})
		self._return_code = 1

	async def _check_last_command(self):
		if not os.path.exists('ipc/lastcmd.p'):
			return
		_log.debug("Scanning last command info in ipc/lastcmd.p...")
		with open('ipc/lastcmd.p', 'rb') as fp:
			# noinspection PyBroadException
			try:
				info = pickle.load(fp)
			except Exception:
				_log.warning("Could not load ipc/lastcmd.p")
				_log.exception("Exception info:")
		os.remove('ipc/lastcmd.p')

		cmd = info['command']

		if cmd == 'quit':
			# just a normal quit, return
			_log.debug("Last command was `quit`, nothing further to do. Continuing normal startup...")
			return
		elif cmd == 'restart':
			_log.debug("Returning from restart...")
			reason = info['data'].get('reason', None)
			if reason is not None:
				msg = "A restart completed! Yay, everything went well!\n\n"
				msg += "\n\n--------\n\nOh! Oh! I gotta tell you! The whole reason I had to be restarted is because " + reason
				await PluginAPI(self).announce(msg)

	def _configure_loaded_modules(self, module_configs):
		for name in self._bot_modules:
			bot_module = self._bot_modules[name]
			bot_module.load_config(module_configs.get(name, {}))

	def _set_settings_in_loaded_modules(self, module_settings_dict):
		for name in self._bot_modules:
			store = self.module_settings[name]
			mod_state = module_settings_dict.get(name, {'global': {}, 'servers': {}})
			store.set_global_state(mod_state['global'])
			for server_id in mod_state['servers']:
				mod_server_state = mod_state['servers'][server_id]
				if mod_server_state is not None:
					store.set_state(server_id, mod_server_state)

	def _set_state_in_loaded_modules(self, state_dict):
		for name in self._bot_modules:
			bot_module = self._bot_modules[name]
			mod_state = state_dict.get(bot_module.name, {'global': {}, 'servers': {}})
			bot_module.set_global_state(mod_state['global'])
			for server_id in mod_state['servers']:
				mod_server_state = mod_state['servers'][server_id]
				if mod_server_state is not None:
					bot_module.set_state(server_id, mod_server_state)

	def _load_modules(self):
		names = []
		_log.debug("Loading modules...")
		for module_str in commands.__all__:
			new_invoke_handlers = _copy_handler_dict(self._invocations)
			new_regex_handlers = _copy_handler_dict(self._regex_handlers)

			# really confused by what the mention handler initialization is doing it seems it'd break on a lot
			# TODO: take another look at the below
			new_mention_handlers = {
				'any': list(self._any_mention_handlers),
				'self': list(self._self_mention_handlers),
				'specific': _copy_handler_dict(self._mention_handlers)
			}
			new_timer_handlers = _copy_handler_dict(self._timers)
			new_reaction_add_handlers = _copy_handler_dict(self._reaction_add_handlers)
			new_reaction_remove_handlers = _copy_handler_dict(self._reaction_remove_handlers)
			mod = importlib.import_module("masabot.commands." + module_str)
			bot_module = mod.BOT_MODULE_CLASS('resources')
			if bot_module.name.lower() == "core":
				raise BotModuleError("refusing to load module with reserved name 'core'")
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
				elif t.trigger_type == 'REACTION':
					if t.include_react_add:
						self._add_new_reaction_handler(bot_module, t, new_reaction_add_handlers)
					if t.include_react_remove:
						self._add_new_reaction_handler(bot_module, t, new_reaction_remove_handlers)

			self._bot_modules[bot_module.name] = bot_module
			self._invocations = new_invoke_handlers
			self._regex_handlers = new_regex_handlers
			self._mention_handlers = new_mention_handlers['specific']
			self._self_mention_handlers = new_mention_handlers['self']
			self._any_mention_handlers = new_mention_handlers['any']
			self._reaction_add_handlers = new_reaction_add_handlers
			self._reaction_remove_handlers = new_reaction_remove_handlers
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
		:type current_handlers: dict[str, dict[str, timerInfo]]
		:param current_handlers: The timer handlers that already exist. The new handler will be added to the end.
		"""

		api = PluginAPI(self, bot_module.name, None, self._message_history_cache)
		# we assume that add_new_timer_handler will always be called with results
		# of current handlers, so we assume that name can be based off of current
		# number of items
		trig_num = 0
		if bot_module.name in current_handlers:
			trig_num = len(current_handlers[bot_module.name])
		trig_name = "MODTRIGGER" + str(trig_num).zfill(3)
		t = timer.Timer(self._execute_action(api, bot_module.on_timer_fire(api), bot_module), int(trig.timer_duration.total_seconds()), id=trig_name)
		tinfo = _TimerInfo(t, repeat=True, is_module_trigger=True)
		if bot_module.name not in current_handlers:
			current_handlers[bot_module.name] = dict()
		current_handlers[bot_module.name][trig_name] = tinfo

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
	def _add_new_mention_handler(self, bot_module, trig, current_handlers: Dict[str, Any]):
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
			err_msg = "Duplicate mention handler for {0:s} ID {1:d} in module {2!r}; last defined in {3!r} module"
			for sid in mts['users']:
				if sid in current_handlers['specific']['users']:
					_log.warning(err_msg.format('user', sid, bot_module.name, current_handlers['specific']['users'][-1].name))
				else:
					current_handlers['specific']['users'][sid] = []
				current_handlers['specific']['users'][sid].append(bot_module)

			for sid in mts['channels']:
				if sid in current_handlers['specific']['channels']:
					_log.warning(err_msg.format('channel', sid, bot_module.name, current_handlers['specific']['channels'][-1].name))
				else:
					current_handlers['specific']['channels'][sid] = []
				current_handlers['specific']['channels'][sid].append(bot_module)

			for sid in mts['roles']:
				if sid in current_handlers['specific']['roles']:
					_log.warning(err_msg.format('role', sid, bot_module.name, current_handlers['specific']['roles'][-1].name))
				else:
					current_handlers['specific']['roles'][sid] = []
				current_handlers['specific']['roles'][sid].append(bot_module)

	# noinspection PyMethodMayBeStatic
	def _add_new_reaction_handler(self, bot_module, trig, current_handlers):
		"""
		Checks a reaction handler and adds it to the active set of handlers.

		:type bot_module: commands.BotBehaviorModule
		:param bot_module: The module registering a reaction handler.
		:type trig: commands.ReactionTrigger
		:param trig: The trigger that specifies the reactions to be handled.
		:type current_handlers: dict[str, list[commands.BotBehaviorModule] | dict[str, commands.BotBehaviorModule]]
		:param current_handlers: The mention handlers that already exist. The new handler will be added to the end of
		the relevant one.
		"""

		rts = trig
		if len(rts.custom_emoji) == 0 and len(rts.emoji) == 0:
			current_handlers['any'].append(bot_module)
		else:
			for custom_name in rts.custom_emoji:
				if custom_name not in current_handlers['custom']:
					current_handlers['custom'][custom_name] = list()
				current_handlers['custom'][custom_name].append(bot_module)
			for unicode_grapheme in rts.emoji:
				if unicode_grapheme not in current_handlers['unicode']:
					current_handlers['unicode'][unicode_grapheme] = list()
				current_handlers['unicode'][unicode_grapheme].append(bot_module)

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

		log_msg = util.add_context(context, "received invocation " + repr(message.content))
		log_msg += " from " + str(context.author.id) + "/" + context.author_name()
		_log.debug(log_msg)

		core_api = PluginAPI(self, None, context, self._message_history_cache)

		try:
			tokens = self._message_to_tokens(message)
		except ValueError as e:
			await self.show_syntax_error(core_api, str(e))
			return
		cmd = tokens[0]
		args = tokens[1:]

		if cmd == 'help':
			help_cmd = None
			if len(args) > 0:
				help_cmd = args[0]
			await self._execute_action(core_api, self.show_help(core_api, help_cmd))
		elif cmd == 'quit':
			await self._execute_action(core_api, self.quit(core_api))
		elif cmd == 'op':
			await self._execute_action(core_api, self._make_op(core_api, args))
		elif cmd == 'deop':
			await self._execute_action(core_api, self._make_nonop(core_api, args))
		elif cmd == 'showops':
			await self._execute_action(core_api, self.show_ops(core_api))
		elif cmd == 'version':
			await self._execute_action(core_api, self.show_version(core_api))
		elif cmd == 'restart':
			await self._execute_action(core_api, self._restart(core_api, args))
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
			await self._execute_action(core_api, self._run_replchars_command(core_api, action, search, repl))
		elif cmd == 'settings':
			await self._execute_action(core_api, self._run_settings_command(core_api, args))
		elif cmd == 'msgsubs':
			await self._execute_action(core_api, self._run_msgsubs_command(core_api, args))
		elif cmd in self._invocations:
			for handler in self._invocations[cmd]:
				api = PluginAPI(self, handler.name, context, self._message_history_cache)
				await self._execute_action(api, handler.on_invocation(api, meta, cmd, *args), handler)
		else:
			_log.debug("Ignoring unknown command " + repr(cmd))

	async def _handle_mention(self, message: discord.Message):
		handled_already = []
		# noinspection PyTypeChecker
		mentions = [util.Mention(util.MentionType.USER, mid, False) for mid in message.raw_mentions]
		# noinspection PyTypeChecker
		mentions += [util.Mention(util.MentionType.CHANNEL, mid, False) for mid in message.raw_channel_mentions]
		# noinspection PyTypeChecker
		mentions += [util.Mention(util.MentionType.ROLE, mid, False) for mid in message.raw_role_mentions]
		context = BotContext(message)
		meta = MessageMetadata.from_message(message)

		log_msg = "[" + _fmt_channel(context.source) + "]: received mentions from " + str(context.author.id) + "/"
		log_msg += context.author_name()
		# don't actually log this yet unless we do something with the message

		valid_mention_handlers = [i for i in self._any_mention_handlers if i.name not in handled_already]
		if len(valid_mention_handlers) > 0:
			_log.debug(log_msg + ": passing to generic mention handlers")
			for h in valid_mention_handlers:
				api = PluginAPI(self, h.name, context, self._message_history_cache)
				await self._execute_action(api, h.on_mention(api, meta, message.content, mentions), h)
				handled_already.append(h.name)

		if self.client.user.id in [m.id for m in mentions if m.is_user()]:
			for h in self._self_mention_handlers:
				if h.name not in handled_already:
					_log.debug(log_msg + ": passing to self-mention handler " + repr(h.name))
					api = PluginAPI(self, h.name, context, self._message_history_cache)
					await self._execute_action(api, h.on_mention(api, meta, message.content, mentions), h)
					handled_already.append(h.name)

		for m in mentions:
			if m.is_user():
				subidx = 'users'
			elif m.is_channel():
				subidx = 'channels'
			elif m.is_role():
				subidx = 'roles'
			else:
				raise BotSyntaxError("Mention not of type users, channels, or roles: " + repr(m))

			if m.id in self._mention_handlers[subidx]:
				for h in self._mention_handlers[subidx][m]:
					if h.name not in handled_already:
						_log.debug(log_msg + ": passing to " + str(m) + " mention handler " + repr(h.name))
						api = PluginAPI(self, h.name, context, self._message_history_cache)
						await self._execute_action(api, h.on_mention(api, meta, message.content, list(mentions)), h)
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
					api = PluginAPI(self, h.name, context, self._message_history_cache)
					await self._execute_action(api, h.on_regex_match(api, meta, *match_groups), h)

	async def _execute_action(self, api: PluginAPI, action, mod=None):
		await self.randomize_presence(self.core_settings.get_global('presence-chance'))
		try:
			mod_name = repr(mod.name) if mod is not None else "core"
			_log.debug("Executing registered action in " + mod_name + " module...")
			await action
		except BotPermissionError as e:
			msg = "User " + e.author.name + "#" + e.author.discriminator + " (ID: " + str(e.author.id) + ") was denied"
			msg += " permission to execute privileged command " + repr(e.command)
			if e.module is not None:
				msg += " in module " + repr(e.module)
			msg += " (needed at least '" + e.required_role + "' status)"
			msg += "."
			_log.error(msg)
			msg = "Sorry, <@!" + str(e.author.id) + ">, but only my " + e.required_role + " users can do that."
			await api.reply(msg)
		except BotSyntaxError as e:
			_log.exception("Syntax error")
			await self.show_syntax_error(api, str(e))
		except BotModuleError as e:
			_log.exception("Module error")
			msg = "Oh no, " + api.mention_user() + "-samaaaaa! I can't quite do that! "
			await api.reply(msg + str(e))

		# TODO: notify somewhere that having state as opposed to settings implies a save on every handle.
		if mod is not None and mod.save_state_on_trigger:
			self._save_all()

	def _message_to_tokens(self, message):
		"""
		Converts a message to a series of tokens for parsing into an invocation.

		:type message: discord.Message
		:param message: The message whose contents are to be parsed.
		:rtype: list[str]
		:return: The tokens.
		"""
		content = message.content[len(self.prefix):]
		""":type : str"""

		# special case; do NOT apply replacements if the replchars command is being invoked:
		pre_analyze = content.split()
		if pre_analyze[0] == 'replchars':
			tokens = pre_analyze
		else:
			for search in self._invocation_replacements:
				replacement = self._invocation_replacements[search]
				content = content.replace(search, replacement)

			tokens = shlex.split(content)

		tokens[0] = tokens[0].lower()

		return tokens

	def _load_builtin_state(self, state_dict):
		if '__BOT__' not in state_dict:
			return
		builtin_state = state_dict['__BOT__']

		if 'operators' in builtin_state:
			for op in builtin_state['operators']:
				# superop roles will be loaded later during config reading
				self._operators[op] = dict(builtin_state['operators'][op])

		if 'invocation_replacements' in builtin_state:
			self._invocation_replacements = dict(builtin_state['invocation_replacements'])

		if 'reaction_subscriptions' in builtin_state:
			self._reaction_subscriptions = dict(builtin_state['reaction_subscriptions'])

		settings_data = builtin_state['settings']

		core_settings = settings_data['core']
		if 'global' in core_settings:
			self.core_settings.set_global_state(core_settings['global'])
		for server in core_settings['servers']:
			server_settings = core_settings['servers'][server]
			self.core_settings.set_state(server, server_settings)

	def _initialize_module_settings(self):
		for module_name in self._bot_modules:
			bot_module = self._bot_modules.get(module_name, None)
			if bot_module is None:
				_log.warning("found module settings for unused module " + repr(module_name) + "; ignoring")
				continue

			store = settings.SettingsStore()

			context_limitations = {}
			dupe_msg = "got duplicate settings key {!r} for module {!r}; previous key will be replaced"
			seen_keys = list()
			for k in bot_module.per_server_settings_keys:
				if k.name in seen_keys:
					_log.warning(dupe_msg.format(k.name, module_name))
				store.register_key(k)
				seen_keys.append(k.name)
				if k.name in context_limitations:
					del context_limitations[k.name]
			for k in bot_module.global_settings_keys:
				if k.name in seen_keys:
					_log.warning(dupe_msg.format(k.name, module_name))
				store.register_key(k)
				context_limitations[k.name] = 'global'
				seen_keys.append(k.name)
			for k in bot_module.server_only_settings_keys:
				if k.name in seen_keys:
					_log.warning(dupe_msg.format(k.name, module_name))
				store.register_key(k)
				context_limitations[k.name] = 'server'
				seen_keys.append(k.name)
			self._module_settings_context_limitations[module_name] = context_limitations

			self.module_settings[module_name] = store

	def register_message_reaction_subscriber(self, mod: str, mid: int):
		if mid not in self._reaction_subscriptions:
			self._reaction_subscriptions[mid] = dict()
		if mod not in self._reaction_subscriptions[mid]:
			self._reaction_subscriptions[mid][mod] = True
			self._save_all()

	def unregister_message_reaction_subscriber(self, mod: str, mid: int):
		if mid not in self._reaction_subscriptions:
			return
		if mod not in self._reaction_subscriptions[mid]:
			return
		del self._reaction_subscriptions[mid][mod]

		if len(self._reaction_subscriptions[mid]) == 0:
			del self._reaction_subscriptions[mid]

		self._save_all()

	def _save_all(self):
		state_dict = {
			'__BOT__': {
				'operators': {op: self._operators[op] for op in self._operators if self._operators[op]['role'] != 'superop'},
				'invocation_replacements': dict(self._invocation_replacements),
				'reaction_subscriptions': dict(self._reaction_subscriptions),
				'settings': {
					'core': {
						'global': self.core_settings.get_global_state(),
						'servers': {server.id: self.core_settings.get_state(server.id) for server in self.connected_guilds},
					},
					'modules': {mod_name: {
						'global': self.module_settings[mod_name].get_global_state(),
						'servers': {server.id: self.module_settings[mod_name].get_state(server.id) for server in self.connected_guilds}
					} for mod_name in self._bot_modules},
				},
			},
			'__VERSION__': version.get_version()
		}

		for m_name in self._bot_modules:
			mod = self._bot_modules[m_name]
			state_dict[mod.name] = {
				'global': mod.get_global_state(),
				'servers': {}
			}
			servers_dict = state_dict[mod.name]['servers']
			""":type: Dict[int, Dict]"""
			for g in self.connected_guilds:
				mod_state = mod.get_state(g.id)
				if mod_state is not None:
					servers_dict[g.id] = mod_state

		with open(self._state_file, "wb") as fp:
			pickle.dump(state_dict, fp)

		_log.debug("Saved state to disk")

	def remove_timer(self, module: Optional[str], id: str):
		"""Remove an existing timer. After this function returns, the timer
		will no longer fire, and is removed from tracking."""
		modidx = None
		modname = "the core module"
		if module is not None:
			modidx = module
			modname = "module " + repr(module)

		if modidx not in self._timers:
			errmsg = "There are not currently any timers defined for " + modname
			raise KeyError(errmsg)
		
		if id not in self._timers[modidx]:
			errmsg = "There is not currently a timer defined for " + modname
			errmsg += " with ID " + repr(id)
			raise KeyError(errmsg)
		
		del self._timers[modidx][id]
		if len(self._timers[modidx]) == 0:
			del self._timers[modidx]
		_log.debug("Removed timer with ID " + repr(id) + "for " + modname)

	def add_timer(self, module: Optional[str], t: timer.Timer, repeat: bool) -> str:
		"""Create a new timer for a module for an action in the future. The
		timer is added to the list of timers that the main tick routine fires,
		and will fire at the correct time.
		
		Note that timers added are never saved as part of state; modules that
		wish to track pending operations will need to keep them as part of state
		and then rebuild any timers at state load time.

		:return: The name of the timer, that can be used to later remove it if
		needed. Note that while timers that do not repeat will be removed
		automatically after firing, it can still be useful to have the ID in
		case it needs to be cancelled before firing.
		"""

		modidx = None
		modname = "the core module"
		if module is not None:
			modidx = module
			modname = "module " + repr(module)
		
		# race condition - could overwrite name if more than one added
		if t.id is None:
			if modidx not in self._timers:
				id_num = "000"
			else:
				id_num = ""
				for x in range(1000):
					id_num = str(x).zfill(3)
					if id_num not in self._timers[modidx]:
						break
					elif id_num == "999":
						raise TypeError("could not generate valid name for timer; are there too many added?")
			t.id = id_num
		tinfo = _TimerInfo(t, repeat, False)
		if modidx not in self._timers:
			self._timers[modidx] = dict()
		self._timers[modidx][t.id] = tinfo
		_log.debug("Added timer with ID " + repr(t.id) + "for " + modname)
		return t.id


def start(configpath, logdir, statepath):
	if not os.path.exists('resources'):
		os.mkdir('resources')
	bot = MasaBot(configpath, logdir, statepath)
	retval = 0
	try:
		retval = bot.run()
	except KeyboardInterrupt:
		# this is a normal shutdown, so notify bot by writing to last command
		with open('ipc/lastcmd.p', 'wb') as fp:
			pickle.dump({'command': 'quit'}, fp)
	if retval != 0:
		sys.exit(retval)


def _copy_handler_dict(dict_to_copy):
	new_dict = {}
	for k in dict_to_copy:
		v = dict_to_copy[k]
		if type(v) == list:
			new_dict[k] = list(v)
		if type(v) == dict:
			new_dict[k] = _copy_handler_dict(v)
		else:
			new_dict[k] = v
	return new_dict
