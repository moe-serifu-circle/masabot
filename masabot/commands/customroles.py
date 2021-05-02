import re
from typing import Dict, Optional

import discord

from . import BotBehaviorModule, InvocationTrigger
from ..util import BotSyntaxError, BotModuleError
from .. import util, settings
from ..bot import PluginAPI


import logging


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class CustomRoleModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "This lets you make a role to change your name color! You can also give it a custom name. Do `role`"
		help_text += " followed by the color you want in hex code, like `#ff0022`, then after that write the name of the"
		help_text += " role. If you are having trouble, just do `role` by itself and I'll help you!\n\n"
		help_text += "If you don't like the custom role, you can run it again and I'll be happy to help you change it!\n\n"
		help_text += "Operators should ensure I have the right permissions for role creation and management for a user"
		help_text += " before turning this on.\n\n"
		help_text += "Oh, also! Operators can use `role-set SERVER_MEMBER [hex color] [role name...]` to assign a server"
		help_text += " member a role that already exists, or to change the role that is mapped to the user to another"
		help_text += " one.\n\n"
		help_text += "__Settings__\n"
		help_text += "* `enabled` - Whether this is turned on. This starts disabled, meaning I will do nothing when the"
		help_text += " commands for this module are called. When turned on, `role` can be used by everyone and"
		help_text += " `role-set` can be used by operators."

		# custom_roles goes server -> user -> role_id
		self.custom_roles: Dict[int, Dict[int, int]] = dict()

		super().__init__(
			name="customroles",
			desc="Create a custom color and name role.",
			help_text=help_text,
			triggers=[
				InvocationTrigger('role'),
				InvocationTrigger('role-set'),
			],
			resource_root=resource_root,
			server_only_settings=[
				settings.Key(settings.key_type_toggle, 'enabled', default=False),
			],
			save_state_on_trigger=True
		)

	def get_state(self, server: int) -> Dict:
		if server not in self.custom_roles:
			return {
				'roles': dict(),
			}
		return {
			'roles': self.custom_roles[server],
		}

	def set_state(self, server: int, state: Dict):
		self.custom_roles[server] = state['roles']

	# noinspection PyMethodMayBeStatic
	async def get_color_arg(self, bot: PluginAPI, *args: str) -> discord.Colour:
		"""
		Parse color argument from the first arg in args, or if not present, asks the user for one.
		:param bot:
		:param args:
		:return:
		"""
		if len(args) > 0:
			color_str = args[0]
		else:
			msg = "What color should the role be? Oh, and could you tell me with a six-digit hex code, like #ff0022?"
			repl = await bot.prompt(msg)
			if repl is None:
				raise BotModuleError("I really need to know what color the role should be!")
			color_str = repl

		return parse_color(color_str)

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if bot.context.is_pm:
			raise BotModuleError("That doesn't make any sense to do in a DM!")

		enabled = await bot.get_setting('enabled')
		if not enabled:
			return

		sid = await bot.require_server()
		if sid not in self.custom_roles:
			self.custom_roles[sid] = dict()
		if command == 'role-set':
			await bot.require_op("role-set")
			if len(args) < 1:
				msg = "I need to know what user you want to assign the role to, please give that after the command!"
				raise BotSyntaxError(msg)
			target_men = util.parse_mention(args[0], require_type=util.MentionType.USER)
			target = await bot.get_guild(sid).get_member(target_men.id)
			color = await self.get_color_arg(bot, *args[1:])
			if len(args) > 2:
				# using role-set will always prefer to use an existing role with the given name
				role_name = ' '.join(args[2:])
			else:
				msg = "Okay, and what is the name of the role I should create and/or assign to"
				msg += " {:s}?".format(target.display_name)
				role_name = await bot.prompt(msg)
				if role_name is None:
					raise BotModuleError("I'm sorry, but if you're doing `role-set`, I really need to know the name of the role!")
			existing_role = self.get_existing_role(bot, sid, role_name)
			if existing_role:
				msg = "Okay! `{:s}` will be updated to the given color".format(role_name)
				if existing_role.id not in [r.id for r in target.roles]:
					msg += " and assigned to {:s} as their custom role.".format(target.display_name)
					if target.id in self.custom_roles[sid]:
						cur_role = bot.get_guild(sid).get_role(self.custom_roles[sid][target.id])
						msg += " This will overwrite the existing custom role assignment of"
						msg += " `{:s}`, but it will not".format(cur_role.name)
						msg += " automatically delete the role itself."
			else:
				msg = "Okay! `{:s}` will be created with the given color".format(role_name)
				msg += " and assigned to {:s} as their custom role.".format(target.display_name)
				if target.id in self.custom_roles[sid]:
					cur_role = bot.get_guild(sid).get_role(self.custom_roles[sid][target.id])
					msg += " This will overwrite the existing custom role assignment of"
					msg += " `{:s}`, but it will not".format(cur_role.name)
					msg += " automatically delete the role itself."
			msg += " Should I set `{:s}` as the custom role for {:s}?".format(role_name, target.display_name)
			conf = await bot.confirm(msg)
			if not conf:
				await bot.reply("Got it! I'll leave it alone for now!")
				return
			await self._assign_role(bot, sid, target, color, role_name, use_role=existing_role)
		elif command == 'role':
			user = bot.get_user()
			target: discord.Member = bot.get_guild(sid).get_member(user.id)
			existing_role = None
			color = await self.get_color_arg(bot, *args)
			if len(args) > 1:
				role_name = ' '.join(args[1:])
				if target.id in self.custom_roles[sid]:
					existing_role = bot.get_guild(sid).get_role(self.custom_roles[sid][target.id])
			else:
				# if target has never been assigned or it HAS but for some reason the server returns nothing for the
				# assigned ID and so needs a new one
				if (
						target.id not in self.custom_roles[sid] or
						bot.get_guild(sid).get_role(self.custom_roles[sid][target.id]) is None
				):
					msg = "Okay, looks like you don't have a custom role assigned yet, so I'll make one for you. If you"
					msg += " want, I can make it super special and call it something custom just for you! Or if not, I'll"
					msg += " just use `" + target.display_name + "`.\n\nDo want to enter a custom name for me to use?"
					conf = await bot.confirm(msg)
					if conf:
						role_name = await bot.prompt("What should the name be?")
						if role_name is None:
							raise BotModuleError("I need to know what you want the custom name to be")
					else:
						await bot.reply("All right, I'll use `" + target.display_name + "`")
						role_name = target.display_name
				else:
					rid = self.custom_roles[sid][target.id]
					existing_role = bot.get_guild(sid).get_role(rid)
					role_name = existing_role.name
			await self._assign_role(bot, sid, target, color, role_name, use_role=existing_role)
		else:
			raise BotModuleError("got unknown command")

	# noinspection PyMethodMayBeStatic
	async def _assign_role(
			self,
			bot: PluginAPI,
			sid: int,
			target: discord.Member,
			color: discord.Colour,
			role_name: str,
			use_role: Optional[discord.Role]
	):
		if bot.get_user().id != target.id:
			reason = "user " + bot.get_user().display_name + " requested custom role assignment for"
			reason += " " + target.display_name + " with role-set command"
		else:
			reason = "user " + bot.get_user().display_name + " requested custom role use/modification with role command"

		with bot.typing():
			if use_role is not None:
				bot_mem: discord.Member = bot.get_guild(sid).get_member(bot.get_bot_id())
				highest_bot_role = bot_mem.roles[-1]
				if use_role.position >= highest_bot_role.position:
					msg = "The role to update/create, `" + use_role.name + "`, is above my own! I can't modify it!"
					msg += " Please ask staff of this server to move the role under my role in order to use"
					msg += " the command."
					raise BotModuleError(msg)
				role = use_role
			else:
				# need to create role, and assign it to variable
				guild = bot.get_guild(sid)
				try:
					role = await guild.create_role(name=role_name, color=color, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permissions to create your `" + role_name + "` role! Please ask the staff of"
					msg += " this server to give me access to role creation in order to use this command."
					_log.exception(util.add_context(bot.context, "could not create role ID {!r}", role_name))
					raise BotModuleError(msg)

				# get highest bot role, we will put the new role under that
				bot_mem: discord.Member = guild.get_member(bot.get_bot_id())
				highest_bot_role = bot_mem.roles[-1]
				new_pos = {
					highest_bot_role: highest_bot_role.position,
					role: highest_bot_role.position - 1
				}
				try:
					await guild.edit_role_positions(positions=new_pos, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permissions to update the position of your `" + role_name + "` role! Please ask"
					msg += " the staff of this server to give me access to role creation in order to use this command."
					_log.exception(util.add_context(bot.context, "could not edit role positions", role_name))
					raise BotModuleError(msg)

			if role is not None and role_name is None:
				role_name = role.name

			if role.color != color or role.name != role_name:
				try:
					await role.edit(colour=color, name=role_name, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permissions to access the `" + role_name + "` role! Please ask the staff of this"
					msg += " server to give me access in order to use this command."
					_log.exception(util.add_context(bot.context, "could not access role ID {:d} {!r}", role.id, role.name))
					raise BotModuleError(msg)

			# check whether user has role
			m: discord.Member = bot.get_guild().get_member(target.id)
			if role.id not in [x.id for x in m.roles]:
				# add role to user
				try:
					await m.add_roles(role, reason=reason)
				except discord.Forbidden:
					log_msg = "could not add role ID {:d} {!r} to user {:d} {!r}"
					_log.exception(util.add_context(bot.context, log_msg, role.id, role.name), m.id, m.display_name)
					msg = "I don't have permissions to add role `" + role_name + "` to you! Please ask the staff of this"
					msg += " server to give me access and ensure the roles are properly ordered in order to use this"
					msg += " command."
					raise BotModuleError(msg)

			self.custom_roles[sid][target.id] = role.id
			await bot.reply("Okay, I've added it! ^_^")

	# noinspection PyMethodMayBeStatic
	def get_existing_role(self, bot: PluginAPI, sid: int, name: str) -> Optional[discord.Role]:
		"""Get an existing editable role with the given name. Returns None if none with that name exists and raises
		BotModuleError if a role with the name does exist but is not modifiable by masabot due to role ordering."""
		bot_mem: discord.Member = bot.get_guild(sid).get_member(bot.get_bot_id())
		highest_bot_role = bot_mem.roles[-1]
		# first check to see if one with the name exists
		for rl in bot.get_guild().roles:
			if rl.name == name:
				if rl.position >= highest_bot_role.position:
					msg = "The role `" + name + "` exists but it is above my own! I can't modify it!"
					msg += " Please ask staff of this server to move the role under my role in order to use"
					msg += " the command."
					raise BotModuleError(msg)
				return rl
		return None


def parse_color(color_str: str) -> discord.Colour:
	color = color_str.lstrip('#')
	if not re.match('^[A-Fa-f0-9]{6}$', color):
		raise BotSyntaxError("`" + str(color) + "` is not a valid 6 hex-digit color code!")
	return discord.Colour(int(color[0:6], 16))


BOT_MODULE_CLASS = CustomRoleModule
