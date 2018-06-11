from . import BotBehaviorModule, InvocationTrigger
from ..bot import BotSyntaxError

import requests
import random


class AnimeModule(BotBehaviorModule):

	def __init__(self, bot_api):
		help_text = "Generates anime memes by assigning a random background to the given text. Type `anime` followed by"
		help_text += " one or two sentences in quotes to generate a meme for them. Example: `anime \"This meme\""
		help_text += " \"is awesome!\"`."

		super().__init__(
			bot_api,
			name="anime",
			desc="Generates anime memes",
			help_text=help_text,
			triggers=[
				InvocationTrigger('anime')
			],
			has_state=True
		)

		self.image_ids = [
			25807110,
			94397920,
			18174314,
			22220076,
			34416107,
			12474821,
			12993192,
			4597749,
			7339663,
			35535326,
			19104818,
			57423992,
			26921405,
			17626160,
			44571077,
			43405372,
			38950445,
			19622581,
			31239668,
			117332355,
			42888394,
			36733847,
			38271852,
			42673583,
			71304973,
			50135478,
			50638399,
			58286928,
			47153328,
			39726670,
			122956951,
			35276598,
			114668963,
			48835181,
			67457456,
			77104422,
			53114009,
			71438489,
			49205105,
			67580477,
			76331267,
			80975850,
			31666916,
			51969741,
			44660853,
			4013622,
			43950101,
			49199381,
			27750606,
			41945860,
			68116873,
			113134097,
			71218628,
			101305547,
			49619379,
			64986519,
			50597830,
			89123027,
			28388155,
			52963738,
			106117641,
			34303382,
			53112845,
			25658529,
			115677867,
			59872333,
			114463489,
			22028330,
			100708736,
			86378411,
			95265591,
			50135595,
			83874167,
			108974740,
			121784562,
			103202143
		]

	async def on_invocation(self, context, command, *args):
		if len(args) < 1:
			raise BotSyntaxError("I need at least one line of text to make a meme.")
		meme_line_1 = args[0]
		if len(args) > 1:
			meme_line_2 = args[1]
		else:
			meme_line_2 = ""

		img_id = random.choice(self._image_ids)

		response = requests.post("https://api.imgflip.com/caption_image", data={
			"template_id": ,
			"username": "waakis",
			"password": "123abc",
			"text0": meme_line_1,
			"text1": meme_line_2
		})
		await self.bot_api.reply(context, msg)

	async def on_regex_match(self, context, *match_groups):
		msg = None

		user = match_groups[1]
		amount_str = match_groups[2]
		amount = len(amount_str) - 1

		if amount_str.startswith('-'):
			amount *= -1

		if amount is not None:

			if user == context.author.id:
				msg = "You cannot set karma on yourself!"
			elif abs(amount) > self._buzzkill_limit > 0:
				msg = "Buzzkill mode enabled;"
				msg += " karma change greater than " + str(self._buzzkill_limit) + " not allowed"
			else:
				msg = self.add_user_karma(user, amount)
		if msg is not None:
			await self.bot_api.reply(context, msg)

	def get_user_karma(self, uuid):
		amt = self._karma.get(uuid, 0)
		msg = "<@" + uuid + ">'s karma is at " + str(amt) + "."
		return msg

	def add_user_karma(self, uuid, amount):
		if uuid not in self._karma:
			self._karma[uuid] = 0
		self._karma[uuid] += amount

		msg = "Okay! <@" + uuid + ">'s karma is now " + str(self._karma[uuid])
		return msg


BOT_MODULE_CLASS = KarmaModule
