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
				InvocationTrigger('role-info'),
				InvocationTrigger('role-remove'),
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
			color_str = str(repl).strip()

		return parse_color(color_str)

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
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
			target = bot.get_guild(sid).get_member(target_men.id)
			color = await self.get_color_arg(bot, *args[1:])
			if len(args) > 2:
				# using role-set will always prefer to use an existing role with the given name
				role_name = ' '.join(args[2:])
			else:
				msg = "Okay, and what is the name of the role I should create and/or assign to"
				msg += " {:s}? (enter blank to remove the custom role assignment)".format(target.display_name)
				role_name = await bot.prompt(msg)
				if role_name is None:
					raise BotModuleError("I'm sorry, but if you're doing `role-set`, I really need you to answer this prompt!")
				role_name = role_name.strip()
				if role_name == '':
					await self._remove_role(bot, sid, target)
					return

			existing_role = self.get_existing_role(bot, sid, role_name)
			if existing_role:
				role_name = existing_role.name
				msg = "Okay! `@{:s}` will be updated to the given color".format(role_name)
				if existing_role.id not in [r.id for r in target.roles]:
					msg += " and assigned to {:s} as their custom role.".format(target.display_name)
					if target.id in self.custom_roles[sid]:
						cur_role = bot.get_guild(sid).get_role(self.custom_roles[sid][target.id])
						if cur_role is None:
							cur_role_name = "invalid target"
						else:
							cur_role_name = cur_role.name
						msg += " This will overwrite the existing custom role assignment of"
						msg += " `@{:s}`, but it will not".format(cur_role_name)
						msg += " automatically delete the role itself."
			else:
				msg = "Okay! `@{:s}` will be created with the given color".format(role_name)
				msg += " and assigned to {:s} as their custom role.".format(target.display_name)
				if target.id in self.custom_roles[sid]:
					cur_role = bot.get_guild(sid).get_role(self.custom_roles[sid][target.id])
					if cur_role is None:
						cur_role_name = "invalid target"
					else:
						cur_role_name = cur_role.name
					msg += " This will overwrite the existing custom role assignment of"
					msg += " `@{:s}`, but it will not".format(cur_role_name)
					msg += " automatically delete the role itself."
			msg += " Should I set `@{:s}` as the custom role for {:s}?".format(role_name, target.display_name)
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
					msg += " just use `" + target.display_name + "`.\n\nDo you want to enter a custom name for me to use?"
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
		elif command == 'role-info':
			if len(args) > 0:
				mem = bot.parse_member_mention(args[0].strip())
			else:
				mem = bot.get_guild(sid).get_member(bot.get_user().id)
			if mem.id not in self.custom_roles[sid]:
				if mem.id == bot.get_user().id:
					subj1 = "{:s}, you don't"
					subj2 = "You"
				else:
					subj1 = "{:s} doesn't"
					subj2 = "They"
				msg = subj1 + " have a custom role yet. " + subj2 + " can create one by using the `role` command."
				await bot.reply(msg.format(mem.display_name))

			if mem.id == bot.get_user().id:
				whose = "Your"
			else:
				whose = mem.display_name + "'s"
			role = bot.get_guild(sid).get_role(self.custom_roles[sid][mem.id])
			role_name = "invalid target"
			color_name = "(invalid)"
			if role is not None:
				role_name = role.name
				color_name = str(role.color)
			await bot.reply("{:s} custom role is `@{:s}` with color {:s}!".format(whose, role_name, color_name))
		elif command == 'role-remove':
			mem = bot.get_guild(sid).get_member(bot.get_user().id)
			await self._remove_role(bot, sid, mem)
		else:
			raise BotModuleError("got unknown command")

	async def _remove_role(self, bot: PluginAPI, sid: int, target: discord.Member):
		if target.id not in self.custom_roles[sid]:
			target_str = "You already don't"
			if bot.get_user().id != target.id:
				target_str = target.display_name + " already doesn't"
			await bot.reply("Oh, that's okay! {:s} have a custom role, so that's already done ^_^".format(target_str))
			return

		cur_role = bot.get_guild(sid).get_member(self.custom_roles[sid][target.id])
		del self.custom_roles[sid][target.id]
		if target.id == bot.get_user().id:
			whose = "your"
		else:
			whose = target.display_name + "'s"
		msg = "Okay, " + whose + " custom role assignment has been removed!"
		await bot.reply(msg)
		if cur_role is not None:
			if cur_role.id in [r.id for r in target.roles]:
				msg = "Now I'll remove the role itself..."
				await bot.reply(msg)
				# need to remove
				reason = "Requested by user with !role-remove command"
				if bot.get_user().id != target.id:
					reason = "Requested by {:s} with !role-set command and nil group input".format(bot.get_user().display_name)

				try:
					await target.remove_roles(cur_role, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permission to remove the `@" + cur_role.name + "` role! Please ask the staff of"
					msg += " this server to give me access to role creation in order to use this command."
					_log.exception(util.add_context(bot.context, "could not remove role ID {!r}", cur_role.name))
					raise BotModuleError(msg)

			await bot.reply("And done! Role removed.")

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
					msg = "The role to update/create, `@" + use_role.name + "`, is above my own! I can't modify it!"
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
					msg = "I don't have permissions to create your `@" + role_name + "` role! Please ask the staff of"
					msg += " this server to give me access to role creation in order to use this command."
					_log.exception(util.add_context(bot.context, "could not create role ID {!r}", role_name))
					raise BotModuleError(msg)

				# get highest bot role, we will put the new role under that
				role_priority = self.calculate_new_role_priority(bot, sid, role)
				new_pos = {
					role: role_priority
				}
				try:
					await guild.edit_role_positions(positions=new_pos, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permissions to update the position of your `@" + role_name + "` role! Please ask"
					msg += " the staff of this server to give me access to role creation in order to use this command."
					_log.exception(util.add_context(bot.context, "could not edit role positions", role_name))
					raise BotModuleError(msg)

			if role is not None and role_name is None:
				role_name = role.name

			if role.color != color or role.name != role_name:
				try:
					await role.edit(colour=color, name=role_name, reason=reason)
				except discord.Forbidden:
					msg = "I don't have permissions to access the `@" + role_name + "` role! Please ask the staff of this"
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

			whose = "your"
			if target.id != bot.get_user().id:
				whose = target.display_name + "'s"
			if role.name != role_name:
				msg = "Okay, I've updated {:s} custom role `@{:s}` to new name `@{:s}`".format(whose, role.name, role_name)
				if role.color != color:
					msg += " and updated the color from {:s} to {:s}".format(role.color, color)
				msg += "."
			elif role.color != color:
				msg = "Okay, I've updated {:s} custom role `@{:s}`'s color from {:s}".format(whose, role.name, role.color)
				msg += " to {:s}.".format(color)
			else:
				msg = "Okay, I've set {:s} custom role to `@{:s}` with color {:s} ^_^".format(whose, role.name, role.color)
			await bot.reply(msg)

	# noinspection PyMethodMayBeStatic
	def get_existing_role(self, bot: PluginAPI, sid: int, name: str) -> Optional[discord.Role]:
		"""Get an existing editable role with the given name. Returns None if none with that name exists and raises
		BotModuleError if a role with the name does exist but is not modifiable by masabot due to role ordering."""
		bot_mem: discord.Member = bot.get_guild(sid).get_member(bot.get_bot_id())
		highest_bot_role = bot_mem.roles[-1]

		too_high_fmt = "The role `{:s}` exists but it is above my own! I can't modify it!"
		too_high_fmt += " Please ask staff of this server to move the role under my role in order to use"
		too_high_fmt += " the command."

		# see if its a role mention
		try:
			men = util.parse_mention(name, util.MentionType.ROLE)
			role = bot.get_guild(sid).get_role(men.id)
			if role.position >= highest_bot_role.position:
				raise BotModuleError(too_high_fmt.format(name))
			return role
		except BotSyntaxError:
			_log.exception("Not a mention...")
			pass

		# first check to see if one with the name exists
		for rl in bot.get_guild().roles:
			if rl.name == name:
				if rl.position >= highest_bot_role.position:
					raise BotModuleError(too_high_fmt.format(name))
				return rl
		return None

	def calculate_new_role_priority(self, bot: PluginAPI, sid: int, role: discord.Role) -> int:
		bot_mem: discord.Member = bot.get_guild(sid).get_member(bot.get_bot_id())
		highest_role = bot_mem.roles[-1]
		start = highest_role.position - 1
		roles = bot.get_guild(sid).roles
		if start >= len(roles):
			raise BotModuleError("There was a problem, I didn't see any roles when I looked, give it another try.")
		for x in range(start, 1, -1):
			role_at_idx = roles[x]
			# put new roles below administrators
			if role_at_idx.permissions.administrator:
				continue
			# if its an admin, place after last admin under us
			if role.permissions.administrator:
				return x
			# otherwise put it below any that we control in the line (wont apply to mod-moved ones by design)
			if role_at_idx.id in self.custom_roles[sid].values():
				continue
			return x
		return 1


def parse_color(color_str: str) -> discord.Colour:
	color = color_str.lstrip('#')
	if not re.match('^[A-Fa-f0-9]{6}$', color):
		raise BotSyntaxError("`" + str(color) + "` is not a valid 6 hex-digit color code!")
	return discord.Colour(int(color[0:6], 16))


BOT_MODULE_CLASS = CustomRoleModule
