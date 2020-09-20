from typing import Dict, Sequence

from . import BotBehaviorModule, InvocationTrigger
from .. import util
from ..util import BotSyntaxError, BotModuleError
from ..bot import PluginAPI

import requests
import random
import logging
import re
import io
import asyncio

from PIL import Image, ImageFont, ImageDraw

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class AnimemeModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "Generates anime memes by assigning a random background to the given text. Type `animeme` followed"
		help_text += " by one or two sentences in quotes to generate a meme for them. Example: `animeme \"This meme\""
		help_text += " \"is awesome!\"`.\n\nOps are able to add new images to the system from by using the"
		help_text += " `animeme-add` command as a comment to an image upload. They can also use the"
		help_text += " `animeme-remove` command followed by the template ID to remove an image from the system."
		help_text += " In addition, the `animeme-info` command will tell how many template IDs there currently are, and"
		help_text += " you can see any current template by running `animeme-info` followed by the template ID!\n\n"
		help_text += "The `animeme-list` command will show a list of all template IDs that I'm currently using!\n\n"
		help_text += "The `animeme-layout` command shows the values of my text layout engine. Give the name of a"
		help_text += " parameter after the command and I'll tell what its value is! Oh, and ops can also set the value"
		help_text += " of a parameter by giving the new value after the name."

		super().__init__(
			name="animeme",
			desc="Generates anime memes",
			help_text=help_text,
			triggers=[
				InvocationTrigger('animeme'),
				InvocationTrigger('animeme-add'),
				InvocationTrigger('animeme-remove'),
				InvocationTrigger('animeme-info'),
				InvocationTrigger('animeme-layout'),
				InvocationTrigger('animeme-list')
			],
			resource_root=resource_root,
			has_state=True
		)

		self.template_ids = set()
		self._user = ""
		self._pass = ""
		self._last_new_template = -1
		self._template_digits = 6
		self._template_width = 640
		self._default_pen = Pen(60, 30, 'fonts/anton/anton-regular.ttf')
		self._default_pen.set_color(fg="white", bg="black")
		self._pens = {}
		""":type: Dict[int, Pen]"""
		self._dm_pen = self._default_pen.copy()

	def load_config(self, config):
		if 'username' not in config:
			raise BotModuleError("Required key 'username' missing from 'anime' module config")
		if 'password' not in config:
			raise BotModuleError("Required key 'password' missing from 'anime' module config")
		self._user = config['username']
		self._pass = config['password']

	def set_global_state(self, state):
		if 'template-ids' in state:
			self.template_ids = set(state['template-ids'])
		if 'last-added' in state:
			self._last_new_template = state['last-added']
		if 'template-width' in state:
			self._template_width = state['template-width']

	def set_state(self, server: int, state: Dict):
		self._pens[server] = self._default_pen.copy()
		if 'font-layout' in state:
			self._pens[server].set_from_state_dict(state['font-layout'])

	def get_state(self, server: int) -> Dict:
		if server not in self._pens:
			return {
				'font-layout': self._default_pen.get_state_dict()
			}
		return {
			'font-layout': self._pens[server].get_state_dict()
		}

	def get_global_state(self):
		new_state = {
			'template-ids': list(self.template_ids),
			'last-added': self._last_new_template,
			'template-width': self._template_width,
		}
		return new_state

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == "animeme":
			await self.generate_animeme(bot, args)
		elif command == "animeme-add":
			await self.add_animeme(bot, metadata, args)
		elif command == "animeme-remove":
			await self.remove_animeme(bot, args)
		elif command == "animeme-info":
			t_id = None
			if len(args) > 0:
				t_id = self._validate_template_id(args[0])
			await self.get_animeme_info(bot, t_id)
		elif command == 'animeme-layout':
			await self.set_or_get_layout_param(bot, args)
		elif command == 'animeme-list':
			await self.list_animemes(bot)

	async def list_animemes(self, bot: PluginAPI):
		pager = util.DiscordPager("_(template list, continued)_")
		pager.add("Sure! Here's the complete list of all animeme templates I'm using. ")
		pager.add_line("You can use `animeme-info` followed by the id of a template to see a picture of it!")
		pager.start_code_block()
		for t_id in self.template_ids:
			pager.add_line(str(t_id).zfill(self._template_digits))
		pager.end_code_block()

		pages = pager.get_pages()
		for p in pages:
			await bot.reply(p)

	async def set_or_get_layout_param(self, bot: PluginAPI, args):
		layout_params = ['kerning', 'template-width', 'spacing', 'border', 'minfont', 'maxfont']
		if len(args) < 1:
			msg = "I need to know what layout parameter you want to set or get, it can be any one of these: "
			msg += ','.join('`' + x + '`' for x in layout_params) + '.'
			raise BotSyntaxError(msg)

		param = args[0]

		if param not in layout_params:
			msg = "That's not a valid layout parameter! It has to be one of these: "
			msg += ','.join('`' + x + '`' for x in layout_params) + ', okay?'
			raise BotSyntaxError(msg)

		if len(args) > 1:
			await self.set_layout_param(bot, param, args[1])
		else:
			await self.get_layout_param(bot, param)

	async def set_layout_param(self, bot: PluginAPI, param, value):
		if not bot.context.is_pm():
			server_id = await bot.require_server()
			await bot.require_op("animeme-layout " + str(param) + " <value>", self.name, server=server_id)
			if server_id not in self._pens:
				self._pens[server_id] = self._default_pen.copy()
			pen = self._pens[server_id]
		else:
			bot.require_master("animeme-layout " + str(param) + " <value>", self.name)
			pen = self._dm_pen

		if param == 'kerning':
			value = util.str_to_int(value, min=0, name="kerning")
			if pen.kerning == value:
				msg = "Haha, the kerning is already set to " + str(value) + ", so yay!"
			else:
				pen.kerning = value
				_log.debug("Set animeme kerning to " + str(value))
				msg = "Okay, I'll set the kerning to " + str(value) + " pixels!"
		elif param == 'template-width':
			value = util.str_to_int(value, min=1, name="template width")
			if self._template_width == value:
				msg = "Ah, well, the template width is already set to " + str(value) + ", so yay!"
			else:
				msg = "Ah, well, I can do that, but I'll have to resize all the templates I'm already using, and some"
				msg += " of them might lose quality! Also, it might take me a little bit. Are you sure you want me to"
				msg += " do that?"
				if await bot.confirm(msg):
					self._template_width = value
					_log.debug("Set animeme template width to " + str(value))
					msg = "Okay, I've changed the width, but now I need to resize my images! I'll let you know as soon"
					msg += " as I'm done!"
					await bot.reply(msg)
					_log.debug("Resize started, " + str(len(self.template_ids)) + " to resize...")
					await self._resize_templates()
					_log.debug("Resize of templates completed")
					msg = "All done, " + bot.mention_user() + "! I resized all my templates!"
				else:
					msg = "Okay! I'll leave my templates alone, then."
		elif param == 'spacing':
			value = util.str_to_float(value, min=0, name="word spacing")
			if pen.word_spacing_factor == value:
				msg = "Mmm, the word spacing is already set to " + str(value) + "..."
			else:
				pen.word_spacing_factor = value
				_log.debug("Set animeme word spacing factor to " + str(value))
				msg = "Okay, I'll set the word spacing to " + str(value) + "x the width of a single space!"
		elif param == 'border':
			value = util.str_to_int(value, min=0, name="border width")
			if pen.border_width == value:
				msg = "Oh, the border width is already set to " + str(value) + "."
			else:
				pen.border_width = value
				_log.debug("Set animeme border width to " + str(value))
				msg = "Okay, I'll set the border width to " + str(value) + " pixels!"
		elif param == 'minfont':
			value = util.str_to_int(value, min=2, name="minimum font size")
			if pen.min_font_size == value:
				msg = "Oh, the minimum font size is already set to " + str(value) + "."
			else:
				pen.min_font_size = value
				_log.debug("Set animeme minimum font size to " + str(value))
				msg = "Okay, I'll set the minimum font size to " + str(value) + " points!"
		elif param == 'maxfont':
			value = util.str_to_int(value, min=2, name="maximum font size")
			if pen.max_font_size == value:
				msg = "Oh, the maximum font size is already set to " + str(value) + "."
			else:
				pen.max_font_size = value
				_log.debug("Set animeme maximum font size to " + str(value))
				msg = "Okay, I'll set the maximum font size to " + str(value) + " points!"
		else:
			raise BotSyntaxError("I don't know anything about the `" + param + "` layout parameter... what is that?")

		await bot.reply(msg)

	async def get_layout_param(self, bot: PluginAPI, param):
		if not bot.context.is_pm:
			server_id = await bot.require_server()
			if server_id not in self._pens:
				self._pens[server_id] = self._default_pen.copy()
			pen = self._pens[server_id]
		else:
			pen = self._dm_pen

		if param == 'kerning':
			msg = "Sure! I've got the kerning set to " + str(pen.kerning) + " pixels right now."
		elif param == 'template-width':
			msg = "Sure! I've got the template width set to " + str(self._template_width) + " pixels right now."
		elif param == 'spacing':
			msg = "Sure! I've got the word spacing set to " + str(pen.word_spacing_factor) + " times the width of"
			msg += " a regular space."
		elif param == 'border':
			msg = "Sure! I'm currently setting a " + str(pen.border_width) + " pixel border on the text."
		elif param == 'minfont':
			msg = "Sure! The minimum size of the font is set to " + str(pen.min_font_size) + " points."
		elif param == 'maxfont':
			msg = "Sure! The maximum size of the font is set to " + str(pen.max_font_size) + " points."
		else:
			raise BotSyntaxError("I don't know anything about the `" + param + "` layout parameter... what is that?")

		await bot.reply(msg)

	async def add_animeme(self, bot: PluginAPI, metadata, args):
		await bot.require_op("animeme-add", self.name)
		if not metadata.has_attachments() or not metadata.attachments[0].is_image():
			raise BotSyntaxError("I need to know the image you want me to add, but you didn't attach one!")

		new_template = False
		if len(args) < 1:
			new_template = True
			template_id = self._create_unused_template_id()
		else:
			template_id = self._validate_template_id(args[0])
			if template_id in self.template_ids:
				async with bot.typing():
					file = self._template_filename(template_id)
					with self.open_resource('templates/' + file) as res:
						msg = "Oh! But I already have this template for ID " + str(template_id) + ":"
						await bot.reply_with_file(res, file, msg)

				replace = await bot.confirm("Do you want to replace it with the new image?")
				if not replace:
					msg = "Okay! I'll keep using the old image!"
					await bot.reply(msg)
					return
				else:
					msg = "All right, you got it! I'll replace that image with the new one!"
					await bot.reply(msg)
			else:
				new_template = True

		async with bot.typing():
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

		await bot.reply("Okay! I'll start using that new template to generate animemes ^_^")

	async def remove_animeme(self, bot: PluginAPI, args):
		await bot.require_op("animeme-remove", self.name)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the template you want me to remove.")

		template_id = self._validate_template_id(args[0])

		if template_id in self.template_ids:
			async with bot.typing():
				file = self._template_filename(template_id)

				with self.open_resource('templates/' + file) as res:
					msg_text = "Oh, " + str(template_id) + ", huh? Let's see, that would be this template:"
					await bot.reply_with_file(res, file, msg_text)

			stop_using_it = await bot.confirm("Want me to stop using it?")
			if not stop_using_it:
				await bot.reply("You got it! I'll keep using it.")
			else:
				self.template_ids.remove(template_id)
				self.remove_resource('templates/' + file)
				_log.debug("Removed animeme template " + str(template_id))
				await bot.reply("Okay! I'll stop using that template in animemes.")
		else:
			await bot.reply("Mmm, all right, but I was already not using that template for animemes.")
		return

	async def get_animeme_info(self, bot: PluginAPI, t_id=None):
		if t_id is None:
			msg = "Sure! I've currently got " + str(len(self.template_ids)) + " images for use with animemes."
			await bot.reply(msg)
		else:
			if t_id not in self.template_ids:
				raise BotModuleError("I don't have a template with that ID!")
			msg = "Oh, sure! Here's template " + str(t_id).zfill(self._template_digits) + ":"
			file = self._template_filename(t_id)
			with self.open_resource('templates/' + file) as fp:
				await bot.reply_with_file(fp, file, msg)

	async def generate_animeme(self, bot: PluginAPI, args):
		if len(args) < 1:
			raise BotSyntaxError("I need at least one line of text to make a meme.")
		meme_line_1 = args[0].upper()
		if len(args) > 1:
			meme_line_2 = args[1].upper()
		else:
			meme_line_2 = ""

		if len(self.template_ids) < 1:
			msg = "Argh! I don't have any backgrounds assigned to this module yet! Assign some with `animeme-add`"
			msg += " first."
			raise BotModuleError(msg)

		async with bot.typing():
			template_id = random.sample(self.template_ids, 1)[0]

			_log.debug("Creating animeme for template ID " + str(template_id))

			padded_id = str(template_id).zfill(self._template_digits)
			im = Image.open(self.open_resource('templates/' + self._template_filename(template_id)))
			":type : Image.Image"

			if bot.context.is_pm:
				self._dm_pen.draw_meme_text(im, meme_line_1, meme_line_2)
			else:
				server_id = bot.get_guild().id
				if server_id not in self._pens:
					self._pens[server_id] = self._default_pen.copy()
				self._pens[server_id].draw_meme_text(im, meme_line_1, meme_line_2)

			buf = io.BytesIO()
			im.save(buf, format='PNG')
			buf.seek(0)

		await bot.reply_with_file(buf, str(template_id) + "-generated.png", "_(" + padded_id + ")_")

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

	async def _resize_templates(self):
		for template_id in self.template_ids:
			with self.open_resource('templates/' + self._template_filename(template_id)) as fp:
				data = fp.read()
			data = self._normalize_template(data)
			with self.open_resource('templates/' + self._template_filename(template_id), for_writing=True) as fp:
				fp.write(data)
				fp.flush()
			_log.debug("Resized animeme template " + str(template_id))
			await asyncio.sleep(0.1)

	def _normalize_template(self, template_data):
		with io.BytesIO(template_data) as buf:
			im = Image.open(buf).convert("RGB")
			""":type : Image.Image"""
			if im.width != self._template_width:
				ratio = self._template_width / float(im.width)
				new_height = round(im.height * ratio)
				if ratio > 1:
					resample_algo = Image.HAMMING
				else:
					resample_algo = Image.LANCZOS
				im = im.resize((self._template_width, new_height), resample_algo)

			with io.BytesIO() as out_buf:
				im.save(out_buf, format='PNG')
				out_buf.seek(0)
				all_data = out_buf.read()
		return all_data


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

	def __init__(self, max_size, min_size, default_font):
		"""
		Create a new one.
		"""
		self._image = None
		""":type : Image.Image"""
		self._ctx = None
		""":type : ImageDraw.ImageDraw"""
		self._fg_color = "black"
		self._bg_color = "white"
		self._pos_x = 0
		self._pos_y = 0
		self._right_bound = 0
		self._left_bound = 0
		self._top_bound = 0
		self._bottom_bound = 0
		self._default_font = default_font
		self._fonts = RangeMap(default_font)
		self.max_font_size = max_size
		self.min_font_size = min_size
		self.line_spacing = 2
		self.border_width = 1
		self.kerning = 2
		self.word_spacing_factor = 1.5

	def copy(self) -> 'Pen':
		state = self.get_state_dict()
		p = Pen(self.max_font_size, self.min_font_size, self._default_font)
		p.set_from_state_dict(state)
		p._fg_color = self._fg_color
		p._bg_color = self._bg_color
		return p

	# noinspection PyMethodMayBeStatic
	def draw_meme_text(self, im, upper, lower):
		self.set_image(im)
		self.draw_top_aligned_text(upper)
		if lower is not None and lower != '':
			self.draw_bottom_aligned_text(lower)

	def set_from_state_dict(self, state):
		self.border_width = state.get('border-width', self.border_width)
		self.kerning = state.get('kerning', self.kerning)
		self.word_spacing_factor = state.get('spacing-factor', self.word_spacing_factor)
		self.min_font_size = state.get('min-font-size', self.min_font_size)
		self.max_font_size = state.get('max-font-size', self.max_font_size)

	def get_state_dict(self):
		d = {
			'border-width': self.border_width,
			'kerning': self.kerning,
			'spacing-factor': self.word_spacing_factor,
			'min-font-size': self.min_font_size,
			'max-font-size': self.max_font_size
		}
		return d

	def set_image(self, im):
		self._image = im
		self._ctx = ImageDraw.Draw(im)
		self._right_bound = im.width - 1
		self._bottom_bound = im.height - 1

	def set_color(self, fg=None, bg=None):
		if fg is not None:
			self._fg_color = fg
		if bg is not None:
			self._bg_color = bg

	def get_color(self):
		"""
		Return a tuple containing foreground and background colors.
		:rtype: (Any, Any)
		:return: The tuple
		"""
		return self._fg_color, self._bg_color

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
		max_width = (self._right_bound - self._left_bound + 1) - (4 * self.border_width)
		lines, f_size = self._wrap_text(text, max_width)

		true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
		line_height = true_line_height + self.line_spacing
		line_num = 0
		for line in lines:
			line_width = self._get_render_width(line, f_size)
			offset_x = round((max_width - line_width) / 2)
			offset_y = round(self.line_spacing / 2)
			y = self._top_bound + (line_num * line_height) + offset_y
			x = offset_x
			self._draw_text(x, y, line, f_size)
			line_num += 1

	def draw_bottom_aligned_text(self, text):
		max_width = (self._right_bound - self._left_bound + 1) - (4 * self.border_width)
		lines, f_size = self._wrap_text(text, max_width)

		true_line_height = ImageFont.truetype(self._fonts.get(ord('A')), f_size).getsize('Ag')[1]
		line_height = true_line_height + self.line_spacing
		line_num = 0
		for line in lines:
			line_width = self._get_render_width(line, f_size)
			offset_x = round((max_width - line_width) / 2)
			offset_y = round(self.line_spacing / 2)
			y = self._bottom_bound - (line_height * (len(lines) - line_num)) + offset_y
			x = offset_x
			self._draw_text(x, y, line, f_size)
			line_num += 1

	def _draw_text(self, x, y, text, size):
		cur_x = x
		cur_y = y
		first_char = False
		for ch in text:
			if first_char:
				first_char = False
			else:
				cur_x += self.kerning * self.font_size_ratio(size)

			f = ImageFont.truetype(self._fonts.get(ord(ch)), size=size)
			b = self.border_width * self.font_size_ratio(size)
			if 0 < b < 1:
				b = 1

			ch_width = f.getsize(ch)[0]

			if ch != ' ':
				self._ctx.text((cur_x - b, cur_y - b), ch, font=f, fill=self._bg_color)
				self._ctx.text((cur_x + b, cur_y - b), ch, font=f, fill=self._bg_color)
				self._ctx.text((cur_x - b, cur_y + b), ch, font=f, fill=self._bg_color)
				self._ctx.text((cur_x + b, cur_y + b), ch, font=f, fill=self._bg_color)

				self._ctx.text((cur_x, cur_y), ch, font=f, fill=self._fg_color)
			else:
				ch_width *= self.word_spacing_factor

			cur_x += ch_width

	def _wrap_text(self, text, width):
		if len(text) == 0:
			return [""]

		# first try to fit the whole thing on one line:
		fit_text, more_text_remains, remaining, f_size = self._fit_to_line(
			text, width, self.max_font_size, self.min_font_size
		)

		while len(fit_text) == 0 and len(text) != 0:
			# uh-oh, looks like the line is too big to fit on the line! so modify the text and start subdividing the
			# first word until it works
			first_word_end = text.find(' ')
			if first_word_end == -1:
				first_word_end = len(text)
			split_idx = first_word_end // 2
			text = text[:split_idx] + '- -' + text[split_idx:]

			fit_text, more_text_remains, remaining, f_size = self._fit_to_line(
				text, width, self.max_font_size, self.min_font_size
			)

		lines = [fit_text]
		# then it didn't fit, so repeat for all remaining lines
		while more_text_remains:
			size = self.min_font_size
			fit_text, more_text_remains, remaining, f_size = self._fit_to_line(remaining, width, size, size)

			while len(fit_text) == 0 and more_text_remains:
				# uh-oh, looks like the line is too big to fit on the line! so modify the text and start subdividing the
				# first word until it works
				first_word_end = remaining.find(' ')
				if first_word_end == -1:
					first_word_end = len(remaining)
				split_idx = first_word_end // 2
				remaining = remaining[:split_idx] + '- -' + remaining[split_idx:]

				fit_text, more_text_remains, remaining, f_size = self._fit_to_line(remaining, width, size, size)

			lines.append(fit_text)

		return lines, f_size

	def _fit_to_line(self, text, max_width, max_font_size, min_font_size):
		"""
		Fits the given text to a line. Breaks words too large to fit on to the next line.
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
		working_text = text
		for font_size in range(max_font_size, min_font_size - 1, -1):
			line_so_far = ""
			working_text = text
			length_so_far = 0
			space_chars = 0
			more_lines = False
			first_word = True
			while True:
				word_end = self._find_next_break(working_text)
				next_word = working_text[:word_end]
				next_word_len = self._get_render_width((' ' * space_chars) + next_word, font_size)
				if first_word:
					first_word = False
				else:
					next_word_len += self.kerning * self.font_size_ratio(font_size)
				if length_so_far + next_word_len <= max_width:
					line_so_far += (' ' * space_chars) + next_word
					length_so_far += next_word_len
				else:
					more_lines = True
					break

				# find next space for adding to next word
				space_chars = 0
				while word_end < len(working_text) and self._is_space(working_text[word_end]):
					space_chars += 1
					word_end += 1

				if word_end != len(working_text):
					working_text = working_text[word_end:]
				else:
					break
			if not more_lines:
				break
		return line_so_far, more_lines, working_text if more_lines else '', font_size

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

	# noinspection PyMethodMayBeStatic
	def _is_space(self, ch):
		import unicodedata
		cat = unicodedata.category(ch)
		return cat.startswith('Z') or ch == '\n' or ch == '\t' or ch == '\r'

	def _get_render_width(self, word, font_size):
		total_size = 0
		first_char = True
		for ch in word:
			if first_char:
				first_char = False
			else:
				total_size += self.kerning * self.font_size_ratio(font_size)
			font_name = self._fonts.get(ord(ch))
			f = ImageFont.truetype(font_name, font_size)
			ch_width = f.getsize(ch)[0]

			if ch == ' ':
				ch_width *= self.word_spacing_factor

			total_size += ch_width
		return total_size

	def font_size_ratio(self, cur):
		return cur / float(self.max_font_size)
