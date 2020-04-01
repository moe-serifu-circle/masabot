from . import http
import urllib.parse


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


def parse_user(mention_text):
	"""
	Parse a user identifier from a user mention.

	:type mention_text: str
	:param mention_text: The mention text.
	:rtype: str, bool
	:return: The user ID, and whether the user is a bot
	"""
	is_bot = False
	mention_text = mention_text.strip()
	if not mention_text.startswith('<@') or not mention_text.endswith('>'):
		raise BotSyntaxError(repr(str(mention_text)) + " is not a user mention")
	parsed = mention_text[2:-1]
	if parsed.startswith('!'):
		parsed = parsed[1:]
	if parsed.startswith('&'):
		parsed = parsed[1:]
		is_bot = True
	if not parsed.isdigit():
		raise BotSyntaxError(repr(str(mention_text)) + " is not a user mention")

	return int(parsed), is_bot


def parse_channel(mention_text):
	"""
	Parse a channel identifier from a channel mention.

	:type mention_text: str
	:param mention_text: The mention text.
	:rtype: str
	:return: The channel ID.
	"""
	mention_text = mention_text.strip()
	if not mention_text.startswith('<#') or not mention_text.endswith('>'):
		raise BotSyntaxError(repr(str(mention_text)) + " is not a channel mention")
	parsed = mention_text[2:-1]
	if not parsed.isdigit():
		raise BotSyntaxError(repr(str(mention_text)) + " is not a channel mention")

	return parsed


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
