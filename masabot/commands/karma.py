from . import BotBehaviorModule, RegexTrigger, InvocationTrigger
from ..util import BotSyntaxError

import re
import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class KarmaModule(BotBehaviorModule):

	def __init__(self, bot_api, resource_root):
		help_text = "The karma system assigns arbitrary points to users (and generic things) and allows other uses to"
		help_text += " increase or decrease the number of karma points.\n\nTo change the number of points, mention a"
		help_text += " user or any item followed by a '++' or '--' to increase or decrease their karma. Add more"
		help_text += " '+'/'-' characters to change the amount by even more.\n\nTo view the amount of karma, use the"
		help_text += " `karma` command followed by the mention of the user to check (or the name of the thing to"
		help_text += " check). As a shortcut, you can view your own karma by invoking `karma` with no arguments.\n\n"
		help_text += "In order to prevent huge karma changes, there is a buzzkill mode, which limits the amount that"
		help_text += " karma can change by. The `karma-buzzkill` command with no arguments will give what the current"
		help_text += " buzzkill limit is, and ops are able to give an argument to set the limit. Setting the limit to"
		help_text += " anything less than 1 disables buzzkill mode entirely, allowing any amount of karma change."

		super().__init__(
			bot_api,
			name="karma",
			desc="Tracks user reputation",
			help_text=help_text,
			triggers=[
				RegexTrigger(r'<@!?(\d+)>\s*(\+\++|--+)$'),
				InvocationTrigger('karma'),
				InvocationTrigger('karma-buzzkill')
			],
			resource_root=resource_root,
			has_state=True
		)

		self._karma = {}
		self._buzzkill_limit = 5
		self._tsundere_chance = 0.1

	def get_state(self):
		return {
			'karma': self._karma,
			'buzzkill': self._buzzkill_limit,
			'tsundere-chance': self._tsundere_chance
		}

	def set_state(self, state):
		self._karma = state['karma']
		self._buzzkill_limit = state['buzzkill']
		if 'tsundere-chance' in state:
			self._tsundere_chance = state['tsundere-chance']

	async def on_invocation(self, context, command, *args):
		if command == "karma":
			await self.show_karma(context, args)
		elif command == "karma-buzzkill":
			await self.configure_buzzkill(context, args)

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

	async def show_karma(self, context, args):
		if len(args) >= 1:
			m = re.search(r'<@!?(\d+)>$', args[0], re.DOTALL)
			if m is None:
				raise BotSyntaxError(str(args[0]) + " is not something that can have karma")
			msg = self.get_user_karma(m.group(1))
		else:
			msg = self.get_user_karma(context.author.id)
		await self.bot_api.reply(context, msg)

	async def configure_buzzkill(self, context, args):
		if len(args) > 0:
			self.bot_api.require_op(context, "karma-buzzkill <limit>", self.name)
			try:
				new_limit = int(args[0])
			except ValueError:
				raise BotSyntaxError("I need the new limit to be an integer.")
			if new_limit > 0:
				msg = ""
				if self._buzzkill_limit < 1:
					msg += "Looks like buzzkill mode was disabled before. I'll turn it on now!\n\n"
				self._buzzkill_limit = new_limit
				msg += "All right, done! The most that karma can change by is now " + str(new_limit) + "."
				await self.bot_api.reply(context, msg)
			else:
				self._buzzkill_limit = 0
				msg = "Okay! Buzzkill mode has now been disabled. Karma change is now unlimited!"
				await self.bot_api.reply(context, msg)
			_log.debug("Set buzzkill limit to " + str(self._buzzkill_limit))
		else:
			if self._buzzkill_limit > 0:
				msg = "Yep! Buzzkill mode is currently enabled; the most that karma can change by is currently"
				msg += " " + str(self._buzzkill_limit) + "."
			else:
				msg = "Hmm... It looks like there is currently no limit to how much karma can change by. Hooray!"
			await self.bot_api.reply(context, msg)

	def get_user_karma(self, uuid):
		amt = self._karma.get(uuid, 0)
		msg = "<@" + uuid + ">'s karma is at " + str(amt) + "."
		return msg

	def add_user_karma(self, uuid, amount):
		if uuid not in self._karma:
			self._karma[uuid] = 0
		self._karma[uuid] += amount
		_log.debug("Modified karma of user " + uuid + " by " + str(amount) + "; new total " + str(self._karma[uuid]))

		if random.random() < self._tsundere_chance and amount > 0:
			msg = "F-fine, <@" + uuid + ">'s karma is now " + str(self._karma[uuid]) + ". B-b-but it's not like I like"
			msg += " them or anything weird like that. So don't get the wrong idea! B-baka..."
		else:
			msg = "Okay! <@" + uuid + ">'s karma is now " + str(self._karma[uuid])
		return msg


BOT_MODULE_CLASS = KarmaModule
