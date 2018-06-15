from . import BotBehaviorModule, InvocationTrigger
from ..bot import BotSyntaxError


import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class DiceRollerModule(BotBehaviorModule):

	def __init__(self, bot_api):
		help_text = "To roll the dice, use the `roll` command followed by the number of dice and sides to role in the"
		help_text += " format <X>d<Y>. This will roll X number of Y-sided dice.\n\nExample: `roll 4d6` will roll 4"
		help_text += " d6's.\n\nIf the number of dice is left out, a single die will be rolled. If the number of sides"
		help_text += " is left out, d6 will be assumed. If no arguments are given, a single d6 is rolled.\n\n"
		help_text += "The maximum number of dice that can be rolled at once can be shown with the `roll-maxdice`"
		help_text += " command. The maximum number of sides that a die can have can be shown with the `roll-maxsides`"
		help_text += " command. Operators may change each of these numbers by giving a number after the command. A"
		help_text += " number less than 1 disables the dice limit entirely (less than 2 for the sides limit)."

		super().__init__(
			bot_api,
			name="roll",
			desc="Rolls a number of dice",
			help_text=help_text,
			triggers=[
				InvocationTrigger('roll'),
				InvocationTrigger('roll-maxsides'),
				InvocationTrigger('roll-maxdice')
			],
			has_state=True
		)

		self._max_count = 100
		self._max_sides = 100

	def get_state(self):
		return {
			'max-sides': self._max_sides,
			'max-count': self._max_count
		}

	def set_state(self, state):
		self._max_sides = state.get('max-sides', 100)
		self._max_count = state.get('max-count', 100)

	async def on_invocation(self, context, command, *args):
		if command == 'roll':
			await self.roll_dice(context, args)
		elif command == 'roll-maxsides':
			await self.get_max_sides(context, args)
		elif command == 'roll-maxdice':
			await self.get_max_dice(context, args)

	async def get_max_sides(self, context, args):
		if len(args) > 0:
			self.bot_api.require_op(context, 'roll-maxsides <limit>', self.name)
			try:
				new_limit = int(args[0])
			except ValueError:
				raise BotSyntaxError("That's not a number at all!")
			if new_limit < 2:
				if self._max_sides < 2:
					msg = "The maximum side limit is already disabled."
				else:
					msg = "Okay, I'll go ahead and disable the limit for number of sides."
				self._max_sides = 0
			else:
				msg = ""
				if self._max_sides < 2:
					msg = "Oh, right now there isn't any limit for the number of sides. I'll turn it on for you!\n\n"
				msg += "Okay! The new limit for the number of sides is now " + str(new_limit) + "!"
				self._max_sides = new_limit
			_log.debug("Set dice side limit to " + str(self._max_sides))
			await self.bot_api.reply(context, msg)
		else:
			if self._max_sides > 0:
				msg = "Sure! The limit for the number of sides is currently " + str(self._max_sides) + "."
			else:
				msg = "Right now there isn't a limit to the number of sides you can have on a die."
			await self.bot_api.reply(context, msg)

	async def get_max_dice(self, context, args):
		if len(args) > 0:
			self.bot_api.require_op(context, 'roll-maxdice <limit>', self.name)
			try:
				new_limit = int(args[0])
			except ValueError:
				raise BotSyntaxError("That's not a number at all!")
			if new_limit < 1:
				if self._max_count < 1:
					msg = "The maximum dice limit is already disabled."
				else:
					msg = "Okay, I'll go ahead and disable the limit for number of dice."
				self._max_count = 0
			else:
				msg = ""
				if self._max_count < 1:
					msg = "Oh, right now there isn't any limit for the number of dice. I'll turn it on for you!\n\n"
				msg += "Okay! The new limit for the number of dice is now " + str(new_limit) + "!"
				self._max_count = new_limit
			_log.debug("Set dice limit to " + str(self._max_count))
			await self.bot_api.reply(context, msg)
		else:
			if self._max_count > 0:
				msg = "Sure! The limit for the number of dice is currently " + str(self._max_count) + "."
			else:
				msg = "Right now there isn't a limit to the number of dice you can roll at once."
			await self.bot_api.reply(context, msg)

	async def roll_dice(self, context, args):
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
		if sides > self._max_sides > 1:
			msg = "Uh oh! That's too many sides on a die! The most you can have right now is " + str(self._max_sides)
			msg += "."
			await self.bot_api.reply(context, msg)
		elif sides < 2:
			msg = "I'm sorry, but that's just not possible! All dice have to have at"
			msg += " least two sides!"
			raise BotSyntaxError(msg)
		elif count > self._max_count > 0:
			msg = "Woah! That's way too many dice! Are you running Shadowrun or something? The most you can have right"
			msg += " now is " + str(self._max_count) + "."
			await self.bot_api.reply(context, msg)
		elif count < 1:
			msg = "Well, if you say so! I will roll " + str(count) + " dice! That is less than 1, so you automatically"
			msg += " fail the roll. Not only that, but rocks fell down from the sky and now everybody is dead!\n\n"
			msg += "...this is just awful... w-why would you make me do that? :c"
			await self.bot_api.reply(context, msg)
		else:
			rolls = ""
			total = 0
			for x in range(count):
				r = random.randint(1, sides)
				rolls += str(r) + ", "
				total += r
			msg += "All right! " + context.mention() + " rolled {0:d}d{1:d}...\n"
			msg += "{2:s}\nTotal: {3:d}"
			msg = msg.format(count, sides, rolls[:-2], total)
			await self.bot_api.reply(context, msg)


BOT_MODULE_CLASS = DiceRollerModule
