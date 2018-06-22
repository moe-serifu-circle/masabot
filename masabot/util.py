
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
	:rtype: str
	:return: The user ID.
	"""
	mention_text = mention_text.strip()
	if not mention_text.startswith('<@') or not mention_text.endswith('>'):
		raise BotSyntaxError(repr(str(mention_text)) + " is not a user mention")
	parsed = mention_text[2:-1]
	if parsed.startswith('!'):
		parsed = parsed[1:]
	if not parsed.isdigit():
		raise BotSyntaxError(repr(str(mention_text)) + " is not a user mention")

	return parsed


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


class Attachment(object):
	"""
	A data file that is attached to an existing message. This file is hosted on Discord and can be accessed either via a
	direct link or a proxy link.
	"""

	def __init__(self, att_id, filename, size, url, proxy_url, width=None, height=None):
		"""
		Create a new attachment.

		:type att_id: str
		:param att_id: The ID of the attachment.
		:type filename: str
		:param filename: The name of the file.
		:type size: int
		:param size: The size, in bytes, of the uploaded file.
		:type url: str
		:param url: The URL for accessing the file directly.
		:type proxy_url: str
		:param proxy_url: The URL for accessing the file via the Discord proxy. This is used for generating previews,
		but can be the same as the direct link when a preview is not generated.
		:type width: int
		:param width: The width of the uploaded file. Only used if the attachment is an image or movie.
		:type height: int
		:param height: The height of the uploaded file. Only used if the attachment is an image or movie.
		"""
		self.id = att_id
		self.filename = filename
		self.size = size
		self.url = url
		self.proxy_url = proxy_url
		self.width = width
		self.height = height

	def is_image(self):
		"""
		Check whether the attachment is an image file.

		:rtype bool:
		:return: Whether the attachment is an image file.
		"""
		if not self.has_dimensions():
			return False

		if self.filename.lower().endswith('.png'):
			return True
		elif self.filename.lower().endswith('.jpg'):
			return True
		elif self.filename.lower().endswith('.jpeg'):
			return True
		elif self.filename.lower().endswith('.gif'):
			return True
		elif self.filename.lower().endswith('.webp'):
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

		if self.filename.lower().endswith('.mp4'):
			return True
		elif self.filename.lower().endswith('.webm'):
			return True

		return False

	def has_dimensions(self):
		"""
		Check whether this attachment has dimensions. This will be true only when the attachment is an image or a video.

		:rtype: bool
		:return: Whether the `height` and `width` are non-None values.
		"""
		return self.width is not None and self.height is not None

	@staticmethod
	def from_dict(att_dict):
		"""
		Create a new Attachment by reading the properties in a dict that came from the discord.py API.

		:type att_dict: dict[str, Any]
		:param att_dict: The dictionary containing the attributes of the attachment.

		:rtype: Attachment
		:return: The new attachment.
		"""
		att_id = att_dict['att_id']
		filename = att_dict['filename']
		size = att_dict['size']
		url = att_dict['url']
		proxy_url = att_dict['proxy_url']
		w = att_dict.get('width', None)
		h = att_dict.get('height', None)
		return Attachment(att_id, filename, size, url, proxy_url, w, h)


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
		for att_dict in message.attachments:
			a = Attachment.from_dict(att_dict)
			attachments.append(a)

		meta = MessageMetadata(attachments)
		return meta
