from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError, BotModuleError

import requests
import random
import logging
import re
import io


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

		self.image_ids = []
		self._user = ""
		self._pass = ""

	def load_config(self, config):
		if 'username' not in config:
			raise BotModuleError("Required key 'username' missing from 'anime' module config")
		if 'password' not in config:
			raise BotModuleError("Required key 'password' missing from 'anime' module config")
		self._user = config['username']
		self._pass = config['password']

	def set_state(self, state):
		self.image_ids = state['image-ids']

	def get_state(self):
		new_state = {
			'image-ids': self.image_ids
		}
		return new_state

	async def on_invocation(self, context, command, *args):
		if command == "animeme":
			await self.generate_animeme(context, args)
		elif command == "animeme-add":
			await self.add_animeme(context, args)
		elif command == "animeme-remove":
			await self.remove_animeme(context, args)
		elif command == "animeme-info":
			await self.get_animeme_info(context)

	async def add_animeme(self, context, args):
		self.bot_api.require_op(context, "animeme-add", self.name)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the template you want me to add.")

		try:
			img_id = str(int(args[0]))  # pass it through int first so it will fail if user passes in non-int ID.
		except ValueError:
			msg = "Template IDs should be a bunch of numbers, but '" + str(args[0]) + "' has some not-numbers in it!"
			raise BotSyntaxError(msg)

		await self.bot_api.reply_typing(context)
		if img_id in self.image_ids:
			await self.bot_api.reply(context, "Ah, I'm already generating animemes with that image.")
		else:
			try:
				prev, prev_name = await self.get_template_preview(img_id)
			except BotSyntaxError:
				raise BotSyntaxError("I couldn't find any templates for that ID; are you super super sure it's valid?")

			msg_text = "Here's what I found for " + str(img_id) + ":"
			await self.bot_api.reply_with_file(context, io.BytesIO(prev), prev_name, msg_text)

			reply = await self.bot_api.prompt_for_option(context, "Is that what you want me to add?")
			if reply is None:
				msg = "I never heard back from you on the animemes..."
				msg += " Did... did you forget about me? T_T\nLet me know if you want to try adding a template again."
				raise BotModuleError(msg)
			elif reply == "no":
				await self.bot_api.reply(context, "Okay, no problem! I'll keep it out of my templates then.")
			elif reply == "yes":
				self.image_ids.append(img_id)
				_log.debug("Added new animeme template " + str(img_id))
				await self.bot_api.reply(context, "Okay! I'll start using that new template to generate animemes ^_^")

	async def remove_animeme(self, context, args):
		self.bot_api.require_op(context, "animeme-remove", self.name)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the template you want me to remove.")

		img_id = args[0]

		await self.bot_api.reply_typing(context)
		if img_id in self.image_ids:
			try:
				prev, prev_name = await self.get_template_preview(img_id)
			except BotSyntaxError:
				_log.exception("Problem fetching known animeme template")
				msg = "This is really weird, I can't find a preview for that image, but I was totally using it"
				msg += " before..."
				await self.bot_api.reply(context, msg)
			else:
				msg_text = "Oh, " + str(img_id) + ", huh? Let's see, that would be this template:"
				await self.bot_api.reply_with_file(context, io.BytesIO(prev), prev_name, msg_text)

			reply = await self.bot_api.prompt_for_option(context, "Want me to stop using it?")
			if reply is None:
				msg = "Hey, you never answered me about the animemes..."
				msg += " You didn't forget about me, did you?\n\nLet me know if you want to try removing a template"
				msg += " again."
				raise BotModuleError(msg)
			elif reply == "no":
				await self.bot_api.reply(context, "You got it! I'll keep using it.")
			elif reply == "yes":
				self.image_ids.remove(img_id)
				_log.debug("Removed animeme template " + str(img_id))
				await self.bot_api.reply(context, "Okay! I'll stop using that template in animemes.")
		else:
			await self.bot_api.reply(context, "Mmm, all right, but I was already not using that template for animemes.")

	async def get_animeme_info(self, context):
		msg = "Sure! I've currently got " + str(len(self.image_ids)) + " images for use with animemes."
		await self.bot_api.reply(context, msg)

	async def generate_animeme(self, context, args):
		if len(args) < 1:
			raise BotSyntaxError("I need at least one line of text to make a meme.")
		meme_line_1 = args[0]
		if len(args) > 1:
			meme_line_2 = args[1]
		else:
			meme_line_2 = ""

		if len(self.image_ids) < 1:
			msg = "Argh! I don't have any backgrounds assigned to this module yet! Assign some with `animeme-add`"
			msg += " first."
			raise BotModuleError(msg)

		await self.bot_api.reply_typing(context)
		img_id = random.choice(self.image_ids)

		_log.debug("Fetching for template ID " + str(img_id))

		response = requests.post("https://api.imgflip.com/caption_image", data={
			"template_id": img_id,
			"username": self._user,
			"password": self._pass,
			"text0": meme_line_1,
			"text1": meme_line_2
		})

		if not response.json()['success']:
			msg = ""
			if 'error_message' in response.json():
				msg = " " + response.json()['error_message']
			raise BotModuleError("Imgflip returned an error when I tried to make the meme!" + msg)

		msg = response.json()['data']['url'] + " _(" + str(img_id) + ")_"

		await self.bot_api.reply(context, msg)

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


BOT_MODULE_CLASS = AnimemeModule
