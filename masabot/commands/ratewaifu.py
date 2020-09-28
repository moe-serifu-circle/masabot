from ..util import BotSyntaxError
from . import BotBehaviorModule, InvocationTrigger
from .. import util, settings
from ..bot import PluginAPI

import logging

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class RateWaifuModule(BotBehaviorModule):
	def __init__(self, resource_root: str):
		help_text = "The \"ratewaifu\" module lets me rate your favorite waifus and tell you if I think they are good or not!"
		help_text += " To use it, just do `ratewaifu <name-of-waifu>`."

		super().__init__(
			name="ratewaifu",
			desc="Rate your waifus",
			help_text=help_text,
			triggers=[
				InvocationTrigger("ratewaifu")
			],
			resource_root=resource_root,
			global_settings=[
				settings.Key(settings.key_type_string, 'seed')
			]
		)

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if len(args) < 1:
			raise BotSyntaxError("I need to know who you want me to rate!")
		waifu = str(args[0])
		seed = await bot.get_setting('seed')
		rating = (hash(waifu.lower() + seed) % 10) + 1
		rate_msg = "I'd give " + waifu + " a " + str(rating) + "/10."
		if rating == 1:
			msg = "❌ **|** " + rate_msg + " Woah, uh... I didn't think anybody could like " + waifu + "..."
			msg += " Oh! But it's okay if you do!"
		elif rating == 2:
			msg = "🗑️ **|** " + rate_msg + " That's pretty awful! @_@"
		elif rating == 3:
			msg = "🚮 **|** " + rate_msg + " But, I don't quite understand why you like them! :O"
		elif rating == 4:
			msg = "🙁 **|** " + rate_msg + " Yeah, I guess they're okay!"
		elif rating == 5:
			msg = "😐 **|** " + rate_msg + " I think you two would be good together!"
		elif rating == 6:
			msg = "🙂 **|** " + rate_msg + " Heehee, actually I kinda like them, too! Oh, but I'd never get in your way!"
		elif rating == 7:
			msg = "😃 **|** " + rate_msg + " Oh my gosh, good choice! You must have really good taste!"
		elif rating == 8:
			msg = "😅 **|** " + rate_msg + " Woah, gosh, ahaha, yeah they, they make me feel all nervous, heheheh"
		elif rating == 9:
			msg = "❤️ **|** " + rate_msg + " Ahahaha yes! Yes! They are amazing!"
		elif rating == 10:
			msg = "😍 **|** " + rate_msg + " You better get them before *I* do!"
		else:
			raise ValueError("expected rating to be between 1 and 10 but was: " + str(rating))
		await bot.reply(msg)


BOT_MODULE_CLASS = RateWaifuModule
