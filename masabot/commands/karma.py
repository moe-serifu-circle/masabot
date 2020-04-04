from . import BotBehaviorModule, RegexTrigger, InvocationTrigger
from ..util import BotSyntaxError
from .. import util

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
		help_text += "Additionally, if you want to check the karma leaderboard for this server, you can view it by"
		help_text += " invoking `karma-top` with no arguments.\n\n"
		help_text += "If you would like to see a user's global karma (or your own global karma), simply add a `global`"
		help_text += " to the end of the command (e.g. `karma global` to see your own, `karma @user global` to see"
		help_text += " another user's global karma). \n\nIn order to prevent huge karma changes, there is a buzzkill mode," 
		help_text += " which limits the amount that karma can change by. The `karma-buzzkill` command with no arguments"
		help_text += " will give what the current buzzkill limit is, and ops are able to give an argument to set the limit."
		help_text += " Setting the limit to anything less than 1 disables buzzkill mode entirely, allowing any amount of"
		help_text += " karma change."

		super().__init__(
			bot_api,
			name="karma",
			desc="Tracks user reputation",
			help_text=help_text,
			triggers=[
				RegexTrigger(r'<([#@])([!&]?)(\d+)>\s*(\+\++|--+)$'),
				InvocationTrigger('karma'),
				InvocationTrigger('karma-buzzkill'),
				InvocationTrigger('karma-top')
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
		loaded_dict = state.get('karma', {})
		for idx in loaded_dict:
			self._karma[int(idx)] = loaded_dict[idx]
		self._buzzkill_limit = state['buzzkill']
		if 'tsundere-chance' in state:
			self._tsundere_chance = state['tsundere-chance']

	async def on_invocation(self, context, metadata, command, *args):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type command: str
		:type args: str
		"""
		if command == "karma":
			await self.show_karma(context, args)
		elif command == "karma-buzzkill":
			await self.configure_buzzkill(context, args)
		elif command == "karma-top":
			await self.show_toplist_karma(context)

	async def on_regex_match(self, context, metadata, *match_groups):
		"""
		:type context: masabot.bot.BotContext
		:type metadata: masabot.util.MessageMetadata
		:type match_groups: str
		"""
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

		if amount is not None:

			if user == context.author.id:
				msg = "You cannot set karma on yourself!"
			elif abs(amount) > self._buzzkill_limit > 0:
				msg = "Buzzkill mode enabled;"
				msg += " karma change greater than " + str(self._buzzkill_limit) + " not allowed"
			else:
				if context.is_pm:
					msg = self.add_user_karma(user, 0, amount)
				else:
					msg = self.add_user_karma(user, context.source.guild.id, amount)
		if msg is not None:
			await self.bot_api.reply(context, msg)

	async def show_karma(self, context, args):
		"""
		replys with given user's karma, by default displays the local karma
		(karma only from current server)
		:type context: masabot.bot.BotContext
		:type args: str
		"""

		if not context.is_pm:
			server = context.source.guild.id
		else:
			server = 0

		global_karma = False
		if len(args) > 1 and args[1].lower() == "global":
			global_karma = True

		if len(args) >= 1:
			try:
				mention = util.parse_mention(args[0])
			except BotSyntaxError:
				if args[0].lower() == "global":
					msg = self.get_user_karma(context.author.id, server_id=server, global_karma=True)
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
			msg = self.get_user_karma(context.author.id, server_id=server, global_karma=global_karma)
		await self.bot_api.reply(context, msg)
	
	async def show_toplist_karma(self, context):
		"""
		replies with the karma of the top users as well as the caller's place in the leaderboard
		:type context: masabot.bot.BotContext
		""" 
		server = None
		if not context.is_pm:
			server = context.source.guild.id
		else:
			await self.bot_api.reply(context, "There are no leaderboards in private messages, baka!")
			return

		# temp_karma_sorted = [("232323", {"5345" : 41, "23423" : 12}),
		# ("userid", {"serverid1" : karma1, "serverid2" : karma2}, ...]
		temp_karma_sorted = sorted(self._karma.items(), key=lambda usv: usv[1][server], reverse=True)  # List has format as above
		
		tkslen = len(temp_karma_sorted)		# Number of users in karma list

		usridx = 0  # Index of author in list before loop
		for x in temp_karma_sorted:  # Loops to calculate ranking of author
			if not x[0] == context.author.id:
				usridx += 1
			else:
				break

		msg = "Sure! Here is a list of the top karma earners in this server.\n\n"
		if usridx == tkslen:		# Checks if user is in the karma list
			msg += "```{:^32.32} {:^1} | {} karma\n{:^53.49}\n".format(context.author.name, "-", 0, "━"*49)
		else:
			member_name = context.source.guild.get_member(temp_karma_sorted[usridx][0]).name
			member_amount = temp_karma_sorted[usridx][1][server]
			msg += "```{:^32.32} {:^1} | {} karma\n{:^53.49}\n".format(member_name, usridx + 1, member_amount, "━" * 49)
		
		for i in range(0, 5):		# Appends top 5 karma values in server if applicable
			if tkslen > i:
				snowflake_id = temp_karma_sorted[i][0]
				user_obj = self.bot_api.get_user(snowflake_id)
				if user_obj is None:
					struserid = "User " + str(type(snowflake_id))
				else:
					struserid = user_obj.name
				karmaval = temp_karma_sorted[i][1][server]
				msg += "{:^32.32} {:^1} | {} karma\n".format(struserid, i + 1, karmaval)
		msg += "```"

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

	def add_user_karma(self, uuid, server_id, amount):
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

		_log.debug("Modified karma of user " + str(uuid) + " by " + str(amount) + "; new total " + str(self._karma[uuid][server_id]))

		if random.random() < self._tsundere_chance and amount > 0:
			msg = "F-fine, <@" + str(uuid) + ">'s karma is now " + str(self._karma[uuid][server_id]) + ". B-b-but it's not like I like"
			msg += " them or anything weird like that. So don't get the wrong idea! B-baka..."
		else:
			msg = "Okay! <@" + str(uuid) + ">'s karma is now " + str(self._karma[uuid][server_id])
		return msg


BOT_MODULE_CLASS = KarmaModule
