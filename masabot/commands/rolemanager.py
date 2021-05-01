from typing import Dict

from . import BotBehaviorModule, ReactionTrigger, InvocationTrigger
from .. import util
from ..bot import PluginAPI

import discord

import logging

from ..util import BotModuleError

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class RoleManagerModule(BotBehaviorModule):
	def __init__(self, resource_root: str):
		help_text = "The \"rolemanager\" module makes it so I can assign people roles by having them react to a message!"
		help_text += "Anybody who can see the message where the reaction roles are set up will be able to get the role by"
		help_text += " reacting to that message with the right emoji!\n\n"
		help_text += "My operators in a server can create and manage reaction roles with special commands.\n\n"
		help_text += "__Adding A Reaction Role__:\n"
		help_text += "To make a new role message, first create the message you want and put it in any channel that I"
		help_text += " can see. Then, use the `rr-add` command. This will ask what message to add the reaction role to."
		help_text += " You can either give me a link to the message or give the ID of the message directly!\n\n"
		help_text += "Next, I'll ask you for what role you want people to get when they react; you can reply by pinging"
		help_text += " that role in your response!\n\n"
		help_text += "Finally, I'll need the emote that people need to react with to get the role. But, be careful! It"
		help_text += " has to be something that everyone in the server can use, so it's gotta be an emote uploaded to"
		help_text += " your server, or else one of the built-in emotes.\n\n"
		help_text += "And that's it! To add more roles to the same message, just run the `rr-add` command again!\n\n"
		help_text += "__Removing A Reaction Role__:\n"
		help_text += "To remove a role from an existing message, use the `rr-remove` command. This will ask you what"
		help_text += " message to remove the role from. You can either give me a link to the message or the ID of the"
		help_text += " message directly!\n\n"
		help_text += "Next, I'll need to know which role you want to remove. Select the one you want to remove, and"
		help_text += " I'll remove it.\n\n"
		help_text += "And that's it! Repeat as many times as you need!"

		self._role_messages = dict()

		"""!rr-group-add
		# * give mesasge
		# * give roles and emotes until done
		# * give limit
		# * assign to message.
		#
		# !!rr-group-edit
		# * give message
		# * ask user add role, remove role, or edit limit?
		#   -> remove role
		#		give role to remove by reacting to this message (which has copy)
		#	-> add role:
		#		give role to add via ping
		#		give emote to add via react
		#	-> edit limit:
		#		warn if lowering - some users may already have multiple roles
		#		prompt for new limit
		#		set	new limit
		#
		# !!rr-group-remove
		# * ask user to select from the messages it is watching
		# * user selects
		# * group is removed from message"""

		super().__init__(
			name="rolemanager",
			desc="Allows for the creation of self-assignable roles.",
			help_text=help_text,
			triggers=[
				ReactionTrigger(reacts=True, unreacts=True),
				InvocationTrigger('rr-add'),
				InvocationTrigger('rr-remove'),
				InvocationTrigger('rr-clear'),
			],
			resource_root=resource_root,
			save_state_on_trigger=False,
			# sic; we set has_state to False but still handle state as we manually manipulate
			# that with setting has_state prior to calling api.save() as a temporary hack
		)

	def get_state(self, server: int) -> Dict:
		"""
		If server is not a server that the module has a state for, return a default state.
		:param server:
		:return:
		"""
		if server not in self._role_messages:
			return {
				'messages': dict(),
			}
		return {
			'messages': self._role_messages[server],
		}

	def set_state(self, server: int, state: Dict):
		self._role_messages[server] = state['messages']

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == 'rr-add':
			await self.add_reactionrole(bot)
		elif command == 'rr-remove':
			await self.remove_reactionrole(bot)
		elif command == 'rr-clear':
			await self.clear_reactionroles(bot)

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		if reaction.user_id == bot.get_bot_id():
			return
		guild = bot.get_guild()

		msg = reaction.source_message
		if guild.id not in self._role_messages:
			return
		if msg.id not in self._role_messages[guild.id]:
			return
		if reaction.emoji not in self._role_messages[guild.id][msg.id]:
			return

		# checks done, this is a managed reaction role.
		rid = self._role_messages[guild.id][msg.id][reaction.emoji]

		if reaction.is_remove:
			await remove_user_role(bot, reaction, rid)
		else:
			await add_user_role(bot, reaction, rid)

	async def remove_reactionrole(self, bot: PluginAPI):
		sid = await bot.require_server()
		await bot.require_op("rr-remove")

		if sid not in self._role_messages or len(self._role_messages[sid]) < 1:
			masamsg = "I would, but there's just one problem! I'm not running any role reactions in this server,"
			masamsg += " but you can add some with `!rr-add`."
			await bot.reply(masamsg)
			return
		
		msg = await bot.select_message("Oh, I have a few of those. Can you tell me the message I should remove a role from?")
		if msg is None:
			full_msg = "I'm sorry, but I can't remove a role unless you tell me which message to remove it from!"
			full_msg += " Do `!rr-remove` to try again."
			raise BotModuleError(full_msg)

		if msg.id not in self._role_messages[sid]:
			raise BotModuleError("That is not a message with role reactions in this server!")

		reacts = self._role_messages[sid][msg.id].keys()
		if len(reacts) < 1:
			raise BotModuleError("I don't have any reaction roles set up on that message.")

		r = await bot.prompt_for_emote_option("Of course! And which reaction should I remove?", reacts)
		if r is None:
			raise BotModuleError("I need to know the role you want me to remove >.< Do `!rr-remove` to try again.")

		del self._role_messages[sid][msg.id][r.emoji]
		if len(self._role_messages[sid][msg.id]) == 0:
			del self._role_messages[sid][msg.id]
			bot.unsubscribe_reactions(msg.id)
			if len(self._role_messages[sid]) == 0:
				del self._role_messages[sid]
		await msg.remove_reaction(r.emoji_value, discord.Object(bot.get_bot_id()))

		bot.save()

		full_msg = "Yes! The role is no more!"
		full_msg += " Oh, but any roles that people already had from that will not be automatically removed."
		await bot.reply(full_msg)

	async def add_reactionrole(self, bot: PluginAPI):
		await bot.require_op("rr-add")
		msg = await bot.select_message("Okay, sure! Which message in this server should I add a reaction role to?")
		if msg is None:
			err_msg = "I'm sorry but I don't know what message you want to set up the reactions on!"
			err_msg += " Use !rr-add to try again."
			raise BotModuleError(err_msg)

		rolemsg = await bot.prompt("Got it! And what role do you want to add?")
		if rolemsg is None:
			raise BotModuleError("I'm sorry but I don't know what role you want to add. Use !rr-add to try again.")
		role = util.parse_mention(rolemsg)
		if not role.is_role:
			raise BotModuleError("It doesn't look like that's a role, and I need a role to continue! Use !rr-add to try again.")

		react = await bot.prompt_for_emote("Okay! And what emoji should people react with to get that role?")

		if react is None:
			raise BotModuleError("I'm sorry but I don't know what emoji you want me to add. Use !rr-add to try again.")
		if not react.is_usable:
			err_msg = "Oh no, it looks like I can't use that emote, is it from another server?"
			err_msg += " Use !rr-add to try again."
			raise BotModuleError(err_msg)

		if msg.channel.guild.id not in self._role_messages:
			self._role_messages[msg.channel.guild.id] = dict()
		if msg.id not in self._role_messages[msg.channel.guild.id]:
			self._role_messages[msg.channel.guild.id][msg.id] = dict()
			bot.subscribe_reactions(msg.id)

		if react.emoji in self._role_messages[msg.channel.guild.id][msg.id]:
			rid = self._role_messages[msg.channel.guild.id][msg.id][react.emoji]
			existing_role = util.Mention(util.MentionType.ROLE, rid, False)
			msg = "That emoji is already in use for the role " + str(existing_role) + "! Use !rr-add to try again."
			raise BotModuleError(msg)
		self._role_messages[msg.channel.guild.id][msg.id][react.emoji] = role.id

		await msg.add_reaction(react.emoji_value)

		bot.save()

		await bot.reply("I have successfully set up that reaction role!")

	async def clear_reactionroles(self, bot: PluginAPI):
		await bot.require_op('rr-clear')

		opts = list(self._role_messages[bot.get_guild().id].keys())
		# TODO: abstract away the concept of "more than one option" and also abstract concept of auto-choosing 1 if only
		# one and not presenting choice if choices are empty.
		if len(opts) < 1:
			await bot.reply("I don't have any reaction roles defined on any messages! You can use !rr-add to make one.")
			return
		elif len(opts) == 1:
			sel = opts[0]
		else:
			opt1 = opts[0]
			opt2 = opts[1]
			other_opts = []
			if len(opts) > 2:
				other_opts = opts[2:]
			q = "Which message ID should I clear all reaction roles from?"
			sel = await bot.prompt_for_option(q, opt1, opt2, *other_opts)
			if sel is None:
				raise BotModuleError("Sorry, but I need to know what MID you want me to operate on!")

		conf = await bot.confirm("Just to double check, you want me to delete ALL reaction roles on that message, right?")
		if conf:
			del self._role_messages[bot.get_guild().id][sel]
			bot.save()
			bot.unsubscribe_reactions(sel)
			await bot.reply("Okay! They have been removed.")
		else:
			await bot.reply("I'll leave the role reactions alone for now.")


async def add_user_role(bot: PluginAPI, reaction: util.Reaction, role_id: int):
	g = bot.get_guild()
	role = g.get_role(role_id)
	mem = g.get_member(reaction.user.id)

	if role is None:
		raise BotModuleError("Role does not exist: RID " + str(role_id))

	if mem is None:
		raise BotModuleError("User is not a member of this guild: UID " + str(reaction.user.id))

	if role not in mem.roles:
		await mem.add_roles(role, reason="Reaction roles request")
		reply_msg = "Okay! I've added the role `@" + role.name + "` to you in " + g.name + "!"
		reply_msg += " To remove it, just remove your reaction!"
		await mem.send(reply_msg)


async def remove_user_role(bot: PluginAPI, reaction: util.Reaction, role_id: int):
	g = bot.get_guild()
	role = g.get_role(role_id)
	mem = g.get_member(reaction.user.id)

	if role is None:
		raise BotModuleError("Role does not exist: RID " + str(role_id))

	if mem is None:
		raise BotModuleError("User is not a member of this guild: UID " + str(reaction.user.id))

	if role in mem.roles:
		await mem.remove_roles(role, reason="Reaction roles request")
		reply_msg = "Okay! I've removed the role `@" + role.name + "` from you in " + g.name + "!"
		reply_msg += " To have it added again, you can react once more!"
		await mem.send(reply_msg)


BOT_MODULE_CLASS = RoleManagerModule
