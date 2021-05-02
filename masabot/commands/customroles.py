import re
from typing import Dict

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

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if bot.context.is_pm:
			raise BotModuleError("That doesn't make any sense to do in a DM!")

		enabled = await bot.get_setting('enabled')
		if not enabled:
			return
		if command == 'role-set':
			await bot.require_op("role-set")
			if len(args) < 1:
				msg = "I need to know what user you want to assign the role to, please give that after the command!"
				raise BotSyntaxError(msg)
			args = args[1:]
			target = util.parse_mention(args[0], require_type=util.MentionType.USER)
			reason = "user " + bot.get_user().display_name + " requested custom role assignment with !role-set command"
		elif command == 'role':
			user = bot.get_user()
			target = user
			reason = "user " + user.display_name + " requested custom role assignment with !role command"
		else:
			raise BotModuleError("got unknown command")

		color = "ffffff"
		if len(args) > 0:
			color = args[0].lstrip('#')
			if not re.match('^[A-Fa-f0-9]{6}$', color):
				raise BotSyntaxError("`" + str(color) + "` is not a valid 6 hex-digit color code")
		r = int(color[0:2], 16)
		g = int(color[2:4], 16)
		b = int(color[4:6], 16)
		if len(args) > 1:
			role_name = ' '.join(args[1:])
		else:
			role_name = bot.get_user().display_name
		msg = "Okay, I will give you a custom color role called `" + role_name + "` which will turn your username #"
		msg += color + ", does that sound good?"
		conf = await bot.confirm(msg)
		if conf:
			# check whether the role exists
			role = None
			for rl in bot.get_guild().roles:
				if rl.name == role_name:
					role = rl
					break
			if role is None:
				# need to create role, and assign it to variable
				guild = bot.get_guild()
				try:
					role = await guild.create_role(name=role_name, color=discord.Colour(int(color, 16)), reason=reason)
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

			if role.color.r != r or role.color.g != g or role.color.b != b:
				try:
					await role.edit(colour=discord.Colour(int(color, 16)), reason=reason)
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

			await bot.reply("Okay, I've added it!")
		else:
			await bot.reply("Sure, I'll just leave it alone ^_^")


BOT_MODULE_CLASS = CustomRoleModule
