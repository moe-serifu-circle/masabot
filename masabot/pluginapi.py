from typing import Any, Optional, Callable, Union, List, Tuple

import asyncio
# noinspection PyPackageRequirements
import discord
import logging
import shlex

from . import util
from .messagecache import MessageHistoryCache
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
	def __init__(
			self,
			target_bot: Any,
			for_plugin: Optional[str] = None,
			context: Optional[BotContext] = None,
			history: Optional[MessageHistoryCache] = None
	):
		"""
		Create a new plugin API object.

		:param target_bot: The bot that the new MasaBotPluginAPI will affect.
		"""
		self._bot = target_bot
		self._context: Optional[BotContext] = context
		self._plugin_name = for_plugin
		self._server_set: Optional[int] = None
		self._history = history

	@property
	def history(self) -> MessageHistoryCache:
		if self._history:
			return self._history
		else:
			raise ValueError("history was never set")

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
					try:
						await ch.send(message)
					except discord.Forbidden:
						pass
					_log.debug(util.add_context(ch, "sent: {!r}", message))

	def get_bot_id(self) -> int:
		"""Get the ID of the user that represents the currently connected bot."""
		return self._bot.client.user.id

	def subscribe_reactions(self, mid: int):
		"""
		Set a message (by message ID) as sending further reactions only to it. If already called, the claimant will be
		added to the list of subscribers and will still receive notifications. It is safe to call this method even if
		has already been called.

		Subscriptions will persist across restarts.
		"""
		self._bot.register_message_reaction_subscriber(self._plugin_name, mid)

	def unsubscribe_reactions(self, mid: int):
		"""
		Unregisters this module as being a reaction subscriber to the given message. If it is the only subscriber, the
		message will be changed back to broadcast and all modules will receive reaction events from it once more
		regardless of whether they are subscribed if they are triggered by ReactionTrigger.
		"""
		self._bot.unregister_message_reaction_subscriber(self._plugin_name, mid)

	async def get_emoji_from_value(self, emoji_value: Union[str, int]) -> Optional[Union[str, discord.Emoji]]:
		"""Get emoji to pass to other api functions of discord. If emoji value is an int it will be an ID and the
		PartialEmoji representing it is returned. If emoji value is a str it is passed through unchanged."""
		if isinstance(emoji_value, int):
			em = self._bot.client.get_emoji(emoji_value)
			return em
		return emoji_value

	async def get_message_by_id(self, mid: int) -> discord.Message:
		return await self.context.source.fetch_message(mid)

	async def react(self, emoji_text: Union[discord.PartialEmoji, str]):
		msg = self.context.message
		await msg.add_reaction(emoji_text)

	async def unreact(self, emoji_text: Union[discord.PartialEmoji, str]):
		msg = self.context.message
		await msg.remove_reaction(emoji_text, member=discord.Object(self.get_bot_id()))

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
		msg = await dest.send(message)
		_log.debug(util.add_context(self.context, "sent {!r}", message))
		return msg

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

		msg = await dest.send(content=message, file=discord.File(fp, filename=filename))
		_log.debug(util.add_context(self.context, " sent <FILE>"))
		return msg

	def require_superop(self, command, module, message="Operation requires superop status"):
		"""
		Ensure that the user that invoked a command has superop permission. If the user does not have superop
		permission, a BotPermissionError is raised.

		:param command: A string representing the command that is attempting to be executed. This should include enough
		of the invocation to distinguish it from other potential invocations of the same command.
		:param module: The module that is requiring operator permissions. This can be set to None if it is a built-in
		command that is requiring op.
		:param message: The message to put in the bot permission error if the check for op fails. This can be left as
		the default, as a suitable error message will be generated from the other properties if this method is called
		from within a core command function or from within one of a module's on_X methods().
		"""
		if not self._bot.is_superop(self.context.author.id):
			raise BotPermissionError(self.context, command, 'superop', module, message=message)

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

	async def select_message(self, prompt: str, timeout: int = 60) -> Optional[discord.message]:
		"""
		Prompt the user to select a message in the server. They will be shown a
		prompt, and the ID of the next message they reply with ✅ on will be
		returned.

		This function requires a server context.

		:param prompt: The prompt to show the user.
		:param timeout: The number of seconds to wait before timing out the prompt.
		:return: The message selected by the user, or None if the prompt times out.
		"""
		sid = await self.require_server()
		full_message = prompt + "\n\n(React with ✅ on the message you want to select)"
		await self.reply(full_message)
		log_msg = "prompt for " + self.context.author_name() + " started for message selection"
		_log.debug(util.add_context(self.context, log_msg))

		def check_react(rc: discord.RawReactionActionEvent):
			if rc.guild_id != sid:
				return False
			if rc.user_id != self.context.author.id:
				return False
			if not rc.emoji.is_unicode_emoji:
				return False
			if not rc.emoji.name == '✅':
				return False
			return True

		try:
			r = await self._bot.client.wait_for('raw_reaction_add', timeout=timeout, check=check_react)
			rct = util.Reaction.from_raw(r)
			await rct.fetch(self._bot.client)
			message = rct.source_message
		except asyncio.TimeoutError:
			message = None
		if message is None:
			_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " timed out"))
		else:
			log_msg = util.add_context(self.context, "prompt for " + self.context.author_name() + " received MID:")
			log_msg += repr(message.id)
			_log.debug(log_msg)
		return message

	async def prompt_for_emote(self, prompt: str, timeout: int = 60) -> util.Reaction:
		"""
		Prompt the user to reply to give an emoji reaction and returns it.

		This function requires a server context.

		:param prompt: The prompt to show the user.
		:param timeout: The number of seconds to wait before timing out the prompt.
		:return: The message selected by the user, or None if the prompt times out.
		"""
		full_message = prompt + "\n\n(React to this message with your answer)"
		msg = await self.reply(full_message)
		log_msg = "prompt for " + self.context.author_name() + " started for emoji-by-reaction selection"
		_log.debug(util.add_context(self.context, log_msg))

		def check_react(rc):
			if rc.message_id != msg.id:
				return False
			if rc.user_id != self.context.author.id:
				return False
			return True

		try:
			r = await self._bot.client.wait_for('raw_reaction_add', timeout=timeout, check=check_react)
			react = util.Reaction.from_raw(r)
			await react.fetch(self._bot.client)
		except asyncio.TimeoutError:
			react = None
		if react is None:
			_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " timed out"))
		else:
			log_msg = util.add_context(self.context, "prompt for " + self.context.author_name() + " received emoji:")
			log_msg += repr(react.emoji)
			_log.debug(log_msg)

		return react

	async def prompt_for_emote_option(self, prompt: str, options: List, timeout: int = 60) -> util.Reaction:
		"""
		Prompt the user to react with one of the given emoji, then returns it.

		This function requires a server context.

		:param prompt: The prompt to show the user.
		:param options: The emoji to choose from. Each must be either a string for
		a unicode emoji or an integer for a custom emoji ID.
		:param timeout: The number of seconds to wait before timing out the prompt.
		:return: The message selected by the user, or None if the prompt times out.
		"""
		full_message = prompt + "\n\n(React to this message with your answer)"
		msg = await self.reply(full_message)
		log_msg = "prompt for " + self.context.author_name() + " started for emoji-by-reaction selection"
		_log.debug(util.add_context(self.context, log_msg))
		for opt in options:
			if isinstance(opt, str):
				await msg.add_reaction(opt)
			else:
				emoji = self._bot.client.get_emoji(opt)
				await msg.add_reaction(emoji)

		def check_react(rc):
			if rc.message_id != msg.id:
				return False
			if rc.user_id != self.context.author.id:
				return False
			return util.reaction_index(rc) in options

		try:
			r = await self._bot.client.wait_for('raw_reaction_add', timeout=timeout, check=check_react)
			react = util.Reaction.from_raw(r)
			await react.fetch(self._bot.client)
		except asyncio.TimeoutError:
			react = None
		if react is None:
			_log.debug(util.add_context(self.context, "prompt for " + self.context.author_name() + " timed out"))
		else:
			log_msg = util.add_context(self.context, "prompt for " + self.context.author_name() + " received emoji:")
			log_msg += repr(react.emoji)
			_log.debug(log_msg)
		return react

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

	def get_channel(self, server_channel_id: Optional[Tuple[int, int]] = None) -> Optional[discord.TextChannel]:
		"""Return the current channel. None is returned if there is no current channel;
		consider doing bot_api.require_server()
		for cases where a server ID is needed, followed by a query to get_channel.

		If the ID is passed in, always gets that server/channel ID.
		"""
		if server_channel_id is None:
			return self.context.source
		else:
			return self.get_guild(server_channel_id[0]).get_channel(server_channel_id[1])

	def get_guild(self, guild_id: Optional[int] = None) -> Optional[discord.Guild]:
		"""Return the current guild. None is returned if there is no current guild; consider doing bot_api.require_server()
		for cases where a server ID is needed.

		If the ID is passed in, always gets that server ID.
		"""
		if guild_id is None:
			return self.context.get_guild()
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
			option_1: Any = "yes",
			option_2: Any = "no",
			*additional_options
	) -> Optional[Any]:
		"""
		Prompt the user to select an option. Not case-sensitive; all options are converted to lower-case. Times out
		after 60 seconds, and returns None then.

		:param message: The message to show before the prompt.
		:param option_1: The first option.
		:param option_2: The second option.
		:param additional_options: Any additional options.
		:return: The option selected by the user, or None if the prompt times out.
		"""
		if str(option_1).lower() == str(option_2).lower():
			raise ValueError("option 1 and 2 are equal")

		all_options = {
			self._bot.prefix + self._bot.prefix + str(option_1).lower(): option_1,
			self._bot.prefix + self._bot.prefix + str(option_2).lower(): option_2
		}

		full_message = message + "\n\nSelect one of the following options: \n"
		full_message += "* `" + self._bot.prefix + self._bot.prefix + str(option_1).lower() + "`\n"
		full_message += "* `" + self._bot.prefix + self._bot.prefix + str(option_2).lower() + "`\n"
		for op in additional_options:
			if str(op).lower() in all_options:
				raise ValueError("Multiple equal options for '" + op.lower() + "'")
			response = self._bot.prefix + self._bot.prefix + str(op).lower()
			full_message += "* `" + response + "`\n"
			all_options[response] = op

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
		Get a user from a snowflake ID. If no ID is provided, gets the message author.
		:param snowflake_id: The ID.
		:return: The user.
		"""
		if snowflake_id is None:
			return self.context.author
		return self._bot.client.get_user(snowflake_id)

	def save(self):
		"""
		Persist all state. Use sparingly. Most cases can be handled with
		the use of !settings, which auto-saves on mutation, or has_state=True
		in module ctor.

		Direct use of save should be used only for high throughput events such
		as receiving all emoji.
		"""
		log_msg = util.add_context(self.context, "save was directly called by module")
		_log.debug(log_msg)

		# TODO: Better way of marking this off/better persistence settings overhaul. Save should be accessible by things
		# that want to manually save but things should also be able to specify that activity should be auto-saved in the
		# default case.
		#
		# could come with method to only save module state.
		# Need to update this to non-protected access and remove PyProtectedMember directive when done.
		# noinspection PyProtectedMember
		self._bot._save_all()

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

	async def get_emoji(self, eid) -> discord.Emoji:
		return await self._bot.client.get_emoji(eid)

	def get_messages(self, from_current: bool = False, limit: int = 0) -> List[discord.Message]:
		"""Return messages, newest first"""
		# TODO: work for DMs
		if self.context.is_pm:
			return list()

		gid = self.get_guild().id
		cid = self.get_channel().id
		full_list = self.history.for_channel(gid, cid)

		if from_current:
			loc_idx = -1
			idx = 0
			for m in full_list:
				if m.id == self.context.message.id:
					loc_idx = idx
					break
				idx += 1
			if loc_idx != -1:
				full_list = full_list[loc_idx:]

		if 0 < limit < len(full_list):
			full_list = full_list[:limit]

		return full_list

	async def with_dm_context(self) -> 'PluginAPI':
		return PluginAPI(self._bot, self._plugin_name, await self.context.to_dm_context(), self._history)

	async def with_message_context(self, message: discord.Message) -> 'PluginAPI':
		return PluginAPI(self._bot, self._plugin_name, BotContext(message), self._history)
