from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError, BotModuleError

import requests
import random
import logging
import re
import io

from PIL import Image, ImageFont, ImageDraw

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class AnimemeModule(BotBehaviorModule):

	def __init__(self, bot_api, resource_root):
		help_text = "Generates anime memes by assigning a random background to the given text. Type `animeme` followed"
		help_text += " by one or two sentences in quotes to generate a meme for them. Example: `animeme \"This meme\""
		help_text += " \"is awesome!\"`.\n\nOps are able to add new images to the system from by using the"
		help_text += " `animeme-add` command, followed by the ImageFlip ID of the image to add. They can also use the"
		help_text += " `animeme-remove` command followed by the ImageFlip ID to remove an image from the system."
		help_text += " In addition, the `animeme-info` command will tell how many template IDs there currently are."

		super().__init__(
			bot_api,
			name="animeme",
			desc="Generates anime memes",
			help_text=help_text,
			triggers=[
				InvocationTrigger('animeme'),
				InvocationTrigger('animeme-add'),
				InvocationTrigger('animeme-remove'),
				InvocationTrigger('animeme-info')
			],
			resource_root=resource_root,
			has_state=True
		)

		self.template_ids = set()
		self._user = ""
		self._pass = ""
		self._last_new_template = -1
		self._template_digits = 6
		self._desired_width = 640

	def load_config(self, config):
		if 'username' not in config:
			raise BotModuleError("Required key 'username' missing from 'anime' module config")
		if 'password' not in config:
			raise BotModuleError("Required key 'password' missing from 'anime' module config")
		self._user = config['username']
		self._pass = config['password']

	def set_state(self, state):
		if 'image-ids' in state:
			self.template_ids = set(state['image-ids'])
		if 'last-added' in state:
			self._last_new_template = state['last-added']

	def get_state(self):
		new_state = {
			'image-ids': list(self.template_ids),
			'last-added': self._last_new_template
		}
		return new_state

	async def on_invocation(self, context, metadata, command, *args):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type command: str
		:type args: str
		"""
		if command == "animeme":
			await self.generate_animeme(context, args)
		elif command == "animeme-add":
			await self.add_animeme(context, metadata, args)
		elif command == "animeme-remove":
			await self.remove_animeme(context, args)
		elif command == "animeme-info":
			await self.get_animeme_info(context)

	async def add_animeme(self, context, metadata, args):
		self.bot_api.require_op(context, "animeme-add", self.name)
		if not metadata.has_attachments() or not metadata.attachments[0].is_image():
			raise BotSyntaxError("I need to know the image you want me to add, but you didn't attach one!")

		new_template = False
		if len(args) < 1:
			new_template = True
			template_id = self._create_unused_template_id()
		else:
			template_id = self._validate_template_id(args[0])
			if template_id in self.template_ids:
				await self.bot_api.reply_typing(context)
				file = self._template_filename(template_id)
				with self.open_resource('templates/' + file) as res:
					msg = "Oh! But I already have this template for ID " + str(template_id) + ":"
					await self.bot_api.reply_with_file(context, res, file, msg)

				replace = await self.bot_api.confirm(context, "Do you want to replace it with the new image?")
				if not replace:
					msg = "Okay! I'll keep using the old image!"
					await self.bot_api.reply(context, msg)
					return
				else:
					msg = "All right, you got it! I'll replace that image with the new one!"
					await self.bot_api.reply(context, msg)
			else:
				new_template = True

		await self.bot_api.reply_typing(context)
		template_data = metadata.attachments[0].download()

		template_data = self._normalize_template(template_data)

		res_fp = self.open_resource('templates/' + self._template_filename(template_id), for_writing=True)
		res_fp.write(template_data)
		res_fp.flush()
		res_fp.close()

		self.template_ids.add(template_id)

		if new_template:
			self._last_new_template = template_id

		_log.debug("Added animeme template " + str(template_id))
		await self.bot_api.reply(context, "Okay! I'll start using that new template to generate animemes ^_^")

	async def remove_animeme(self, context, args):
		self.bot_api.require_op(context, "animeme-remove", self.name)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the template you want me to remove.")

		template_id = self._validate_template_id(args[0])

		await self.bot_api.reply_typing(context)
		if template_id in self.template_ids:
			file = self._template_filename(template_id)

			with self.open_resource('templates/' + file) as res:
				msg_text = "Oh, " + str(template_id) + ", huh? Let's see, that would be this template:"
				await self.bot_api.reply_with_file(context, res, file, msg_text)

			stop_using_it = await self.bot_api.confirm(context, "Want me to stop using it?")
			if not stop_using_it:
				await self.bot_api.reply(context, "You got it! I'll keep using it.")
			else:
				self.template_ids.remove(template_id)
				self.remove_resource('templates/' + file)
				_log.debug("Removed animeme template " + str(template_id))
				await self.bot_api.reply(context, "Okay! I'll stop using that template in animemes.")
		else:
			await self.bot_api.reply(context, "Mmm, all right, but I was already not using that template for animemes.")
		return

	async def get_animeme_info(self, context):
		msg = "Sure! I've currently got " + str(len(self.template_ids)) + " images for use with animemes."
		await self.bot_api.reply(context, msg)

	async def generate_animeme(self, context, args):
		if len(args) < 1:
			raise BotSyntaxError("I need at least one line of text to make a meme.")
		meme_line_1 = args[0]
		if len(args) > 1:
			meme_line_2 = args[1]
		else:
			meme_line_2 = ""

		if len(self.template_ids) < 1:
			msg = "Argh! I don't have any backgrounds assigned to this module yet! Assign some with `animeme-add`"
			msg += " first."
			raise BotModuleError(msg)

		await self.bot_api.reply_typing(context)
		template_id = random.sample(self.template_ids, 1)[0]

		_log.debug("Creating animeme for template ID " + str(template_id))

		im = Image.open(self.open_resource('templates/' + self._template_filename(template_id)))
		":type : Image.Image"

		self._draw_meme_text(im, meme_line_1, meme_line_2)

		buf = io.BytesIO()
		im.save(buf, format='PNG')
		buf.seek(0)

		await self.bot_api.reply_with_file(context, buf, template_id + "-generated.png")

	# noinspection PyMethodMayBeStatic
	async def get_template_preview(self, template_id):
		response = requests.get("https://imgflip.com/memetemplate/" + str(template_id))

		html = response.text
		m = re.search(r'(i.imgflip.com/[^.]+\.\w+)"', html, re.DOTALL)
		if not m:
			raise BotSyntaxError("Not a valid template ID")

		filename = m.group(1)[m.group(1).index('/')+1:]
		response = requests.get("https://" + m.group(1))

		return response.content, filename

	def _create_unused_template_id(self):
		max_templates = 10 ** self._template_digits
		if len(self.template_ids) >= max_templates:
			msg = "I already have " + str(max_templates) + " templates, and I can't handle any more! But you can"
			msg += " replace old ones if you want by giving me the ID of template to replace."
			raise BotModuleError(msg)

		existing = frozenset(self.list_resources('templates/*'))

		temp_id = self._last_new_template + 1

		while ('templates/' + self._template_filename(temp_id)) in existing:
			if temp_id == self._last_new_template:
				raise BotModuleError("I couldn't find any free slots for a new template filename!")

			temp_id += 1
			if temp_id >= max_templates:
				temp_id = 0

		return temp_id

	def _template_filename(self, temp_id):
		return str(temp_id).zfill(self._template_digits) + '.png'

	def _validate_template_id(self, temp_id):
		try:
			temp_id = int(temp_id)
		except ValueError:
			msg = "Template IDs should be a bunch of numbers, but " + repr(str(temp_id)) + " has some not-numbers in"
			msg += " it!"
			raise BotSyntaxError(msg)
		if temp_id < 0:
			raise BotSyntaxError("Template IDs have to be at least 0.")
		if temp_id >= 10 ** self._template_digits:
			raise BotSyntaxError("Template IDs can't be more than " + str(10 ** self._template_digits - 1) + ".")

		return temp_id

	def _normalize_template(self, template_data):
		with io.BytesIO(template_data) as buf:
			im = Image.open(buf).convert("RGB")
			""":type : Image.Image"""
			if im.width != self._desired_width:
				ratio = self._desired_width / float(im.width)
				new_height = round(im.height * ratio)
				if ratio > 1:
					resample_algo = Image.HAMMING
				else:
					resample_algo = Image.LANCZOS
				im = im.resize((self._desired_width, new_height), resample_algo)

			with io.BytesIO() as out_buf:
				im.save(out_buf, format='PNG')
				out_buf.seek(0)
				all_data = out_buf.read()
		return all_data

	def _draw_meme_text(self, im, upper, lower):
		pen = Pen(im, 30, 15)
		pen.set_color(fg="white", bg="black")
		pen.draw_top_aligned_text(upper)
		if lower is not None and lower != '':
			pen.draw_bottom_aligned_text(lower)


BOT_MODULE_CLASS = AnimemeModule


class RangeMap(object):

	def __init__(self, default_value):
		self._default = default_value
		self._rules = []

	def add_rule(self, start, end, value):
		self._rules.insert(0, (start, end, value))

	def get(self, key):
		for r in self._rules:
			start, end, value = r
			if start <= key <= end:
				return value
		return self._default


class Pen(object):

	def __init__(self, im, max_size, min_size):
		"""
		Create a new one.
		:type im: Image.Image
		:param im:
		"""
		self._image = im
		self._ctx = ImageDraw.Draw(im)
		self._fg_color = "black"
		self._bg_color = "white"
		self._pos_x = 0
		self._pos_y = 0
		self._right_bound = im.width - 1
		self._left_bound = 0
		self._top_bound = 0
		self._bottom_bound = im.height - 1
		self._fonts = RangeMap('anton/anton-regular.ttf')
		self._max_size = max_size
		self._min_size = min_size
		self._line_spacing = 2
		self._border_width = 1

	def set_color(self, fg=None, bg=None):
		if fg is not None:
			self._fg_color = fg
		if bg is not None:
			self._bg_color = bg

	def set_font_mapping(self, path, codepoint_start, codepoint_end):
		self._fonts.add_rule(codepoint_start, codepoint_end, path)

	def set_right_bound(self, bound):
		self._right_bound = bound

	def set_bottom_bound(self, bound):
		self._bottom_bound = bound

	def set_position(self, x=None, y=None):
		if x is not None:
			self._pos_x = x
		if y is not None:
			self._pos_y = y

	def draw_top_aligned_text(self, text):
		max_width = self._right_bound - self._left_bound + 1
		lines, f_size = self._wrap_text(text, max_width)

		true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
		line_height = true_line_height + self._line_spacing
		line_num = 0
		for line in lines:
			line_width = self._get_render_width(line, f_size)
			offset_x = round((max_width - line_width) / 2)
			offset_y = round(self._line_spacing / 2)
			y = self._top_bound + (line_num * line_height) + offset_y
			x = offset_x
			self._draw_text(x, y, text, f_size)
			line_num += 1

	def draw_bottom_aligned_text(self, text):
		max_width = self._right_bound - self._left_bound + 1
		lines, f_size = self._wrap_text(text, max_width)

		true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
		line_height = true_line_height + self._line_spacing
		line_num = 0
		for line in lines:
			line_width = self._get_render_width(line, f_size)
			offset_x = round((max_width - line_width) / 2)
			offset_y = round(self._line_spacing / 2)
			y = self._bottom_bound - (line_height * (len(lines) - line_num)) + offset_y
			x = offset_x
			self._draw_text(x, y, text, f_size)
			line_num += 1

	def _draw_text(self, x, y, text, size):
		cur_x = x
		cur_y = y
		for ch in text:
			f = ImageFont.truetype(self._fonts.get(ord(ch)), size=size)
			b = self._border_width

			self._ctx.text((cur_x - b, cur_y - b), ch, font=f, fill=self._bg_color)
			self._ctx.text((cur_x + b, cur_y - b), ch, font=f, fill=self._bg_color)
			self._ctx.text((cur_x - b, cur_y + b), ch, font=f, fill=self._bg_color)
			self._ctx.text((cur_x + b, cur_y + b), ch, font=f, fill=self._bg_color)

			self._ctx.text((cur_x, cur_y), ch, font=f, fill=self._fg_color)
			delta = f.getsize(ch)[1]
			cur_x += delta

	def _wrap_text(self, text, width):
		# first try to fit the whole thing on one line:

		fit_text, more_text_remains, remaining, f_size = self._fit_to_line(text, width, self._max_size, self._min_size)

		lines = [fit_text]

		if more_text_remains:
			# then it didn't fit, so repeat for all remaining lines
			while more_text_remains:
				size = self._min_size
				fit_text, more_text_remains, remaining, f_size = self._fit_to_line(remaining, width, size, size)
				lines.append(fit_text)

		return lines, f_size

	def _fit_to_line(self, text, max_width, max_font_size, min_font_size):
		"""
		Fits the given text to a line.
		:param text: The text to fit.
		:param max_width: The maximum width of a line.
		:param max_font_size: The maximum size the font can be.
		:param min_font_size: The minimum size the font can be.

		:return: A tuple.
		The line, whether there is more text, the rest of the text, the font size of the final version.
		"""
		line_so_far = ''
		more_lines = False
		font_size = 0
		for font_size in range(max_font_size, min_font_size - 1, -1):
			line_so_far = ""
			length_so_far = 0
			space_chars = 0
			more_lines = False
			while True:
				word_end = self._find_next_break(text)
				next_word = text[:word_end]
				next_word_len = self._get_render_width((' ' * space_chars) + next_word, font_size)
				if length_so_far + next_word_len <= max_width:
					line_so_far += (' ' * space_chars) + next_word
					length_so_far += next_word_len
				else:
					more_lines = True
					break

				# find next space for adding to next word
				space_chars = 0
				while word_end < len(text) and self._is_space(text[word_end]):
					space_chars += 1
					word_end += 1

				if word_end != len(text):
					text = text[word_end:]
				else:
					break
			if not more_lines:
				break
		return line_so_far, more_lines, text if more_lines else '', font_size

	def _find_next_break(self, text):
		import unicodedata
		idx = -1
		for ch in text:
			idx += 1
			cat = unicodedata.category(ch)
			if cat == 'Lo':
				return idx + 1
			elif self._is_space(ch):
				return idx
		return len(text)

	def _is_space(self, ch):
		import unicodedata
		cat = unicodedata.category(ch)
		return cat.startswith('Z') or ch == '\n' or ch == '\t' or ch == '\r'

	def _get_render_width(self, word, font_size):
		total_size = 0
		for ch in word:
			font_name = self._fonts.get(ord(ch))
			f = ImageFont.truetype(font_name, font_size)
			total_size += f.getsize(ch)[0]
		return total_size