from . import BotBehaviorModule, BotSyntaxError, RegexTrigger, InvocationTrigger

import re


class KarmaModule(BotBehaviorModule):

	def __init__(self, bot_api):
		help_text="The karma system assigns arbitrary points to users (and generic things) and allows other uses to"
		help_text += " increase or decrease the number of karma points.\n\nTo change the number of points, mention a"
		help_text += " user or any item followed by a '++' or '--' to increase or decrease their karma. Add more"
		help_text += " '+'/'-' characters to change the amount by even more.\n\nTo view the amount of karma, use the"
		help_text += "` karma` command followed by the mention of the user to check (or the name of the thing to"
		help_text += "check). As a shortcut, you can view your own karma by invoking `karma` with no arguments."

		super().__init__(
			bot_api,
			name="karma",
			desc="Tracks user reputation",
			help_text=help_text,
			triggers=[
				RegexTrigger(r'<@!?(\d+)>\s*(\+\++|--+)$'),
				InvocationTrigger('karma')
			],
			has_state=True
		)

		self._karma = {}
		self._buzzkill_limit = 5

	def get_state(self):
		return {'karma': self._karma, 'buzzkill': self._buzzkill_limit}

	def set_state(self, state):
		self._karma = state['karma']
		self._buzzkill_limit = state['buzzkill']

	async def on_invocation(self, context, command, *args):
		if len(args) >= 1:
			m = re.search(r'<@!?(\d+)>$', args[0], re.DOTALL)
			if m is None:
				raise BotSyntaxError(str(args[0]) + " is not something that can have karma")
			msg = self.get_user_karma(m.group(1))
		else:
			msg = self.get_user_karma(context.author.id)
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
