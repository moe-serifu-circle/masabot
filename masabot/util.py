from . import http
import urllib.parse
import enum
from typing import Optional, Sequence, Tuple, Iterable, Union


discord_char_limit = 2000


class BotSyntaxError(Exception):
	def __init__(self, message, context=None):
		super().__init__(message)
		self.context = context


class BotPermissionError(Exception):
	def __init__(self, context, command, module=None, message=None):
		if message is None:
			message = "Operation requires operator permission"
		self.author = context.author
		self.command = command
		self.module = module
		self.context = context
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
	def __init__(self, m_type: MentionType, id: int, has_nick: bool):
		self.resource_type = m_type
		self.id = id
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


def str_to_int(str_value, min=None, max=None, name="value"):
	"""
	Convert a string value to an int. If the conversion fails, instead of a ValueError, a BotSyntaxError is
	generated.

	:type str_value: str
	:param str_value: The value to be converted.
	:type min: int
	:param min: The minimum value a number can be. If not set, no lower limit is enforced.
	:type max: int
	:param max: The maximum value a number can be. If not set, no upper limit is enforced.
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

	if min is not None and value < min:
		msg = "The " + name + " just has to be at least " + str(min) + ", so " + str(value) + " is too small!"
		raise BotSyntaxError(msg)

	if max is not None and value > max:
		msg = "The " + name + " really can't be any bigger than " + str(max) + ", so " + str(value) + " is too big!"
		raise BotSyntaxError(msg)

	return value


def str_to_float(str_value, min=None, max=None, name="value"):
	"""
	Convert a string value to a float. If the conversion fails, instead of a ValueError, a BotSyntaxError is
	generated.

	:type str_value: str
	:param str_value: The value to be converted.
	:type min: float
	:param min: The minimum value a number can be. If not set, no lower limit is enforced.
	:type max: float
	:param max: The maximum value a number can be. If not set, no upper limit is enforced.
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

	if min is not None and value < min:
		msg = "The " + name + " just has to be at least " + str(min) + ", so " + str(value) + " is too small!"
		raise BotSyntaxError(msg)

	if max is not None and value > max:
		msg = "The " + name + " really can't be any bigger than " + str(max) + ", so " + str(value) + " is too big!"
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
