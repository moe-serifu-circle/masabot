from . import BotBehaviorModule, RegexTrigger, InvocationTrigger
from ..util import BotSyntaxError
from .. import util, settings
from ..bot import PluginAPI

import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class KarmaModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "The karma system assigns arbitrary points to users (and generic things) and allows other uses to"
		help_text += " increase or decrease the number of karma points.\n\nTo change the number of points, mention a"
		help_text += " user or any item followed by a '++' or '--' to increase or decrease their karma. Add more"
		help_text += " '+'/'-' characters to change the amount by even more.\n\nTo view the amount of karma, use the"
		help_text += " `karma` command followed by the mention of the user to check (or the name of the thing to"
		help_text += " check). As a shortcut, you can view your own karma by invoking `karma` with no arguments.\n\n"
		help_text += "Additionally, if you want to check the karma leaderboard for this server, you can view it by"
		help_text += " invoking `karma-top` with no arguments.\n\n"
		help_text += "If you would like to see a user's global karma (or your own global karma), simply add a `global`"
		help_text += " to the end of the command (e.g. `karma global` to see your own, `karma @user global` to see"
		help_text += " another user's global karma).\n\n"
		help_text += "To see the top list for the server, you can do `!karma-top`.\n\n"
		help_text += "__Settings__\n"
		help_text += " * `buzzkill-limit` - The maximum amount that karma can change by. Setting to anything less than 1"
		help_text += " disables buzzkill mode entirely, allowing any amount of karma change.\n"
		help_text += " * `tsundere-chance` - How likely I am to act tsundere when increasing karma."

		super().__init__(
			name="karma",
			desc="Tracks user reputation",
			help_text=help_text,
			triggers=[
				RegexTrigger(r'<([#@])([!&]?)(\d+)>\s*(\+\++|--+)$'),
				InvocationTrigger('karma'),
				InvocationTrigger('karma-top')
			],
			resource_root=resource_root,
			has_state=True,
			server_only_settings=[
				settings.Key(settings.key_type_int_range(min=0), 'buzzkill-limit', default=5),
				settings.Key(settings.key_type_percent, 'tsundere-chance', default=0.1),
			]
		)

		self._karma = {}

	def get_global_state(self):
		return {
			'karma': self._karma,
		}

	def set_global_state(self, state):
		loaded_dict = state.get('karma', {})
		for idx in loaded_dict:
			self._karma[int(idx)] = loaded_dict[idx]

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == "karma":
			await self.show_karma(bot, args)
		elif command == "karma-top":
			await self.show_toplist_karma(bot)

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		msg = None

		is_channel = match_groups[1] == '#'
		is_role = match_groups[2] == '&'
		if is_role:
			raise BotSyntaxError("That's a role, not a user, and I'm not really comfortable giving an entire role karma!")
		elif is_channel:
			raise BotSyntaxError("That's sort of a channel so I don't think I can really give that karma!")
		user = int(match_groups[3])
		amount_str = match_groups[4]
		amount = len(amount_str) - 1

		if amount_str.startswith('-'):
			amount *= -1

		buzzkill_limit = await bot.get_setting('buzzkill-limit')

		if amount is not None:
			if user == bot.get_user().id:
				msg = "You cannot set karma on yourself!"
			elif abs(amount) > buzzkill_limit > 0:
				msg = "Buzzkill mode enabled;"
				msg += " karma change greater than " + str(buzzkill_limit) + " not allowed"
			else:
				if bot.context.is_pm:
					msg = await self.add_user_karma(bot, user, 0, amount)
				else:
					msg = await self.add_user_karma(bot, user, bot.get_guild().id, amount)
		if msg is not None:
			await bot.reply(msg)

	async def show_karma(self, bot: PluginAPI, args):
		"""
		replies with given user's karma, by default displays the local karma
		(karma only from current server)
		"""

		server = 0
		if not bot.context.is_pm:
			server = bot.get_guild().id

		global_karma = False
		if len(args) > 1 and args[1].lower() == "global":
			global_karma = True

		if len(args) >= 1:
			try:
				mention = util.parse_mention(args[0])
			except BotSyntaxError:
				if args[0].lower() == "global":
					msg = self.get_user_karma(bot.get_user().id, server_id=server, global_karma=True)
				else:
					raise BotSyntaxError(str(args[0]) + " is not something that can have karma")
			else:
				if mention.is_role():
					raise BotSyntaxError(str(mention) + " is a role, so it can't have karma")
				elif mention.is_channel():
					raise BotSyntaxError(str(mention) + " is a channel, so it can't have karma")
				# no idea why pycharm is complaining on the next line; thinking it's a glitch in the static analysis?
				# remove these two comments when the next line doesn't trigger a warning in pycharm:
				msg = self.get_user_karma(mention.id, server_id=server, global_karma=global_karma)
		else:
			msg = self.get_user_karma(bot.get_user().id, server_id=server, global_karma=global_karma)
		await bot.reply(msg)

	async def show_toplist_karma(self, bot: PluginAPI):
		"""
		replies with the karma of the top users as well as the caller's place in the leaderboard
		"""
		server = None
		if not bot.context.is_pm:
			server = bot.get_guild().id
		else:
			await bot.reply("There are no leaderboards in private messages, baka!")
			return

		# temp_karma_sorted = [("232323", {"5345" : 41, "23423" : 12}),
		# ("userid", {"serverid1" : karma1, "serverid2" : karma2}, ...]
		candidates = [x for x in self._karma.items() if server in x[1]]  # filter out those that aren't in this server
		temp_karma_sorted = sorted(candidates, key=lambda usv: usv[1][server], reverse=True)  # List has format as above

		tkslen = len(temp_karma_sorted)		# Number of users in karma list

		usridx = 0  # Index of author in list before loop
		for x in temp_karma_sorted:  # Loops to calculate ranking of author
			if not x[0] == bot.get_user().id:
				usridx += 1
			else:
				break

		msg = "Sure! Here is a list of the top karma earners in this server.\n\n"
		if usridx == tkslen:		# Checks if user is in the karma list
			msg += "```{:^32.32} {:^1} | {} karma\n{:^53.49}\n".format(bot.get_user().name, "-", 0, "━"*49)
		else:
			member_name = bot.get_guild().get_member(temp_karma_sorted[usridx][0]).name
			member_amount = temp_karma_sorted[usridx][1][server]
			msg += "```{:^32.32} {:^1} | {} karma\n{:^53.49}\n".format(member_name, usridx + 1, member_amount, "━" * 49)

		for i in range(0, 5):		# Appends top 5 karma values in server if applicable
			if tkslen > i:
				snowflake_id = temp_karma_sorted[i][0]
				user_obj = bot.get_user(snowflake_id)
				if user_obj is None:
					struserid = "User " + str(type(snowflake_id))
				else:
					struserid = user_obj.name
				karmaval = temp_karma_sorted[i][1][server]
				msg += "{:^32.32} {:^1} | {} karma\n".format(struserid, i + 1, karmaval)
		msg += "```"

		await bot.reply(msg)

	def get_user_karma(self, uuid: int, global_karma: bool = False, server_id: int = 0):
		"""
		returns given user's karma
		:param uuid: The ID of the user to get the karma for.
		:param global_karma: set to true for user's global karma.
		:param server_id: server id for local karma
		"""

		amt = 0

		if uuid in self._karma:
			# convert old karma format to new karma format
			if isinstance(self._karma[uuid], int):
				self._karma[uuid] = {server_id: self._karma[uuid]}

			if global_karma:
				amt = 0
				for i in self._karma[uuid]:
					amt += self._karma[uuid][i]
			else:
				amt = self._karma[uuid].get(server_id, 0)

		if global_karma:
			msg = "<@" + str(uuid) + ">'s global karma is at " + str(amt) + "."
		else:
			msg = "<@" + str(uuid) + ">'s karma is at " + str(amt) + "."
		return msg

	async def add_user_karma(self, bot: PluginAPI, uuid, server_id, amount):
		# fix for user's still in old karma format, gives current karma
		# to the first server that requests it
		if uuid in self._karma:
			if isinstance(self._karma[uuid], int):
				self._karma[uuid] = {server_id: self._karma[uuid]}

		if uuid not in self._karma:
			self._karma[uuid] = {}
		if server_id == 0:
			self._karma[uuid][0] = 0
		elif server_id not in self._karma[uuid]:
			self._karma[uuid][server_id] = 0

		self._karma[uuid][server_id] += amount

		new_total = str(self._karma[uuid][server_id])
		_log.debug("Modified karma of user " + str(uuid) + " by " + str(amount) + "; new total " + new_total)

		tsundere_chance = await bot.get_setting('tsundere-chance')
		if random.random() < tsundere_chance and amount > 0:
			msg = "F-fine, <@" + str(uuid) + ">'s karma is now " + str(self._karma[uuid][server_id])
			msg += ". B-b-but it's not like I like"
			msg += " them or anything weird like that. So don't get the wrong idea! B-baka..."
		else:
			msg = "Okay! <@" + str(uuid) + ">'s karma is now " + str(self._karma[uuid][server_id])
		return msg


BOT_MODULE_CLASS = KarmaModule
