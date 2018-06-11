from . import BotBehaviorModule, InvocationTrigger
from ..bot import BotSyntaxError, BotModuleError

import requests
import random
import logging


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class AnimemeModule(BotBehaviorModule):

	def __init__(self, bot_api):
		help_text = "Generates anime memes by assigning a random background to the given text. Type `animeme` followed"
		help_text += " by one or two sentences in quotes to generate a meme for them. Example: `animeme \"This meme\""
		help_text += " \"is awesome!\"`.\n\nOps are able to add new images to the system from by using the"
		help_text += " `animeme-add` command, followed by the ImageFlip ID of the image to add. They can also use the"
		help_text += " `animeme-remove` command followed by the ImageFlip ID to remove an image from the system."

		super().__init__(
			bot_api,
			name="animeme",
			desc="Generates anime memes",
			help_text=help_text,
			triggers=[
				InvocationTrigger('animeme'),
				InvocationTrigger('animeme-add'),
				InvocationTrigger('animeme-remove')
			],
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

	async def add_animeme(self, context, args):
		self.bot_api.require_op(context)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the image you want me to add.")

		img_id = str(int(args[0]))  # pass it through int first so it will fail if user passes in non-int ID.

		if img_id in self.image_ids:
			await self.bot_api.reply(context, "Ah, I'm already generating animemes with that image.")
		else:
			self.image_ids.append(img_id)
			await self.bot_api.reply(context, "Okay! I'll start using that new template to generate animemes ^_^")

	async def remove_animeme(self, context, args):
		self.bot_api.require_op(context)

		if len(args) < 1:
			raise BotSyntaxError("I need to know the ID of the image you want me to remove.")

		img_id = args[0]

		if img_id in self.image_ids:
			self.image_ids.remove(img_id)
			await self.bot_api.reply(context, "Okay! I'll stop using that template in animemes.")
		else:
			await self.bot_api.reply(context, "Mmm, all right, but I was already not using that template for animemes.")

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

		img_id = random.choice(self.image_ids)

		_log.debug("Fetching for template ID " + str(img_id))

		response = requests.post("https://api.imgflip.com/caption_image", data={
			"template_id": img_id,
			"username": self._user,
			"password": self._pass,
			"text0": meme_line_1,
			"text1": meme_line_2
		})

		msg = response.json()['data']['url'] + " _(" + str(img_id) + ")_"

		await self.bot_api.reply(context, msg)


BOT_MODULE_CLASS = AnimemeModule
