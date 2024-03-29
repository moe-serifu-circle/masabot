from typing import Any, Sequence

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
	"Please take this on your head, I hope it makes you happy! *pats you gently*",
	"*pats you a lot* >.< If things have been rough, I hope this makes you feel better! *pats you more*",
	"*pats you on the head*",
	"Here, you absolutely deserve this!",
	"Yes, please let me pat you! *pats you* On the head! *pats you more*",
	"Have another lovely pat on the head!",
	"d'awwww you look really cute when I pat you!",
	"Do you need a headpat? Here!",
	"You are valid uwu",
	"Hey, everything will be okay. *pat-pat*",
	"You're cute!"
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
			self.templates = dict()
			for k in state['templates']:
				v = state['templates'][k]
				self.templates[k] = {
					'x1': v['x1'],
					'x2': v['x2'],
					'y1': v['y1'],
					'y2': v['y2'],
					'dx': v['dx'],
					'dy': v['dy'],
					'width': v['width'],
					'height': v['height'],
				}

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
		bot.require_superop("headpat-add", self)
		if not metadata.has_attachments() or not metadata.attachments[0].is_image():
			raise BotSyntaxError("I need to know the image you want me to add, but you didn't attach one!")
		if len(args) < 4:
			msg = "You need to give me the corner coordinates of where the headpat receiver's picture"
			msg += " should go!"
			raise BotSyntaxError(msg)

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

			with Image.open(io.BytesIO(template_data)) as im:
				size = im.width, im.height
			x1, y1, x2, y2 = extract_corners(args[0:4], size)

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
				'dy': y2 - y1,
				'width': size[0],
				'height': size[1]
			}

			if new_template:
				self._last_new_template = template_id

			_log.debug("Added headpat template " + str(template_id))
		msg = "Okay! I'll start using this new template to generate headpats, with ID `" + str(template_id) + "`:"
		await self.reply_with_templated(bot, template_id, msg)

	async def edit_headpat(self, bot: PluginAPI, args):
		bot.require_superop("headpat-edit", self)
		if len(args) < 5:
			msg = "You need to give me the ID of the headpat template to edit and the corner coordinates of"
			msg += " where the headpat receiver's picture should go!"
			raise BotSyntaxError(msg)
		tid = self._validate_template_id(args[0])
		if tid not in self.templates:
			raise BotSyntaxError("`" + str(tid) + "` is not a headpat template I have! Use `headpat-info` to see them.")
		tinfo = self.templates[tid]

		x1, y1, x2, y2 = extract_corners(args[1:5], size=(tinfo['width'], tinfo['height']))
		async with bot.typing():
			self.templates[tid] = {
				'x1': x1,
				'x2': x2,
				'y1': y1,
				'y2': y2,
				'dx': x2 - x1,
				'dy': y2 - y1,
				'width': tinfo['width'],
				'height': tinfo['height']
			}

			_log.debug(util.add_context(bot.context, "Edited headpat template " + str(tid)))
		msg = "Okay! I'll start using the new coordinates (" + str(x1) + ", " + str(y1) + "), (" + str(x2) + ","
		msg += " " + str(y2) + ") to generate headpats with ID `" + str(tid) + "`, like this:"
		await self.reply_with_templated(bot, tid, msg)

	async def remove_headpat(self, bot: PluginAPI, args):
		bot.require_superop("headpat-remove", self)

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
		if t_id is not None and t_id not in self.templates:
			msg = "Sorry, that's not a template I have! Use `headpat-info` with no arguments to see them!"
			await bot.reply(msg)
			return
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
				template_info = self.templates[t_id]
				msg = "Oh, sure! Here's template " + str(t_id).zfill(self._template_digits) + ":\n"
				msg += "__Size:__ " + str(template_info['width']) + "x" + str(template_info['height']) + "\n"
				msg += "__Corner 1:__ (" + str(template_info['x1']) + ", " + str(template_info['y1']) + ")\n"
				msg += "__Corner 2:__ (" + str(template_info['x2']) + ", " + str(template_info['y2']) + ")\n"
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
		p.set_color(fg=(0, 0, 0, 128), bg=(255, 255, 255, 128))

		# need to do weird math bc we do not assume that the user args are lower args so subtraction gets weird,
		# and convention is that we put the image exactly where user sees rect drawn.
		x1, y1, x2, y2 = template_info['x1'], template_info['y1'], template_info['x2'], template_info['y2']
		ul = (min(x1, x2), min(y1, y2))
		p.set_position(x=ul[0], y=ul[1])
		p.draw_solid_rect(dx=abs(template_info['dx']) - 1, dy=abs(template_info['dy']) - 1)

		# now draw the hash marks for percent, if big enough for it to make sense
		if template_info['height'] > 40 and template_info['width'] > 40:
			def draw_percent_hash(x1p, y1p, x2p, y2p, size=1):
				"""Draw a hash than an off-color - 1"""
				dx = x2p-x1p
				dy = y2p-y1p
				size_adj = int(0.5 * size)
				p.set_line_size(width=size)
				p.set_color(fg=(0, 0, 0))
				if x2p == x1p:
					p.set_position(x=x1p-size_adj, y=y1p)
				else:
					p.set_position(x=x1p, y=y1p-size_adj)
				p.draw_line(dx=dx, dy=dy)
				p.set_color(fg=(255, 255, 255))
				if x2p == x1p:
					p.move(dx=size, dy=-dy)
				else:
					p.move(dx=-dx, dy=size)
				p.draw_line(dx=dx, dy=dy)

			w = template_info['width']
			h = template_info['height']
			for percent in range(10, 100, 10):
				frac = float(percent) / 100.0
				horz_x = int(w * frac)
				vert_y = int(h * frac)
				if percent == 50:
					line_w = 2
					line_len = 20
				else:
					line_w = 1
					line_len = 10
				draw_percent_hash(horz_x, 0, horz_x, line_len, size=line_w)
				draw_percent_hash(horz_x, h, horz_x, h-line_len, size=line_w)
				draw_percent_hash(0, vert_y, line_len, vert_y, size=line_w)
				draw_percent_hash(w, vert_y, w-line_len, vert_y, size=line_w)

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

		# TODO: im p sure this is done in one case only so why is it embedded deep here? should probs be near caller
		if tid is not None:
			tinfo = self.templates[tid]
			tinfo['x1'] = round(tinfo['x1'] * ratio)
			tinfo['x2'] = round(tinfo['x2'] * ratio)
			tinfo['y1'] = round(tinfo['y1'] * ratio)
			tinfo['y2'] = round(tinfo['y2'] * ratio)
			tinfo['dx'] = tinfo['x2'] - tinfo['x1']
			tinfo['dy'] = tinfo['y2'] - tinfo['y1']
			tinfo['height'] = new_height
			tinfo['width'] = width
			self.templates[tid] = tinfo

		return all_data


def extract_corners(args: Sequence[str], size: (int, int)) -> (int, int, int, int):
	"""
	Get coordinates that are valid of corners.
	:param args: must be a sequence of at least length 4. Only first four arguments are used.
	:param size: width, height of the image to bound the arguments and convert percents with.
	:return: The x1, y1, x2, y2 coordinates, guaranteed to fit within the given size.
	:except: BotSyntaxError if there is a problem with the arguments.
	"""
	try:
		x1 = util.parse_ranged_int_or_percent(args[0], 0, size[0])
	except ValueError as e:
		raise BotSyntaxError("X1 doesn't look right, " + str(e))
	try:
		y1 = util.parse_ranged_int_or_percent(args[1], 0, size[1])
	except ValueError as e:
		raise BotSyntaxError("Y1 doesn't look right, " + str(e))
	try:
		x2 = util.parse_ranged_int_or_percent(args[2], 0, size[0])
	except ValueError as e:
		raise BotSyntaxError("X2 doesn't look right, " + str(e))
	try:
		y2 = util.parse_ranged_int_or_percent(args[3], 0, size[1])
	except ValueError as e:
		raise BotSyntaxError("Y2 doesn't look right, " + str(e))
	if x1 == x2:
		raise BotSyntaxError("X1 and X2 can't be the same, there'd be nowhere to put the picture!")
	if y1 == y2:
		raise BotSyntaxError("Y1 and Y2 can't be the same, there'd be nowhere to put the picture!")
	return x1, y1, x2, y2


BOT_MODULE_CLASS = HeadpatModule
