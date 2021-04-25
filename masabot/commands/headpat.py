from typing import Any

from . import BotBehaviorModule, InvocationTrigger
from .. import util, settings, pen
from ..util import BotSyntaxError, BotModuleError
from ..bot import PluginAPI

# noinspection PyPackageRequirements

import random
import logging
import io
import asyncio

# noinspection PyPackageRequirements
from PIL import Image

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


headpat_messages = [
	"iiko, iiko~",
	"Everything will be okay~ *pats your head*",
	"Here, have a headpat!",
	"You deserve one of these!",
	"Ehehehe, let me pat your head!",
	"Here, you should have a headpat!",
	"_nade-nade, nade-nade~_",
	"Gooooooood cute!",
	"There, there!",
	"Please take this on your head, I hope it makes you happy! *pats you gently*"
]


class HeadpatModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "Summons emergency headpats when you really need them! Also, I think pretty much"
		help_text += " any time you want them counts as an emergency!\n\n"
		help_text += "Do `headpat` to receive a headpat, or do `headpat <member>` to have me give someone else a headpat!\n"
		help_text += "\n__Superop Commands:__\n\n"
		help_text += "* `headpat-add <X1> <Y1> <X2> <Y2> [id]` with an image and a message with x1 y1 x2 y2 of"
		help_text += " coordinates of where the person"
		help_text += " being given a headpat will have their picture put, note that this is relative to the size after"
		help_text += " any resizing of the template is done! And you can give the ID if you want, otherwise I'll make one!\n"
		help_text += "* `headpat-edit <id> <X1> <Y1> <X2> <Y2>` with the ID of the template to change!\n"
		help_text += "* `headpat-remove <id>` to completely remove that headpat template.\n"
		help_text += "* `headpat-info` to list info about all current templates, or give an ID to see that one!\n"
		help_text += "__Settings__\n"
		help_text += "Use the `settings headpat` command to set these:\n"
		help_text += " * `template-width` - The width of the templates used to generate headpats. This is a global value"
		help_text += " that is used by all servers I'm connected to."

		width_prompt = "Ah, well, I can do that, but I'll have to resize all the templates"
		width_prompt += " I'm already using, and some of them might lose quality! Also, it"
		width_prompt += " might take me a little bit. Are you sure you want me to do that?"

		super().__init__(
			name="headpat",
			desc="Give and receive headpats!",
			help_text=help_text,
			triggers=[
				InvocationTrigger('headpat'),
				InvocationTrigger('headpat-add'),
				InvocationTrigger('headpat-remove'),
				InvocationTrigger('headpat-info'),
				InvocationTrigger('headpat-edit')
			],
			resource_root=resource_root,
			save_state_on_trigger=True,
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

		self.templates = dict()
		self._last_new_template = -1
		self._template_digits = 6

	def set_global_state(self, state):
		if 'templates' in state:
			self.templates = state['templates']
		if 'last-added' in state:
			self._last_new_template = state['last-added']

	def get_global_state(self):
		new_state = {
			'templates': self.templates,
			'last-added': self._last_new_template,
		}
		return new_state

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == "headpat":
			await self.generate_headpat(bot, args)
		elif command == "headpat-add":
			await self.add_headpat(bot, metadata, args)
		elif command == "headpat-remove":
			await self.remove_headpat(bot, args)
		elif command == "headpat-info":
			t_id = None
			if len(args) > 0:
				t_id = self._validate_template_id(args[0])
			await self.get_headpat_info(bot, t_id)
		elif command == 'headpat-edit':
			await self.edit_headpat(bot, args)

	async def on_setting_change(self, bot: PluginAPI, key: str, old_value: Any, new_value: Any):
		if key != 'template-width':
			return

		msg = "Okay, I've changed the width, but now I need to resize my images! I'll let you know as soon"
		msg += " as I'm done!"
		await bot.reply(msg)
		_log.debug(util.add_context(bot.context, "Resize started, {:d} to resize...", len(self.templates)))
		await self._resize_templates(new_value)
		_log.debug(util.add_context(bot.context, "Resize of templates completed"))
		msg = "All done, " + bot.mention_user() + "! I resized all my templates!"
		await bot.reply(msg)

	async def add_headpat(self, bot: PluginAPI, metadata, args):
		await bot.require_op("headpat-add")
		if not metadata.has_attachments() or not metadata.attachments[0].is_image():
			raise BotSyntaxError("I need to know the image you want me to add, but you didn't attach one!")
		if len(args) < 4:
			msg = "You need to give me the corner coordinates of where the headpat receiver's picture"
			msg += " should go!"
			raise BotSyntaxError(msg)
		try:
			x1 = int(args[0])
		except ValueError:
			raise BotSyntaxError("X1 needs to be an integer!")
		try:
			y1 = int(args[1])
		except ValueError:
			raise BotSyntaxError("Y1 needs to be an integer!")
		try:
			x2 = int(args[2])
		except ValueError:
			raise BotSyntaxError("X2 needs to be an integer!")
		try:
			y2 = int(args[3])
		except ValueError:
			raise BotSyntaxError("Y2 needs to be an integer!")

		new_template = False
		if len(args) < 5:
			new_template = True
			template_id = self._create_unused_template_id()
		else:
			template_id = self._validate_template_id(args[4])
			if template_id in self.templates:
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
			template_data = self._normalize_template(template_width, template_data, None)

			res_fp = self.open_resource('templates/' + self._template_filename(template_id), for_writing=True)
			res_fp.write(template_data)
			res_fp.flush()
			res_fp.close()

			self.templates[template_id] = {
				'x1': x1,
				'x2': x2,
				'y1': y1,
				'y2': y2,
				'dx': x2 - x1,
				'dy': y2 - y1
			}

			if new_template:
				self._last_new_template = template_id

			_log.debug("Added headpat template " + str(template_id))
		msg = "Okay! I'll start using this new template to generate headpats, with ID `" + str(template_id) + "`:"
		await self.reply_with_templated(bot, template_id, msg)

	async def edit_headpat(self, bot: PluginAPI, args):
		await bot.require_op("headpat-edit")
		if len(args) < 5:
			msg = "You need to give me the ID of the headpat template to edit and the corner coordinates of"
			msg += " where the headpat receiver's picture should go!"
			raise BotSyntaxError(msg)
		tid = self._validate_template_id(args[0])
		if tid not in self.templates:
			raise BotSyntaxError("`" + str(tid) + "` is not a headpat template I have! Use `headpat-info` to see them.")
		try:
			x1 = int(args[1])
		except ValueError:
			raise BotSyntaxError("X1 needs to be an integer!")
		try:
			y1 = int(args[2])
		except ValueError:
			raise BotSyntaxError("Y1 needs to be an integer!")
		try:
			x2 = int(args[3])
		except ValueError:
			raise BotSyntaxError("X2 needs to be an integer!")
		try:
			y2 = int(args[4])
		except ValueError:
			raise BotSyntaxError("Y2 needs to be an integer!")

		async with bot.typing():
			self.templates[tid] = {
				'x1': x1,
				'x2': x2,
				'y1': y1,
				'y2': y2,
				'dx': x2 - x1,
				'dy': y2 - y1
			}

			_log.debug(util.add_context(bot.context, "Edited headpat template " + str(tid)))
		msg = "Okay! I'll start using the new coordinates to generate headpats with ID `" + str(tid) + "`, like this:"
		await self.reply_with_templated(bot, tid, msg)

	async def remove_headpat(self, bot: PluginAPI, args):
		await bot.require_op("headpat-remove")

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the template you want me to remove.")

		template_id = self._validate_template_id(args[0])

		if template_id in self.templates:
			async with bot.typing():
				msg_text = "Oh, " + str(template_id) + ", huh? Let's see, that would be this template:"
				await self.reply_with_templated(bot, template_id, msg_text)

			stop_using_it = await bot.confirm("Want me to stop using it?")
			if not stop_using_it:
				await bot.reply("You got it! I'll keep using it.")
			else:
				del self.templates[template_id]
				file = self._template_filename(template_id)
				self.remove_resource('templates/' + file)
				_log.debug("Removed headpat template " + str(template_id))
				await bot.reply("Okay! I'll stop using that template for headpats.")
		else:
			await bot.reply("Mmm, all right, but I was already not using that template for headpats.")
		return

	async def get_headpat_info(self, bot: PluginAPI, t_id=None):
		async with bot.typing():
			if t_id is None:
				pager = util.DiscordPager("_(template list, continued)_")
				msg = "Sure! I've currently got " + str(len(self.templates)) + " images for use with headpats. "
				await bot.reply(msg)
				pager.add_line("You can use `headpat-info` followed by the id of a template to see a picture of it!")
				pager.start_code_block()
				for t_id in self.templates.keys():
					pager.add_line(str(t_id).zfill(self._template_digits))
				pager.end_code_block()

				pages = pager.get_pages()
				for p in pages:
					await bot.reply(p)
			else:
				if t_id not in self.templates:
					msg = "Sorry, that's not a template I have! Use `headpat-info` with no arguments to see them!"
					await bot.reply(msg)
					return
				template_info = self.templates[t_id]
				msg = "Oh, sure! Here's template " + str(t_id).zfill(self._template_digits) + ":\n"
				msg += "__Corner 1__: (" + str(template_info['x1']) + ", " + str(template_info['y1']) + ")\n"
				msg += "__Corner 2__: (" + str(template_info['x2']) + ", " + str(template_info['y2']) + ")\n"
				msg += "_(Delta): (" + str(template_info['dx']) + ", " + str(template_info['dy']) + ")_"
				await self.reply_with_templated(bot, t_id, msg)

	async def reply_with_templated(self, bot: PluginAPI, tid, msg):
		if tid not in self.templates:
			raise BotModuleError("I don't have a template with that ID!")
		file = self._template_filename(tid)
		template_info = self.templates[tid]
		im = Image.open(self.open_resource('templates/' + file))
		p = pen.Pen(0, 0, 'fonts/anton/anton-regular.ttf')
		p.set_image(im)
		p.set_color(fg=(0, 0, 0, 128), bg="white")
		p.set_position(x=template_info['x1'], y=template_info['y1'])
		p.draw_solid_rect(dx=template_info['dx'], dy=template_info['dy'])

		buf = io.BytesIO()
		im.save(buf, format='PNG')
		buf.seek(0)
		await bot.reply_with_file(buf, file, msg)

	async def generate_headpat(self, bot: PluginAPI, args):
		if len(args) < 1:
			user = bot.get_user()
		else:
			men = util.parse_mention(args[0], require_type=util.MentionType.USER)
			user = bot.get_user(men.id)

		if len(self.templates) < 1:
			msg = "Argh! I don't have any backgrounds assigned to this module yet! Assign some with `headpat-add`"
			msg += " first."
			raise BotModuleError(msg)

		async with bot.typing():
			template_id = random.sample(self.templates.keys(), 1)[0]

			_log.debug("Creating headpat for template ID " + str(template_id))

			padded_id = str(template_id).zfill(self._template_digits)
			im = Image.open(self.open_resource('templates/' + self._template_filename(template_id)))
			":type : Image.Image"

			p = pen.Pen(0, 1, 'fonts/anton/anton-regular.ttf')
			template_info = self.templates[template_id]
			p.set_image(im)
			p.set_position(x=template_info['x1'], y=template_info['y1'])
			p.set_color(fg="blue", bg="black")

			avatar_bytes = await user.avatar_url_as(format='png').read()
			pfp_im = Image.open(io.BytesIO(avatar_bytes))
			p.draw_image_rect(template_info['dx'], template_info['dy'], pfp_im)

			buf = io.BytesIO()
			im.save(buf, format='PNG')
			buf.seek(0)

		msg = random.choice(headpat_messages)
		await bot.reply_with_file(buf, str(template_id) + "-" + user.name + "-generated.png", msg)

	def _create_unused_template_id(self):
		max_templates = 10 ** self._template_digits
		if len(self.templates) >= max_templates:
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
		for template_id in self.templates.keys():
			with self.open_resource('templates/' + self._template_filename(template_id)) as fp:
				data = fp.read()
			data = self._normalize_template(width, data, template_id)
			with self.open_resource('templates/' + self._template_filename(template_id), for_writing=True) as fp:
				fp.write(data)
				fp.flush()
			_log.debug("Resized headpat template " + str(template_id))
			await asyncio.sleep(0.1)

	# noinspection PyMethodMayBeStatic
	def _normalize_template(self, width: int, template_data, tid: Any):
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

		if tid is not None:
			tinfo = self.templates[tid]
			tinfo['x1'] = round(tinfo['x1'] * ratio)
			tinfo['x2'] = round(tinfo['x2'] * ratio)
			tinfo['y1'] = round(tinfo['y1'] * ratio)
			tinfo['y2'] = round(tinfo['y2'] * ratio)
			tinfo['dx'] = tinfo['x2'] - tinfo['x1']
			tinfo['dy'] = tinfo['y2'] - tinfo['y1']
			self.templates[tid] = tinfo

		return all_data


BOT_MODULE_CLASS = HeadpatModule
