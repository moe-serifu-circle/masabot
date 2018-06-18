
discord_char_limit = 2000


class BotSyntaxError(Exception):
	def __init__(self, message):
		super().__init__(message)


class BotPermissionError(Exception):
	def __init__(self, context, command, module=None, message=None):
		if message is None:
			message = "Operation requires operator permission"
		self.author = context.author
		self.command = command
		self.module = module
		super().__init__(message)


class BotModuleError(RuntimeError):
	def __init__(self, message):
		super().__init__(message)


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

	def __init__(self):
		self._pages = []
		self._pages.append("")
		self._prepend_newline = False
		self._prepend_codeblock = False
		self._in_code_block = False

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
