from typing import Any, Optional, Callable, Union

import asyncio
import discord
import logging
import shlex

from . import util
from .util import BotModuleError, BotPermissionError
from .context import BotContext

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class PluginAPI:
	"""
	BotPluginAPI contains all methods needed for a plugin to perform actions with the bot without directly exposing the
	actual MasaBot object. We implement a proxy pattern here to hide the actual bot implementation from callers.

	It is intended to be created outside of the plugin's control and then passed to plugins.
	"""
	def __init__(self, target_bot: Any, for_plugin: Optional[str] = None, context: Optional[BotContext] = None):
		"""
		Create a new plugin API object.

		:param target_bot: The bot that the new MasaBotPluginAPI will affect.
		"""
		self._bot = target_bot
		self._context: Optional[BotContext] = context
		self._plugin_name = for_plugin
		self._server_set: Optional[int] = None

	@property
	def context(self) -> BotContext:
		if self._context:
			return self._context
		else:
			raise ValueError("context was never set")

	@context.setter
	def context(self, context: BotContext):
		self._context = context

	async def announce(self, message: str):
		"""
		Send a message to all applicable channels on all servers. The channels are those that are set as the
		announce channels in the configuration.

		:param message: The message to send.
		"""
		for g in self._bot.connected_guilds:
			for ch in g.channels:
				if ch.type == discord.ChannelType.text and ('#' + ch.name) in self._bot.announce_channels:
					await ch.send(message)
					_log.debug(util.add_context(ch, "sent: {!r}", message))

	def get_bot_id(self) -> int:
		"""Get the ID of the user that represents the currently connected bot."""
		return self._bot.client.user.id

	async def react(self, emoji_text: str):
		await self.context.message.add_reaction(emoji_text)

	def reset_server(self):
		"""
		Reset the server to its original state if one were set with require_server(). If require_server() was not called
		then this function has no effect.
		"""
		self._server_set = None

	async def require_server(self) -> int:
		"""
		Prompt the user to give a server ID only if the context does not already contain one.
		:return: Either the user-prompted ID if in a DM, or the current server ID.
		"""
		if self.context.is_pm:
			if self._server_set is not None:
				return self._server_set
			got_valid_server = False
			server_id = -1
			while not got_valid_server:
				resp = await self.prompt("Ok, really quick, what server should I do that for?")
				if resp is None:
					break
				try:
					server_id = int(resp)
				except ValueError:
					resp = ' '.join(shlex.split(resp))
					found_guild = None
					for g in self._bot.client.guilds:
						g = g
						""":type: discord.Guild"""
						norm_guild_name = ' '.join(shlex.split(g.name))
						if norm_guild_name.lower().find(resp.lower()) > -1:
							found_guild = g
							break
					if found_guild:
						conf_msg = "Just to make sure, I should do that for {:s}, right?"
						if not await self.confirm(conf_msg.format(found_guild.name)):
							await self.reply("Sorry; it looked really similar >.<")
							continue
						server_id = found_guild.id
					else:
						await self.reply("Oh no! I'm not in any servers that match that @_@")
						continue
				if server_id not in [g.id for g in self._bot.connected_guilds]:
					await self.reply("I'm not in a guild that matches that.")
					continue
				got_valid_server = True
			if not got_valid_server:
				raise BotModuleError("Sorry, but I can't do that without a server!")
			self._server_set = server_id
			return server_id
		else:
			return self.context.source.guild.id

	async def reply(self, message: str):
		"""
		Send a message in the same context as the message that caused the action to start.

		:param message: The message to send.
		"""
		if self.context.is_pm:
			dest = self.context.author
		else:
			dest = self.context.source
		await dest.send(message)
		_log.debug(util.add_context(self.context, "sent {!r}", message))

	async def reply_with_file(self, fp: Any, filename: str = None, message: str = None):
		"""
		Send a file in the same context as the message that caused the action to start.

		:param fp: The file-like object to upload.
		:param filename: The name that the file will have once uploaded to the server.
		:param message: A message to include before the file. Can be None to send only the file.
		"""
		if self.context.is_pm:
			dest = self.context.author
		else:
			dest = self.context.source

		await dest.send(content=message, file=discord.File(fp, filename=filename))
		_log.debug(util.add_context(self.context, " sent <FILE>"))

	def require_master(self, command, module, message="Operation requires master status"):
		"""
		Ensure that the user that invoked a command has master permission. If the user does not have master
		permission, a BotPermissionError is raised.

		:param command: A string representing the command that is attempting to be executed. This should include enough
		of the invocation to distinguish it from other potential invocations of the same command.
		:param module: The module that is requiring operator permissions. This can be set to None if it is a built-in
		command that is requiring op.
		:param message: The message to put in the bot permission error if the check for op fails. This can be left as
		the default, as a suitable error message will be generated from the other properties if this method is called
		from within a core command function or from within one of a module's on_X methods().
		"""
		if not self._bot.is_master(self.context.author.id):
			raise BotPermissionError(self.context, command, 'master', module, message=message)

	async def require_op(
			self,
			command: str,
			message: str = "Operation requires operator status",
			server: Optional[int] = None
	):
		"""
		Ensure that the user that invoked a command has operator permission. If the user does not have operator
		permission, a BotPermissionError is raised.

		:param command: A string representing the command that is attempting to be executed. This should include enough
		of the invocation to distinguish it from other potential invocations of the same command.
		:param message: The message to put in the bot permission error if the check for op fails. This can be left as
		the default, as a suitable error message will be generated from the other properties if this method is called
		from within a core command function or from within one of a module's on_X methods().
		:param server: if set, ensures that the user is op in the given server.
		"""
		if server is None:
			server_id = await self.require_server()
		else:
			server_id = server
		if not self._bot.is_op(self.context.author.id, server_id):
			cmd_end = " (in server " + str(server_id) + ")"
			raise BotPermissionError(self.context, command + cmd_end, 'operator', self._plugin_name, message=message)

	async def prompt(self, message: str, timeout: int = 60, type_conv: Callable[[str], Any] = str) -> Any:
		"""
		Prompt the user for open-ended input. Returns None if the prompt times out.

		:param message: The message to show before the prompt.
		:param timeout: The number of seconds to wait before timing out the prompt.
		:param type_conv: The type to put the input through before returning it.
		:return: The input given by the user, or None if the prompt times out.
		"""

		full_message = message + "\n\n(Enter `" + (self._bot.prefix * 2) + "` followed by your answer)"
		await self.reply(full_message)
		_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " started"))

		def check_option(msg):
			if msg.author != self.context.author:
				return False
			if not msg.content.startswith(self._bot.prefix * 2):
				return False
			# noinspection PyBroadException
			try:
				type_conv(msg.content[len(self._bot.prefix * 2):])
			except Exception:
				return False
			return True

		try:
			message = await self._bot.client.wait_for('message', timeout=timeout, check=check_option)
		except asyncio.TimeoutError:
			message = None
		if message is None:
			_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " timed out"))
			return None
		else:
			log_msg = util.add_context(self.context, "prompt for " + self.context.author_name() + " received ")
			log_msg += repr(message.content)
			_log.debug(log_msg)
			return type_conv(message.content[len(self._bot.prefix * 2):])

	def mention_user(self, user_id: Optional[int] = None) -> str:
		if user_id is None:
			user_id = self.context.author.id
		return '<@' + str(user_id) + '>'

	def typing(self):
		return self.context.source.typing()

	def get_guild(self, guild_id: Optional[int] = None) -> Optional[discord.Guild]:
		"""Return the current guild. None is returned if there is no current guild; consider doing bot_api.require_server()
		for cases where a server ID is needed.

		If the ID is passed in, always gets that server ID.
		"""
		if guild_id is None:
			if self.context.is_pm:
				return None
			else:
				return self.context.source.guild
		else:
			return self._bot.client.get_guild(guild_id)

	async def confirm(self, message: str) -> bool:
		"""
		Prompt the user to select a yes-or-no option, and defaults to False if they do not answer. Times out after 60
		seconds, and returns False then.

		:param message: The message to show before the prompt.
		:return: The option selected by the user, or False if the prompt times out.
		"""
		answer = await self.prompt_for_option(message)
		if answer is None:
			msg = "Sorry, " + self.context.mention() + ", but the prompt timed out! I'll assume 'no' for now; if that's not"
			msg += " what you wanted, go ahead and rerun the command again, okay?"
			await self.reply(msg)
			return False
		elif answer == "yes":
			return True
		elif answer == "no":
			return False

	async def prompt_for_option(
			self,
			message: str,
			option_1: str = "yes",
			option_2: str = "no",
			*additional_options
	) -> Optional[str]:
		"""
		Prompt the user to select an option. Not case-sensitive; all options are converted to lower-case. Times out
		after 60 seconds, and returns None then.

		:param message: The message to show before the prompt.
		:param option_1: The first option.
		:param option_2: The second option.
		:param additional_options: Any additional options.
		:return: The option selected by the user, or None if the prompt times out.
		"""
		if option_1.lower() == option_2.lower():
			raise ValueError("option 1 and 2 are equal")

		all_options = {
			self._bot.prefix + self._bot.prefix + option_1.lower(): option_1.lower(),
			self._bot.prefix + self._bot.prefix + option_2.lower(): option_2.lower()
		}

		full_message = message + "\n\nSelect one of the following options: \n"
		full_message += "* `" + self._bot.prefix + self._bot.prefix + option_1.lower() + "`\n"
		full_message += "* `" + self._bot.prefix + self._bot.prefix + option_2.lower() + "`\n"
		for op in additional_options:
			if op.lower() in all_options:
				raise ValueError("Multiple equal options for '" + op.lower() + "'")
			full_message += "* `" + self._bot.prefix + self._bot.prefix + op + "`\n"
			all_options[self._bot.prefix + self._bot.prefix + op.lower()] = op.lower()

		await self.reply(full_message)
		_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " started"))

		def check_option(msg):
			if msg.author != self.context.author:
				return False
			return msg.content in all_options

		try:
			message = await self._bot.client.wait_for('message', timeout=60, check=check_option)
		except asyncio.TimeoutError:
			message = None
		if message is None:
			_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " timed out"))
			return None
		else:
			log_msg = util.add_context(self.context, "prompt for " + self.context.author_name() + " received ")
			log_msg += repr(message.content)
			_log.debug(log_msg)
			return all_options[message.content]

	def get_user(self, snowflake_id: Optional[int] = None) -> Optional[discord.User]:
		"""
		Get a user from a snowflake ID.
		:param snowflake_id: The ID.
		:return: The user.
		"""
		if snowflake_id is None:
			return self.context.author
		return self._bot.client.get_user(snowflake_id)

	async def get_setting(self, key: str) -> Union[int, str, bool, float]:
		if self._plugin_name is None:
			if self.context.is_pm:
				return self._bot.core_settings.get_global(key)
			else:
				return self._bot.core_settings.get(self.context.source.guild.id, key)
		else:
			context_restriction = self._bot.get_setting_restrictions(self._plugin_name, key)
			mod_settings = self._bot.module_settings[self._plugin_name]
			if context_restriction is None:
				if self.context.is_pm:
					return mod_settings.get_global(key)
				else:
					return mod_settings.get(self.context.source.guild.id, key)
			elif context_restriction == 'global':
				return mod_settings.get_global(key)
			elif context_restriction == 'server':
				server_id = await self.require_server()
				return mod_settings.get(server_id, key)

	# no set_setting because settings are now centralized

	async def with_dm_context(self) -> 'PluginAPI':
		return PluginAPI(self._bot, self._plugin_name, await self.context.to_dm_context())
