from typing import Dict, Optional, Any

from . import BotBehaviorModule, ReactionTrigger, InvocationTrigger
from .. import util
from ..bot import PluginAPI

import discord

import logging

from ..util import BotModuleError

_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


# TODO: a lot of this module will fail if state loading fails, because it assumes that sid will exist in its
# state dicts for any server it is called in, which might not be true. add way to make it true


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
		help_text += " I'll remove it. If you want to remove *all* the roles, you can use the `!rr-clear` command"
		help_text += " instead.\n\n"
		help_text += "__Naming, Moving, And Copying__:\n"
		help_text += "To rename a role group, use the `rr-rename` command with the old name followed by the new name.\n\n"
		help_text += "To move a role group to another message, use `!rr-move` followed by the name of the group. Or if"
		help_text += "you want, you can use `!rr-copy` followed by the name of the role group and the name of the new"
		help_text += " group to copy it, which will leave it on the old message as well!\n\n"
		help_text += "If you ever need to delete a role group, use `!rr-clear` followed by the name of the group to"
		help_text += " clear. And `!rr-info` will show all the current ones that are named!"
		
		# groups is server -> group -> group_attr -> group_value.
		self._groups: Dict[int, Dict[str, Dict[str, Any]]] = dict()
		# known messages maps server -> message_id -> name of group within server, None if there isnt one
		self._known_messages: Dict[int, Dict[int, Optional[str]]] = dict()

		"""!rr-group-add
		# * give message
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
				InvocationTrigger('rr-rename'),
				InvocationTrigger('rr-copy'),
				InvocationTrigger('rr-move'),
				InvocationTrigger('rr-info'),
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
		if server not in self._groups:
			return {
				'groups': dict(),
				'messages': dict(),
			}
		# TODO 1.10.0 MIGRATION CODE, remove any time after 1.11.0
		if None in self._groups[server]:
			# noinspection PyTypeChecker
			del self._groups[server][None]
		# TODO END 1.10.0 MIGRATION CODE
		return {
			'groups': self._groups[server],
			'messages': self._known_messages[server],
		}

	def set_state(self, server: int, state: Dict):
		# TODO 1.10.x MIGRATION CODE, remove any time after 1.11.0
		if 'groups' not in state:
			state['groups'] = dict()
		if 'messages' not in state:
			state['messages'] = dict()
		# TODO END 1.10.x MIGRATION CODE
		self._groups[server] = state['groups']
		self._known_messages[server] = state['messages']

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		group = None
		if command == 'rr-add':
			if len(args) > 0:
				group = args[0]
			await self.add_reactionrole(bot, group)
		elif command == 'rr-remove':
			await self.remove_reactionrole(bot)
		elif command == 'rr-clear':
			await self.clear_reactionroles(bot)
		elif command == 'rr-rename':
			if len(args) > 0:
				group = args[0]
			await self.rename_reactionrole(bot, group)
		elif command == 'rr-copy':
			if len(args) > 0:
				group = args[0]
			new_name = None
			if len(args) > 1:
				new_name = args[1]
			await self.copy_reactionrole(bot, group, new_name)
		elif command == 'rr-move':
			if len(args) > 0:
				group = args[0]
			await self.move_reactionrole(bot, group)
		elif command == 'rr-info':
			await self.list_reactionroles(bot)

	def get_group(self, server: int, mid: int):
		return self._groups[server][self._known_messages[server][mid]]

	def set_group(self, server: int, name: Optional[str], group: Dict[str, Any]):
		group['name'] = name
		self._groups[server][name] = group

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		if reaction.user_id == bot.get_bot_id():
			return
		guild = bot.get_guild()

		msg = reaction.source_message
		if guild.id not in self._known_messages:
			return
		if msg.id not in self._known_messages[guild.id]:
			return
		if reaction.emoji not in self.get_group(guild.id, msg.id)['emotes']:
			return

		# checks done, this is a managed reaction role.
		rid = self.get_group(guild.id, msg.id)['emotes'][reaction.emoji]

		if reaction.is_remove:
			await remove_user_role(bot, reaction, rid)
		else:
			await add_user_role(bot, reaction, rid)

	async def list_reactionroles(self, bot: PluginAPI):
		sid = await bot.require_server()
		await bot.require_op("rr-info")
		if len([x for x in self._groups[sid] if x is not None]) == 0:
			await bot.reply("I don't have any reaction roles in this server yet! Use `rr-add` to create one.")
			return
		msg = "Sure! Here are all reaction role groups I currently have defined:\n\n```"
		for group in self._groups[sid]:
			if group is None:
				continue
			msg += " * " + str(group) + "\n"
		msg += "```"
		await bot.reply(msg)

	async def remove_reactionrole(self, bot: PluginAPI):
		sid = await bot.require_server()
		await bot.require_op("rr-remove")

		if sid not in self._known_messages or len(self._known_messages[sid]) < 1:
			masamsg = "I would, but there's just one problem! I'm not running any role reactions in this server,"
			masamsg += " but you can add some with `!rr-add`."
			await bot.reply(masamsg)
			return
		
		msg = await bot.select_message("Oh, I have a few of those. Can you tell me the message I should remove a role from?")
		if msg is None:
			full_msg = "I'm sorry, but I can't remove a role unless you tell me which message to remove it from!"
			full_msg += " Do `!rr-remove` to try again."
			raise BotModuleError(full_msg)

		if msg.id not in self._known_messages[sid]:
			raise BotModuleError("That is not a message with role reactions in this server!")

		gr = self.get_group(sid, msg.id)
		reacts = list(gr['emotes'].keys())
		if len(reacts) < 1:
			raise BotModuleError("I don't have any reaction roles set up on that message.")

		r = await bot.prompt_for_emote_option("Of course! And which reaction should I remove?", reacts)
		if r is None:
			raise BotModuleError("I need to know the role you want me to remove >.< Do `!rr-remove` to try again.")

		del gr['emotes'][r.emoji]
		if len(gr['emotes']) == 0:
			del self._groups[sid][gr['name']]
			del self._known_messages[sid][msg.id]
			bot.unsubscribe_reactions(msg.id)
			if len(self._known_messages[sid]) == 0:
				del self._known_messages[sid]
				del self._groups[sid]
		await msg.remove_reaction(r.emoji_value, discord.Object(bot.get_bot_id()))

		bot.save()

		full_msg = "Yes! The role is no more!"
		full_msg += " Oh, but any roles that people already had from that will not be automatically removed."
		await bot.reply(full_msg)

	async def copy_reactionrole(self, bot: PluginAPI, name: Optional[str] = None, new_name: Optional[str] = None):
		await bot.require_op("rr-copy")
		sid = await bot.require_server()

		if name is None:
			name = await bot.prompt("Which role group do you want to copy?")
			if name is None:
				raise BotModuleError("I need you to tell me the role group you want to copy!")
			name = name.lower().strip()
			if name not in self._groups[sid]:
				raise BotModuleError("That's not a group that exists, do `rr-copy` to try again!")

		sel_msg = "Okay, sure! Which message in this server should I copy the reaction role `" + name + "` to?"
		msg = await bot.select_message(sel_msg)
		if msg is None:
			err_msg = "I'm sorry but I need to know the message you want to copy the role group to!"
			err_msg += " Use `rr-copy` to try again."
			raise BotModuleError(err_msg)

		sid = msg.channel.guild.id
		if msg.id in self._known_messages[sid]:
			err_msg = "Oh, it looks like that message already has role group `" + str(self._known_messages[sid][msg.id])
			err_msg += "` on it. Please remove it before trying to put other roles on this message!"
			raise BotModuleError(err_msg)

		if new_name is None:
			new_name = await bot.prompt("And what should the name of the copy be?")
			if new_name is None:
				raise BotModuleError("I need you to tell me a name for the role group copy!")
			new_name = new_name.lower().strip()
			if new_name in self._groups[sid]:
				raise BotModuleError("That group already exists, do `rr-copy` to try again!")

		conf_msg = "Certainly, I can copy `" + name + "` there with name `" + new_name + "`. But just so you know, any"
		conf_msg += " existing user reactions will not be copied. Does that sound okay?"

		conf = await bot.confirm(conf_msg)
		if conf:
			old_group = self._groups[sid][name]
			old_mid = old_group['message']
			self._known_messages[sid][msg.id] = new_name
			self._groups[sid][new_name] = {
				'name': new_name,
				'emotes': dict(old_group['emotes']),
				'message': msg.id
			}
			bot.subscribe_reactions(msg.id)
			for emoji_code in self._groups[sid][name]['emotes']:
				emoji = await bot.get_emoji_from_value(emoji_code)
				await msg.add_reaction(emoji)
			_log.debug(util.add_context(bot.context, "Copied role group {!r} from MID {:d} to MID {:d}", name, old_mid, msg.id))
			await bot.reply("Done! I've copied it over to the new message!")
		else:
			await bot.reply("All right, I won't copy `" + name + "`.")

	async def move_reactionrole(self, bot: PluginAPI, name: Optional[str] = None):
		await bot.require_op("rr-move")
		sid = await bot.require_server()

		if name is None:
			name = await bot.prompt("Which role group do you want to move?")
			if name is None:
				raise BotModuleError("I need you to tell me the role group you want to move!")
			name = name.lower().strip()
			if name not in self._groups[sid]:
				raise BotModuleError("That's not a group that exists, do `rr-move` to try again!")

		sel_msg = "Okay, sure! Which message in this server should I move the reaction role `" + name + "` to?"
		msg = await bot.select_message(sel_msg)
		if msg is None:
			err_msg = "I'm sorry but I need to know the message you want to move the role group to!"
			err_msg += " Use `rr-move` to try again."
			raise BotModuleError(err_msg)

		sid = msg.channel.guild.id
		if msg.id in self._known_messages[sid]:
			err_msg = "Oh, it looks like that message already has role group `" + str(self._known_messages[sid][msg.id])
			err_msg += "` on it. Please remove it before trying to put other roles on this message!"
			raise BotModuleError(err_msg)

		conf_msg = "Certainly, I can move `" + name + "` there. But just so you know, any existing reactions on it"
		conf_msg += " will not be changed, and any existing by other users will not carry over. Should I move it?"

		conf = await bot.confirm(conf_msg)
		if conf:
			old_mid = self._groups[sid][name]['message']
			bot.unsubscribe_reactions(old_mid)
			del self._known_messages[sid][old_mid]
			self._known_messages[sid][msg.id] = name
			self._groups[sid][name]['message'] = msg.id
			for emoji_code in self._groups[sid][name]['emotes']:
				emoji = await bot.get_emoji_from_value(emoji_code)
				await msg.add_reaction(emoji)
			bot.subscribe_reactions(msg.id)
			_log.debug(util.add_context(bot.context, "Moved role group {!r} from MID {:d} to MID {:d}", name, old_mid, msg.id))
			await bot.reply("Done! I've moved it over to the new message!")
		else:
			await bot.reply("All right, I'll leave `" + name + "` where it is.")

	async def rename_reactionrole(self, bot: PluginAPI, name: Optional[str] = None, new_name: Optional[str] = None):
		await bot.require_op("rr-rename")

		opts = list(self._groups[bot.get_guild().id].keys())
		if len(opts) < 1:
			raise BotModuleError("I don't have any reaction role groups in this server yet! Add one with `rr-add`.")

		sid = await bot.require_server()
		if name is None:
			name = await bot.prompt("Which role group do you want to rename?")
			if name is None:
				raise BotModuleError("I need you to give me a name for the role group!")
			name = name.lower().strip()
			if name not in self._groups[sid]:
				raise BotModuleError("That group doesn't exist, do `rr-rename` try again!")

		if new_name is None:
			new_name = await bot.prompt("And what should the new name be?")
			if new_name is None:
				raise BotModuleError("I need you to tell me a name for the role group copy!")
			new_name = new_name.lower().strip()
			if new_name in self._groups[sid]:
				raise BotModuleError("That group already exists, do `rr-rename` to try again!")

		gr = self._groups[sid][name]
		del self._groups[sid][name]
		gr.name = new_name
		self._groups[sid][new_name] = gr
		self._known_messages[gr['message']] = new_name
		_log.debug(
			util.add_context(bot.context, "Renamed role group on MID {:d} from {!r} to `{!r}`", gr['message'], name, new_name)
		)

		msg = "Okay! I've renamed the role group `" + name + "` to `" + new_name + "`!"
		await bot.reply(msg)

	async def add_reactionrole(self, bot: PluginAPI, name: Optional[str] = None):
		await bot.require_op("rr-add")

		msg = await bot.select_message("Okay, sure! Which message in this server should I add a reaction role to?")
		if msg is None:
			err_msg = "I'm sorry but I don't know what message you want to set up the reactions on!"
			err_msg += " Use !rr-add to try again."
			raise BotModuleError(err_msg)

		sid = msg.channel.guild.id
		if msg.id in self._known_messages[sid]:
			name = self._known_messages[sid][msg.id]
		elif name is None:
			name = await bot.prompt("Okay! That will be a new role group, so what should I call it?")
			if name is None:
				raise BotModuleError("I need you to give me a name for the new role group!")
			name = name.lower().strip()
			if name in self._groups[sid]:
				raise BotModuleError("That group already exists, try again!")

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

		if sid not in self._known_messages:
			self._known_messages[sid] = dict()
			self._groups[sid] = dict()
		if msg.id not in self._known_messages[sid]:
			self._known_messages[sid][msg.id] = name
			self._groups[sid][name] = {
				'name': name,
				'emotes': dict(),
				'message': msg.id
			}
			bot.subscribe_reactions(msg.id)

		gr = self.get_group(sid, msg.id)
		if react.emoji in gr['emotes']:
			rid = gr[react.emoji]
			existing_role = util.Mention(util.MentionType.ROLE, rid, False)
			msg = "That emoji is already in use for the role " + str(existing_role) + "! Use !rr-add to try again."
			raise BotModuleError(msg)
		gr['emotes'][react.emoji] = role.id
		self.set_group(sid, name, gr)

		await msg.add_reaction(react.emoji_value)

		bot.save()

		await bot.reply("I have successfully set up that reaction role!")

	async def clear_reactionroles(self, bot: PluginAPI):
		await bot.require_op('rr-clear')

		sid = bot.get_guild().id
		opts = [x for x in self._groups[sid].keys() if x is not None]
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
			sid = bot.get_guild().id
			del self._known_messages[sid][self._groups[sid][sel]['message']]
			del self._groups[bot.get_guild().id][sel]
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
