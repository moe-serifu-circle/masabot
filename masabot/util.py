import math

from . import http
import urllib.parse
import enum
# noinspection PyPackageRequirements
import discord
from typing import Optional, Sequence, Iterable, Union, Any, List

discord_char_limit = 2000


def add_context(ctx: Any, message: str, *params) -> str:
	"""Add context to a message that includes info on the given context. The context could be a discord model class
	of any place where a message could be sent (discord.abc.Messageable) or it could be an actual BotContext."""

	def user_str(user: Union[discord.User, discord.Member]) -> str:
		return "{:d}/{:s}#{:s}".format(user.id, user.name, user.discriminator)

	def dm_name(user: Union[discord.User, discord.Member]) -> str:
		return "DM {:s}".format(user_str(user))

	def guild_ch_str(
			channel: Union[discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel],
			channel_name: str
	) -> str:
		return "{:d}:{:d}/{!r}:{:s}".format(channel.guild.id, channel.id, channel.guild.name, channel_name)

	def text_ch_name(channel: discord.TextChannel) -> str:
		return guild_ch_str(channel, "#{:s}".format(channel.name))

	def voice_ch_name(channel: discord.VoiceChannel) -> str:
		return guild_ch_str(channel, "<VOICE>{!r}".format(channel.name))

	def group_ch_name(channel: discord.GroupChannel) -> str:
		ch_name = "Group DM with "
		for u in channel.recipients:
			ch_name += "{:d},".format(u.id)
		ch_name = ch_name[:-1]  # remove trailing comma
		ch_name += "/"
		for u in channel.recipients:
			ch_name += "{:s}#{:s},".format(u.name, u.discriminator)
		ch_name = ch_name[:-1]  # remove trailing comma
		return ch_name

	context_name = None

	try:
		if ctx.is_pm:
			context_name = dm_name(ctx.author)
		else:
			ch = ctx.source
			if ch.type == discord.ChannelType.text:
				context_name = text_ch_name(ch)
			elif ch.type == discord.ChannelType.voice:
				context_name = voice_ch_name(ch)
			elif ch.type == discord.ChannelType.private:
				# should never happen, but handle just in case
				context_name = dm_name(ctx.author)
			elif ch.type == discord.ChannelType.group:
				context_name = group_ch_name(ch)
	except AttributeError:
		# getting here based on only the bot context having a .source
		try:
			context_name = dm_name(ctx)
		except AttributeError:
			# getting here based on only user-ish things having a .discriminator
			ch = ctx
			if ch.type == discord.ChannelType.text:
				context_name = text_ch_name(ch)
			elif ch.type == discord.ChannelType.voice:
				context_name = voice_ch_name(ch)
			elif ch.type == discord.ChannelType.private:
				# should never happen, but handle just in case
				context_name = dm_name(ch.recipient)
			elif ch.type == discord.ChannelType.group:
				context_name = group_ch_name(ch)

	if context_name is None:
		context_name = "Channel of Unknown Type"

	if len(params) > 0:
		message = message.format(*params)

	return "[{:s}]: {:s}".format(context_name, message)


class BotSyntaxError(Exception):
	def __init__(self, message, context=None):
		super().__init__(message)
		self.context = context


class BotPermissionError(Exception):
	def __init__(self, context, command, required_role: str, module=None, message=None):
		if message is None:
			message = "Operation requires operator permission"
		self.author = context.author
		self.command = command
		self.module = module
		self.context = context
		self.required_role = required_role
		super().__init__(message)


class BotModuleError(RuntimeError):
	def __init__(self, message, context=None):
		super().__init__(message)
		self.context = context


class MentionType(enum.IntEnum):
	USER = enum.auto()
	CHANNEL = enum.auto()
	ROLE = enum.auto()


class Mention:
	def __init__(self, m_type: MentionType, m_id: int, has_nick: bool):
		self.resource_type = m_type
		self.id = m_id
		":type: int"
		self._has_nick = has_nick

	def has_nick(self) -> bool:
		return self._has_nick

	def is_user(self) -> bool:
		return self.resource_type == MentionType.USER

	def is_channel(self) -> bool:
		return self.resource_type == MentionType.CHANNEL

	def is_role(self) -> bool:
		return self.resource_type == MentionType.ROLE

	def __str__(self) -> str:
		return "<" + ('#' if self.is_channel() else '@') + ('!' if self.is_role() else '') + str(self.id) + ">"

	def __repr__(self) -> str:
		return "Mention(" + repr(self.resource_type) + ", " + repr(self.id) + ", " + repr(self.has_nick()) + ")"

	def __eq__(self, other):
		if not isinstance(other, Mention):
			return False
		return (self.resource_type, self.id, self._has_nick) == (other.resource_type, other.id, other._has_nick)

	def __hash__(self):
		return hash((self.resource_type, self.id, self._has_nick))


class MentionMatch:
	"""
	Holds information on the position of a Mention found in a call to find_mentions().

	pos - has the start index (inclusive) and end index (exclusive) of where in the search string the match was found.
	start - the start index (inclusive) of where in the search string the match was found.
	end - the end index (exclusive) of where in the search string the match was found.

	This makes it such that message_text[start:end] is valid.
	"""
	def __init__(self, mention: Mention, start_index: int, end_index: int):
		self.mention = mention
		self.pos = (start_index, end_index)

	@property
	def end(self) -> int:
		return self.pos[1]

	@property
	def start(self) -> int:
		return self.pos[0]


class CustomEmoji(object):
	"""domain specific emoji info to abstract away discord.py"""

	# noinspection PyShadowingBuiltins
	def __init__(self, id: int, name: str, guild: Optional[int] = None):
		self.id: int = id
		self.guild: int = guild
		self.name: str = name


class Reaction(object):

	"""domain specific reaction info to abstract away discord.py access"""
	def __init__(
			self,
			emoji: Optional[Union[str, int]] = None,
			action: str = 'add',
			uid: int = 0,
			mid: int = 0,
			cid: int = 0,
			gid: int = 0
	):
		"""
		Create a new Reaction for use with Bot API functions. Most created by the masabot core will have info
		automatically pre-populated before plugins see them. If creating a Reaction for the Bot API, at minimum
		the emoji is required.

		In order to fully populate the Reaction with data such that all properties are valid, API calls must be made.
		This is accomplished by calling fetch() on the created Reaction, and passing in a discord.Client. This is done
		deliberately to make it difficult for a module to directly invoke API-calling methods. However, for most
		purposes that a module will have (finding reactions, setting them, reacting to messages), calling fetch is not
		required.

		In order to query whether fetch() has been called, use Reaction.cached. If True, fetch has been called at least
		once and all properties are valid.

		:param emoji: The emoji being reacted with. Can either be a string containing the unicode codepoints for the
		emoji, or the ID of a custom emoji.
		:param action: What action the Reaction is produced in response to. Must be 'add' or 'remove'. Not required if
		creating a Reaction in a module.
		:param uid: The ID of the user who did the action, if applicable.
		:param mid: The ID of the message that the reaction was on, if applicable.
		:param cid: The ID of the channel that the message referred to by mid is present in, if applicable.
		:param gid: The ID of the guild that the channel referred to by cid is present in, if applicable.
		"""
		self.user_id = uid
		"""The user who actually did the removal or add."""

		self.message_id = mid
		"""Message reaction was on."""

		self.channel_id = cid
		"""Channel where message is. Will be 0 if message is not in a guild channel."""

		self.guild_id = gid
		"""Guild where message is. Will be 0 if message is not in a guild channel."""

		if action.lower() != 'add' and action.lower() != 'remove':
			raise TypeError("action must be 'add' or 'remove', but was: {!r}".format(action))
		self.action = action
		"""Either 'add' or 'remove'."""

		self.cached: bool = False
		"""Whether a fetch has been run for the data. If it has, the Optional properties will return data again."""

		self._member: Optional[discord.Member] = None
		self._user: Optional[discord.User] = None
		self._source_message: Optional[discord.Message] = None
		self._custom_emoji: Optional[CustomEmoji] = None
		self._unicode_emoji: Optional[str] = None
		self._reactors: Optional[List[int]] = None

		if emoji is not None:
			if isinstance(emoji, str):
				self._unicode_emoji = emoji
			else:
				self._custom_emoji = CustomEmoji(id=emoji, name='')  # TODO: make name be optional in CustomEmoji

	def __str__(self):
		if self.is_custom:
			emoji_str = '(custom; ID:' + str(self.emoji) + ')'
		else:
			emoji_str = self.emoji

		if self.cached:
			reactors_str = str(self.reactors)
		else:
			reactors_str = '(None; not cached)'

		s = '<Reaction:'
		s += ' emoji={:s},'
		s += ' user_id={:d},'
		s += ' message_id={:d},'
		s += ' channel_id={:d},'
		s += ' guild_id={:d},'
		s += ' action={:s},'
		s += ' cached={:b},'
		s += ' reactors={:s}>'

		full = s.format(
			emoji_str,
			self.user_id,
			self.message_id,
			self.channel_id,
			self.guild_id,
			self.action,
			self.cached,
			reactors_str
		)

		return full

	def __repr__(self):
		s = 'Reaction({!r}, {!r}, {!r}, {!r}, {!r}, {!r})'
		return s.format(self.emoji, self.action.lower(), self.user_id, self.message_id, self.channel_id, self.guild_id)

	def custom_name(self) -> str:
		"""Return the name of the custom emoji. If not custom, returns ''."""
		if self.is_custom:
			return self._custom_emoji.name
		return ''

	def custom_guild(self) -> int:
		"""Return the guild ID of the custom emoji. If not custom, returns 0."""
		if self.is_custom:
			return self._custom_emoji.guild
		return 0

	@property
	def emoji_value(self) -> Optional[Union[discord.PartialEmoji, str]]:
		"""
		Return the value that must be given to discord to represent an emoji.
		"""
		if self.is_custom:
			if not self.cached:
				return None
			p = discord.PartialEmoji(name=self.custom_name(), id=self.emoji)
			return p
		else:
			return self.emoji

	@property
	def is_in_guild(self) -> bool:
		"""
		Return whether the reaction is from a guild channel. If not, guild_id and channel_id will be zeroed and invalid.
		"""
		return self.guild_id is not None

	@property
	def member(self) -> Optional[discord.Member]:
		"""
		Get the guild member who did the reaction. Does not necessarily require cached to be true to return
		valid value. If cached is True, this will be non-None as long as the reaction is in a guild. If cached
		is false, this will be non-None only if the reaction is in a guild and the reaction is an add as per
		the discord.py API docs.
		"""
		return self._member

	@property
	def user(self) -> Optional[discord.User]:
		"""
		Get the guild member who did the reaction. Does not necessarily require cached to be true to return
		valid value. If cached is True, this is guaranteed to be non-None.
		"""
		return self._user

	@property
	def reactors(self) -> Optional[List[int]]:
		"""
		Get the list of IDs of users who currently have added the same reaction to the same message. Will be None if
		cached is False; call fetch() at least once before this method to ensure that this is the case.

		As the call to get message info may come after the actual reaction event, this is not guaranteed to include
		self.user_id even if is_add is True.
		"""
		if not self.cached:
			return None
		return self._reactors

	@property
	def source_message(self) -> Optional[discord.Message]:
		"""Get the message that the reaction occured on. Only available if cached; run fetch() once to make cached True."""
		if self.cached:
			return self._source_message
		return None

	@property
	def is_usable(self) -> Optional[bool]:
		"""Whether the reaction can be used. Always True for unicode emoji, False if custom and not in the same server,
		or None if custom and not cached."""
		if not self.is_custom:
			return True

		if not self.cached:
			return None

		return self._custom_emoji.guild == self.guild_id

	@property
	def is_custom(self) -> bool:
		"""Whether it is a custom emoji."""
		return self._custom_emoji is not None

	@property
	def count(self) -> Optional[int]:
		"""Number of users who reacted with the same emoji. Will be None if not cached; run fetch() at least once to do
		so."""
		if not self.cached:
			return None
		return len(self._reactors)

	@property
	def is_add(self) -> bool:
		"""Return whether this reaction is an Add."""
		return self.action.lower() == 'add'

	@property
	def is_remove(self) -> bool:
		"""Return whether this reaction is a Removal."""
		return self.action.lower() == 'remove'

	@property
	def emoji(self):
		"""
		Return the emoji in the reaction event. If it is a custom emoji, this will be an
		int with the emoji ID. If it is a standard unicode emoji, this will be a str
		containing the emoji text.
		"""
		if self.is_custom:
			return self._custom_emoji.id
		else:
			return self._unicode_emoji

	async def fetch(self, client: discord.Client):
		"""
		Get all info from discord if not obtained yet and cache it. Will set cached to True after execution.
		If cached is already True, calling this method has no effect.
		"""
		if self.cached:
			return

		# get actual source message
		if self._source_message is None:
			if self.channel_id != 0:
				msg = await client.get_channel(self.channel_id).fetch_message(self.message_id)
				self._source_message = msg
			else:
				msg = await client.get_channel(self.user_id).fetch_message(self.message_id)
				self._source_message = msg

		# get reactors
		reactions = self._source_message.reactions
		target_reaction = None
		for rct in reactions:
			if rct.custom_emoji != self.is_custom:
				continue
			if rct.custom_emoji:
				if rct.emoji.id == self.emoji:
					target_reaction = rct
					break
			elif rct.emoji == self.emoji:
				target_reaction = rct
				break
		if target_reaction is not None:
			users = await target_reaction.users().flatten()
			self._reactors = list([u.id for u in users])

		# get emoji server ID
		if self.is_custom and self._custom_emoji.guild is None:
			emj = client.get_emoji(self._custom_emoji.id)
			self._custom_emoji.guild = emj.guild_id

		if self._member is None and self.is_in_guild:
			self._member = client.get_guild(self.guild_id).get_member(self.user_id)
		if self._user is None:
			self._user = client.get_user(self.user_id)

		self.cached = True

	@staticmethod
	def from_raw(r: discord.RawReactionActionEvent) -> 'Reaction':
		rct = Reaction()
		rct.message_id = r.message_id
		rct.user_id = r.user_id
		rct.channel_id = r.channel_id
		rct.guild_id = r.guild_id
		if r.event_type == 'REACTION_ADD':
			rct.action = 'add'
		elif r.event_type == 'REACTION_REMOVE':
			rct.action = 'remove'
		else:
			raise TypeError("cannot convert unknown-type of RawReactionActionEvent: " + str(rct.action))
		rct.cached = False

		rct._member = r.member

		# r.emoji is a discord.PartialEmoji
		if r.emoji.is_custom_emoji():
			# cant get server from raw event, need fetch for that.
			rct._custom_emoji = CustomEmoji(r.emoji.id, r.emoji.name)
		else:
			rct._unicode_emoji = r.emoji.name

		return rct

	@staticmethod
	async def from_discord(r: discord.Reaction, u: Optional[discord.User] = None, removal: bool = False) -> 'Reaction':
		rct = Reaction()
		rct.message_id = r.message.id
		rct._source_message = r.message
		rct.user_id = u.id
		rct._user = u

		if r.message.channel is not None:
			rct.channel_id = r.message.channel.id

		if r.message.guild is not None:
			rct.guild_id = r.message.guild.id
			rct._member = r.message.guild.get_member(u.id)

		if removal:
			rct.action = 'remove'
		else:
			rct.action = 'add'

		rct.cached = True

		# stuff that would normally be done in fetch
		users = await r.users().flatten()
		rct._reactors = list([u.id for u in users])

		if isinstance(r.emoji, discord.PartialEmoji):
			if r.emoji.is_unicode_emoji():
				rct._unicode_emoji = r.emoji.name
			else:
				rct._custom_emoji = CustomEmoji(r.emoji.id, r.emoji.name, rct.guild_id)
		elif isinstance(r.emoji, discord.Emoji):
			rct._custom_emoji = CustomEmoji(r.emoji.id, r.emoji.name, r.emoji.guild_id)
		else:
			# otherwise, it is a str
			rct._unicode_emoji = r.emoji

		return rct


def reaction_index(react: Union[discord.Reaction, discord.RawReactionActionEvent]):
	if isinstance(react, discord.RawReactionActionEvent):
		if react.emoji.is_custom_emoji():
			return react.emoji.id
		else:
			return react.emoji.name
	else:
		if isinstance(react.emoji, discord.PartialEmoji):
			return react.emoji.id
		elif isinstance(react.emoji, discord.Emoji):
			return react.emoji.id
		else:
			return react.emoji


def find_mentions(
		message_text: str,
		include_types: Optional[Union[Iterable[MentionType], MentionType]] = None,
		include_ids: Optional[Union[Iterable[int], int]] = None,
		limit: int = 0
) -> Sequence[MentionMatch]:
	"""
	Find the starting and ending position of all mentions within the message. With no other keyword arguments present,
	return all match locations found.
	:param message_text: The text to search for mentions in.
	:param include_types: If set to an iterable of types, only mentions who are of a type contained in the iterable will
	be returned. If set to a single type, only mentions of that type will be returned.
	:param include_ids: If set to an iterable of IDs, only mentions whose ID is contained in the iterable will be
	returned. If set to a single ID, only mentions of that ID will be returned.
	:param limit: If set to a positive value, stops parsing for mentions after limit mentions that match the conditions
	of include_types and include_ids if they are specified. If neither are specified, stops parsing after limit mentions
	are found.
	:return: A sequence of MentionMatch objects in the order that they were encountered.
	"""
	matches = list()
	for left_idx, ch in enumerate(message_text):
		if left_idx + 1 >= len(message_text):
			# don't check on last character because then we can always assume that we have idx+1 later on in loop, and
			# it will never be a match if we are on the last char.
			continue
		if ch == '<':
			right_idx = message_text.find('>', left_idx+1)
			if right_idx == -1:
				# no more mentions are possible
				break
			try:
				men = parse_mention(message_text[left_idx:right_idx+1])
			except BotSyntaxError:
				# not a valid match; discard this left_index
				continue
			else:
				if include_ids is not None:
					if isinstance(include_ids, int):
						include_ids = [include_ids]
					if men.id not in include_ids:
						# valid match, but not an included ID; discard this left_index
						continue
				if include_types is not None:
					if isinstance(include_types, MentionType):
						include_types = [include_types]
					if men.resource_type not in include_types:
						# valid match, but not an included type; discard this left_index
						continue

				# everything else passed, if we are at this point, it is a valid mention
				matches.append(MentionMatch(men, left_idx, right_idx+1))

				# limit is only enforced if it is set to a positive number
				if limit > 0:
					if len(matches) >= limit:
						break
	return matches


def parse_ranged_int_or_percent(arg: str, range_min: int, range_max: int) -> int:
	if range_min > range_max:
		raise ValueError("range_min (" + str(range_min) + ") cannot be larger than range_max (" + str(range_max) + ")")

	percent = False
	original_arg = arg
	if arg.endswith('%'):
		percent = True
		arg = arg[:-1]

	if percent:
		try:
			per_arg = float(arg)
		except ValueError:
			raise ValueError(str(original_arg) + " is not a number percent!")
		if int(per_arg) == 100:
			# will break math, need to special case
			return range_max

		if not 0 <= per_arg <= 100:
			raise ValueError(str(original_arg) + " is not a valid percent between 0 and 100")
		scale = per_arg / 100.0
		range_amt = range_max - range_min
		add = int(math.floor(scale * (range_amt + 1)))
		return range_min + add
	else:
		try:
			int_arg = int(arg)
		except ValueError:
			raise ValueError(str(original_arg) + " is not an integer")
		if not range_min <= int_arg <= range_max:
			raise ValueError(str(arg) + " is not in range [" + str(range_min) + ", " + str(range_max) + "]")
		return int_arg


def parse_mention(mention_text: str, require_type: Optional[MentionType] = None) -> Mention:
	"""
	Parse a user identifier from a user mention.

	:type mention_text: str
	:param mention_text: The mention text.
	:param require_type: The type that the mention is expected to be; a BotSyntaxError will be raised if the parsed
	mention is not of that type.
	:rtype: Mention
	:return: The parsed mention.
	"""
	mention_text = mention_text.strip()
	if not mention_text.startswith('<') or not mention_text.endswith('>'):
		raise BotSyntaxError(repr(str(mention_text)) + " is not a mention")

	parsed = mention_text[1:-1]

	has_nick = False
	if parsed.startswith('#'):
		mention_type = MentionType.CHANNEL
		parsed = parsed[1:]
	elif parsed.startswith('@'):
		parsed = parsed[1:]
		if parsed.startswith('&'):
			parsed = parsed[1:]
			mention_type = MentionType.ROLE
		else:
			mention_type = MentionType.USER
			if parsed.startswith('!'):
				has_nick = True
				parsed = parsed[1:]
	else:
		raise BotSyntaxError(repr(str(mention_text)) + " is not a mention")
	if not parsed.isdigit():
		raise BotSyntaxError(repr(str(mention_text)) + " is not a mention")

	if require_type is not None and require_type != mention_type:
		raise BotSyntaxError(repr(str(mention_text)) + " is not a " + require_type.name.lower() + " mention")

	return Mention(mention_type, int(parsed), has_nick)


class DiscordPager(object):
	"""
	Arrange large messages into a series of pages, each of which is under the maximum size for a single Discord message.
	The messages can then all be sent sequentially.
	"""

	def __init__(self, continue_message=None):
		self._pages = []
		self._pages.append("")
		self._prepend_newline = False
		self._prepend_codeblock = False
		self._in_code_block = False
		self._continue_message = continue_message

	def add_line(self, line=""):
		self.add(line)
		self._prepend_newline = True

	def add(self, text):
		prefix = ""
		if self._prepend_newline:
			prefix += '\n'
		if self._prepend_codeblock:
			prefix += '```\n'
			self._in_code_block = True

		required_end_len = 0
		if self._in_code_block:
			required_end_len += len("\n```")

		if len(self._pages[-1]) + len(prefix + text) + required_end_len <= discord_char_limit:
			self._pages[-1] += prefix + text
		else:
			was_in_code_block = self._in_code_block
			if was_in_code_block:
				self._pages[-1] += '\n```'
			self._pages.append("")
			if self._continue_message is not None:
				self._pages[-1] += str(self._continue_message) + '\n'
			if was_in_code_block or self._prepend_codeblock:
				self._pages[-1] += '```\n'
				self._in_code_block = True
			self._pages[-1] += text

		self._prepend_codeblock = False
		self._prepend_newline = False

	def end_code_block(self):
		self._prepend_codeblock = False
		if not self._in_code_block:
			return
		self._prepend_newline = True
		self.add_line("```")
		self._in_code_block = False

	def start_code_block(self):
		self._prepend_newline = True
		self._prepend_codeblock = True
		self._in_code_block = False

	def get_pages(self):
		complete_pages = []
		for x in self._pages:
			if x != '':
				complete_pages.append(x)
		return complete_pages


# TODO: find out who is using this; convert them to SettingsStore usage
def str_to_int(str_value, min_allowed=None, max_allowed=None, name="value"):
	"""
	Convert a string value to an int. If the conversion fails, instead of a ValueError, a BotSyntaxError is
	generated.

	:type str_value: str
	:param str_value: The value to be converted.
	:type min_allowed: int
	:param min_allowed: The minimum value a number can be. If not set, no lower limit is enforced.
	:type max_allowed: int
	:param max_allowed: The maximum value a number can be. If not set, no upper limit is enforced.
	:type name: str
	:param name: What the value should be called in the resulting error, should conversion fail. If no name
	is given, no reference to a name is included in the resulting error.
	:rtype: int
	:return: The converted int.
	"""
	try:
		value = int(str_value)
	except ValueError:
		msg = "I need the " + name + " to be a whole number, and " + repr(str_value)
		msg += " isn't one at all!"
		raise BotSyntaxError(msg)

	if min_allowed is not None and value < min_allowed:
		msg = "The " + name + " just has to be at least " + str(min_allowed) + ", so " + str(value) + " is too small!"
		raise BotSyntaxError(msg)

	if max_allowed is not None and value > max_allowed:
		msg = "The " + name + " really can't be any bigger than " + str(max_allowed) + ", so " + str(value) + " is too big!"
		raise BotSyntaxError(msg)

	return value


def str_to_float(str_value, min_allowed=None, max_allowed=None, name="value"):
	"""
	Convert a string value to a float. If the conversion fails, instead of a ValueError, a BotSyntaxError is
	generated.

	:type str_value: str
	:param str_value: The value to be converted.
	:type min_allowed: float
	:param min_allowed: The minimum value a number can be. If not set, no lower limit is enforced.
	:type max_allowed: float
	:param max_allowed: The maximum value a number can be. If not set, no upper limit is enforced.
	:type name: str
	:param name: What the value should be called in the resulting error, should conversion fail. If no name
	is given, no reference to a name is included in the resulting error.
	:rtype: float
	:return: The converted float.
	"""
	try:
		value = float(str_value)
	except ValueError:
		msg = "I need the " + name + " to be a real number, and " + repr(str_value)
		msg += " isn't one at all!"
		raise BotSyntaxError(msg)

	if min_allowed is not None and value < min_allowed:
		msg = "The " + name + " just has to be at least " + str(min_allowed) + ", so " + str(value) + " is too small!"
		raise BotSyntaxError(msg)

	if max_allowed is not None and value > max_allowed:
		msg = "The " + name + " really can't be any bigger than " + str(max_allowed) + ", so " + str(value) + " is too big!"
		raise BotSyntaxError(msg)

	return value


class AttachmentData(object):
	"""
	A data file that is attached to an existing message. This file is hosted on Discord and can be accessed either via a
	direct link or a proxy link.
	"""

	def __init__(self, att):
		"""
		Create a new attachment.

		:type att: discord.Attachment
		:param att: The attachment.
		"""
		self.attachment = att

	def is_image(self):
		"""
		Check whether the attachment is an image file.

		:rtype bool:
		:return: Whether the attachment is an image file.
		"""
		if not self.has_dimensions():
			return False

		if self.attachment.filename.lower().endswith('.png'):
			return True
		elif self.attachment.filename.lower().endswith('.jpg'):
			return True
		elif self.attachment.filename.lower().endswith('.jpeg'):
			return True
		elif self.attachment.filename.lower().endswith('.gif'):
			return True
		elif self.attachment.filename.lower().endswith('.webp'):
			return True

		return False

	def is_video(self):
		"""
		Check whether the attachment is a video file.

		:rtype bool:
		:return: Whether the attachment is a video file.
		"""
		if not self.has_dimensions():
			return False

		if self.attachment.filename.lower().endswith('.mp4'):
			return True
		elif self.attachment.filename.lower().endswith('.webm'):
			return True

		return False

	def has_dimensions(self):
		"""
		Check whether this attachment has dimensions. This will be true only when the attachment is an image or a video.

		:rtype: bool
		:return: Whether the `height` and `width` are non-None values.
		"""
		return self.attachment.width is not None and self.attachment.height is not None

	def download(self):
		"""
		Downloads the attachment from the URL and returns the bytes that make it up.

		:rtype: bytes
		:return: The bytes that make up the attachment.
		"""

		parsed_url = urllib.parse.urlparse(self.attachment.url)
		ssl = False
		if parsed_url.scheme.lower() == 'https':
			ssl = True

		agent = http.HttpAgent(parsed_url.netloc, response_payload='binary', ssl=ssl)
		_, data = agent.request('GET', parsed_url.path)
		return data


class MessageMetadata(object):
	"""
	Additional metadata attached to a message. Does not include the author or the channel.
	"""
	def __init__(self, attachments=None):
		"""
		Create a new metadata object.

		:type attachments: list[Attachment]
		:param attachments: The attachments on the message, if there are any.
		"""
		if attachments is None:
			attachments = []
		self.attachments = list(attachments)
		""":type : list[Attachment]"""

	def has_attachments(self):
		"""
		Check if the message has any attachments.

		:rtype: bool
		:return: Whether the message has attachments.
		"""
		return len(self.attachments) > 0

	@staticmethod
	def from_message(message):
		"""
		Create a new MessageMetadata by reading the properties in a discord Message.

		:type message: discord.Message
		:param message: The message to read the metadata from.

		:rtype: MessageMetadata
		:return: The metadata.
		"""

		attachments = []
		for att in message.attachments:
			a = AttachmentData(att)
			attachments.append(a)

		meta = MessageMetadata(attachments)
		return meta
