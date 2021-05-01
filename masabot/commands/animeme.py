from typing import Any

from . import BotBehaviorModule, InvocationTrigger
from .. import util, settings, pen
from ..util import BotSyntaxError, BotModuleError
from ..bot import PluginAPI

# noinspection PyPackageRequirements
import requests
import random
import logging
import re
import io
import asyncio

# noinspection PyPackageRequirements
from PIL import Image

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
		help_text += "__Settings__\n"
		help_text += "Use the `settings animeme` command to set these:\n"
		help_text += " * `kerning` - The number of pixes between letters.\n"
		help_text += " * `spacing` - The amount of space between words, measured as this value multiplied by the width"
		help_text += " of a space.\n"
		help_text += " * `text-border` - Width in pixels of the border around text.\n"
		help_text += " * `min-font` - The minimum size in points that text can be drawn at to avoid going to a new line.\n"
		help_text += " * `max-font` - The maximum size in points that text can be drawn at.\n"
		help_text += " * `template-width` - The width of the templates used to generate animemes. This is a global value"
		help_text += " that is used by all servers I'm connected to."

		width_prompt = "Ah, well, I can do that, but I'll have to resize all the templates"
		width_prompt += " I'm already using, and some of them might lose quality! Also, it"
		width_prompt += " might take me a little bit. Are you sure you want me to do that?"

		super().__init__(
			name="animeme",
			desc="Generates anime memes",
			help_text=help_text,
			triggers=[
				InvocationTrigger('animeme'),
				InvocationTrigger('animeme-add'),
				InvocationTrigger('animeme-remove'),
				InvocationTrigger('animeme-info'),
				InvocationTrigger('animeme-list')
			],
			resource_root=resource_root,
			save_state_on_trigger=True,
			settings=[
				settings.Key(settings.key_type_int_range(min=0), 'kerning', default=2),
				settings.Key(settings.key_type_float_range(min=0.0), 'spacing', default=1.5),
				settings.Key(settings.key_type_int_range(min=0), 'text-border', default=1),
				settings.Key(settings.key_type_int_range(min=2), 'min-font', default=30),
				settings.Key(settings.key_type_int_range(min=2), 'max-font', default=60),
			],
			global_settings=[
				settings.Key(
					settings.key_type_int_range(min=1),
					'template-width',
					default=640,
					prompt_before=width_prompt,
					call_module_on_alter=True
				),
			]
		)

		self.template_ids = set()
		self._user = ""
		self._pass = ""
		self._last_new_template = -1
		self._template_digits = 6

	# noinspection PyMethodMayBeStatic
	async def create_pen(self, bot: PluginAPI) -> pen.Pen:
		kerning = await bot.get_setting('kerning')
		spacing = await bot.get_setting('spacing')
		border = await bot.get_setting('text-border')
		min_font = await bot.get_setting('min-font')
		max_font = await bot.get_setting('max-font')

		p = pen.Pen(max_font, min_font, 'fonts/anton/anton-regular.ttf')
		p.set_color(fg="white", bg="black")
		p.border_width = border
		p.word_spacing_factor = spacing
		p.kerning = kerning
		return p

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

	def get_global_state(self):
		new_state = {
			'template-ids': list(self.template_ids),
			'last-added': self._last_new_template,
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

	async def on_setting_change(self, bot: PluginAPI, key: str, old_value: Any, new_value: Any):
		if key != 'template-width':
			return

		msg = "Okay, I've changed the width, but now I need to resize my images! I'll let you know as soon"
		msg += " as I'm done!"
		await bot.reply(msg)
		_log.debug(util.add_context(bot.context, "Resize started, {:d} to resize...", len(self.template_ids)))
		await self._resize_templates(new_value)
		_log.debug(util.add_context(bot.context, "Resize of templates completed"))
		msg = "All done, " + bot.mention_user() + "! I resized all my templates!"
		await bot.reply(msg)

	async def add_animeme(self, bot: PluginAPI, metadata, args):
		await bot.require_op("animeme-add")
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
			template_width = await bot.get_setting('template-width')
			template_data = metadata.attachments[0].download()
			template_data = self._normalize_template(template_width, template_data)

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
		await bot.require_op("animeme-remove")

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

			# noinspection PyShadowingNames
			pen = await self.create_pen(bot)
			pen.draw_meme_text(im, meme_line_1, meme_line_2)

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

		filename = m.group(1)[m.group(1).index('/') + 1:]
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

	async def _resize_templates(self, width: int):
		for template_id in self.template_ids:
			with self.open_resource('templates/' + self._template_filename(template_id)) as fp:
				data = fp.read()
			data = self._normalize_template(width, data)
			with self.open_resource('templates/' + self._template_filename(template_id), for_writing=True) as fp:
				fp.write(data)
				fp.flush()
			_log.debug("Resized animeme template " + str(template_id))
			await asyncio.sleep(0.1)

	# noinspection PyMethodMayBeStatic
	def _normalize_template(self, width: int, template_data):
		with io.BytesIO(template_data) as buf:
			im = Image.open(buf).convert("RGB")
			""":type : Image.Image"""
			if im.width != width:
				ratio = width / float(im.width)
				new_height = round(im.height * ratio)
				if ratio > 1:
					resample_algo = Image.HAMMING
				else:
					resample_algo = Image.LANCZOS
				im = im.resize((width, new_height), resample_algo)

			with io.BytesIO() as out_buf:
				im.save(out_buf, format='PNG')
				out_buf.seek(0)
				all_data = out_buf.read()
		return all_data


BOT_MODULE_CLASS = AnimemeModule
