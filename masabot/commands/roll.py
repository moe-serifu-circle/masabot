from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError
from .. import util, settings
from ..bot import PluginAPI


import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class DiceRollerModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "To roll the dice, use the `roll` command followed by the number of dice and sides to role in the"
		help_text += " format <X>d<Y>. This will roll X number of Y-sided dice.\n\nExample: `roll 4d6` will roll 4"
		help_text += " d6's.\n\nIf the number of dice is left out, a single die will be rolled. If the number of sides"
		help_text += " is left out, d6 will be assumed. If no arguments are given, a single d6 is rolled.\n\n"
		help_text += "The maximum number of dice that can be rolled at once can be shown with the `roll-maxdice`"
		help_text += " command. The maximum number of sides that a die can have can be shown with the `roll-maxsides`"
		help_text += " command. Operators may change each of these numbers by giving a number after the command. A"
		help_text += " number less than 1 disables the dice limit entirely (less than 2 for the sides limit)."

		super().__init__(
			name="roll",
			desc="Rolls a number of dice",
			help_text=help_text,
			triggers=[
				InvocationTrigger('roll'),
			],
			resource_root=resource_root,
			server_only_settings=[
				settings.Key(settings.key_type_int, 'max-count', default=1000),
				settings.Key(settings.key_type_int, 'max-sides', default=200),
			]
		)

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == 'roll':
			await self.roll_dice(bot, args)

	async def roll_dice(self, bot: PluginAPI, args):
		if bot.context.is_pm:
			max_sides = 100000
			max_dice = 100000
		else:
			max_sides = bot.get_setting('max-sides')
			max_dice = bot.get_setting('max-count')

		msg = ""
		sides = 6
		count = 1
		if len(args) > 0:
			try:
				parts = args[0].split('d')
				count = int(parts[0])
				sides = int(parts[1])
			except (IndexError, ValueError):
				msg += "Um, I'm sorry, but, well, that is not in XdY format, so I'll assume you mean 1d6, okay?\n\n"
		if sides > max_sides > 1:
			msg = "Uh oh! That's too many sides on a die! The most you can have right now is " + str(max_sides)
			msg += "."
			await bot.reply(msg)
		elif sides < 2:
			msg = "I'm sorry, but that's just not possible! All dice have to have at"
			msg += " least two sides!"
			raise BotSyntaxError(msg)
		elif count > max_dice > 0:
			msg = "Woah! That's way too many dice! Are you running Shadowrun or something? The most you can have right"
			msg += " now is " + str(max_dice) + "."
			await bot.reply(msg)
		elif count < 1:
			msg = "Well, if you say so! I will roll " + str(count) + " dice! That is less than 1, so you automatically"
			msg += " fail the roll. Not only that, but rocks fell down from the sky and now everybody is dead!\n\n"
			msg += "...this is just awful... w-why would you make me do that? :c"
			await bot.reply(msg)
		else:
			rolls = ""
			total = 0
			for x in range(count):
				r = random.randint(1, sides)
				rolls += str(r) + ", "
				total += r
			msg += "All right! " + bot.mention_user() + " rolled {0:d}d{1:d}...\n"
			msg += "{2:s}\nTotal: {3:d}"
			msg = msg.format(count, sides, rolls[:-2], total)
			await bot.reply(msg)


BOT_MODULE_CLASS = DiceRollerModule
