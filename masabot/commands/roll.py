from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError


import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class DiceRollerModule(BotBehaviorModule):

	def __init__(self, bot_api, resource_root):
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
			resource_root=resource_root,
			has_state=True
		)

		self._max_count = {}
		self._max_sides = {}

	def get_state(self, server_id: int):
		if server_id not in self._max_count:
			self._max_count[server_id] = 100
			self._max_sides[server_id] = 100

		return {
			'max-sides': self._max_sides[server_id],
			'max-count': self._max_count[server_id]
		}

	def set_state(self, server_id: int, state):
		self._max_sides[server_id] = state.get('max-sides', 100)
		self._max_count[server_id] = state.get('max-count', 100)

	async def on_invocation(self, context, metadata, command, *args):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type command: str
		:type args: str
		"""
		if command == 'roll':
			await self.roll_dice(context, args)
		elif command == 'roll-maxsides':
			await self.get_max_sides(context, args)
		elif command == 'roll-maxdice':
			await self.get_max_dice(context, args)

	async def get_max_sides(self, context, args):
		server_id = await self.bot_api.require_server(context)
		if len(args) > 0:
			self.bot_api.require_op(context, server_id, 'roll-maxsides <limit>', self.name)
			try:
				new_limit = int(args[0])
			except ValueError:
				raise BotSyntaxError("That's not a number at all!")
			if new_limit < 2:
				if self._max_sides[server_id] < 2:
					msg = "The maximum side limit is already disabled."
				else:
					msg = "Okay, I'll go ahead and disable the limit for number of sides."
				self._max_sides[server_id] = 0
			else:
				msg = ""
				if self._max_sides[server_id] < 2:
					msg = "Oh, right now there isn't any limit for the number of sides. I'll turn it on for you!\n\n"
				msg += "Okay! The new limit for the number of sides is now " + str(new_limit) + "!"
				self._max_sides[server_id] = new_limit
			_log.debug("Set dice side limit to " + str(self._max_sides[server_id]))
			await self.bot_api.reply(context, msg)
		else:
			if self._max_sides[server_id] > 0:
				msg = "Sure! The limit for the number of sides is currently " + str(self._max_sides[server_id]) + "."
			else:
				msg = "Right now there isn't a limit to the number of sides you can have on a die."
			await self.bot_api.reply(context, msg)

	async def get_max_dice(self, context, args):
		server_id = await self.bot_api.require_server(context)
		if len(args) > 0:
			self.bot_api.require_op(context, server_id, 'roll-maxdice <limit>', self.name)
			try:
				new_limit = int(args[0])
			except ValueError:
				raise BotSyntaxError("That's not a number at all!")
			if new_limit < 1:
				if self._max_count[server_id] < 1:
					msg = "The maximum dice limit is already disabled."
				else:
					msg = "Okay, I'll go ahead and disable the limit for number of dice."
				self._max_count[server_id] = 0
			else:
				msg = ""
				if self._max_count[server_id] < 1:
					msg = "Oh, right now there isn't any limit for the number of dice. I'll turn it on for you!\n\n"
				msg += "Okay! The new limit for the number of dice is now " + str(new_limit) + "!"
				self._max_count[server_id] = new_limit
			_log.debug("Set dice limit to " + str(self._max_count[server_id]))
			await self.bot_api.reply(context, msg)
		else:
			if self._max_count[server_id] > 0:
				msg = "Sure! The limit for the number of dice is currently " + str(self._max_count[server_id]) + "."
			else:
				msg = "Right now there isn't a limit to the number of dice you can roll at once."
			await self.bot_api.reply(context, msg)

	async def roll_dice(self, context, args):
		if context.is_pm:
			max_sides = 100000
			max_dice = 100000
		else:
			max_sides = self._max_sides[context.source.id]
			max_dice = self._max_count[context.source.id]

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
			await self.bot_api.reply(context, msg)
		elif sides < 2:
			msg = "I'm sorry, but that's just not possible! All dice have to have at"
			msg += " least two sides!"
			raise BotSyntaxError(msg)
		elif count > max_dice > 0:
			msg = "Woah! That's way too many dice! Are you running Shadowrun or something? The most you can have right"
			msg += " now is " + str(max_dice) + "."
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
