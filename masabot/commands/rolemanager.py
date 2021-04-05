import asyncio

from . import BotBehaviorModule, RegexTrigger, MentionTrigger, ReactionTrigger, mention_target_self
from .. import settings, util
from ..bot import PluginAPI

import logging
import random

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

		# !rr-group-add
		# * give mesasge
		# * give roles and emotes until done
		# * give limit
		# * assign to message.
		#
		# !!rr-group-edit
		# * give message
		# * ask user add role, remove role, or edit limit?
		#   -> remove role:
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
		# * group is removed from message

		super().__init__(
			name="rolemanager",
			desc="Allows for the creation of self-assignable roles.",
			help_text=help_text,
			triggers=[
				ReactionTrigger(reacts=True, unreacts=True),
				InvocationTrigger('rr-add'),
				InvocationTrigger('rr-remove'),
			],
			resource_root=resource_root,
			has_state=False  # sic; we set has_state to False but still handle state as we manually manipulate that with setting has_state prior to calling api.save() as a temporary hack
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

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		if reaction.is_from_this_client:
			return
		guild = bot.get_guild()
		msg = reaction.message
		if guild.id not in self._role_messages:
			return
		if msg.id not in self._role_messages[guild.id]:
			return
		if reaction.index not in self._role_messages[guild.id][msg.id]:
			return

		# checks done, this is a managed reaction role.
		rid = self._role_messages[guild.id][msg.id][reaction.index]

		if reaction.action == 'remove':
			await self.remove_user_role(reaction, rid)
		elif reaction.action == 'add':
			await self.add_user_role(reaction, rid)

	async def add_user_role(self, bot: PluginAPI, reaction: util.Reaction, role_id: int):
		g = bot.get_guild()
		role = g.get_role(role_id)
		mem = g.get_member(reaction.user.id)

		if role is None:
			raise BotModuleError("Role does not exist: RID " + str(role_id))

		if mem is None:
			raise BotModuleError("User is not a member of this guild: UID " + str(reaction.user.id))

		if role not in mem.roles:
			await mem.add_roles(role, reason="Reaction roles request")
			await mem.send("Okay! I've added the role `@" + role.name + "` to you in " + g.name + "! To remove it, just remove your reaction!")

	async def remove_user_role(self, bot: PluginAPI, reaction: util.Reaction, role_id: int):
		g = bot.get_guild()
		role = g.get_role(role_id)
		mem = g.get_member(reaction.user.id)

		if role is None:
			raise BotModuleError("Role does not exist: RID " + str(role_id))

		if mem is None:
			raise BotModuleError("User is not a member of this guild: UID " + str(reaction.user.id))

		if role not in mem.roles:
			await mem.add_roles(role, reason="Reaction roles request")
			await mem.send("Okay! I've added the role `@" + role.name + "` to you in " + g.name + "! To remove it, just remove your reaction!")


	async def remove_reactionrole(self, bot: PluginAPI):
		sid = bot.require_server()
		bot.require_op("rr-remove")
		if sid not in self._role_messages or len(self._role_messages[sid]) < 1:
			await bot.reply("I would, but there's just one problem! I'm not running any role reactions in this server, but you can add some with `!rr-add`.")
			return
		
		msg = await bot.select_message("Oh, I have a few of those. Can you tell me the message I should remove a role from?")
		if msg is None:
			raise BotModuleError("I'm sorry, but I can't remove a role unless you tell me which message to remove it from! Do `!rr-remove` to try again.")

		if msg.id not in self._role_messages[sid]:
			raise BotModuleError("That is not a message in this server!")

		reacts = self._role_messages[sid][msg.id].keys()
		if len(reacts) < 1:
			raise BotModuleError("I don't have any reaction roles set up on that message.")

		r = await bot.prompt_for_emote_option("Of course! And which reaction should I remove?", reacts)
		if r is None:
			raise BotModuleError("I need to know the role you want me to remove >.< Do `!rr-remove` to try again.")

		del self._role_messages[sid][selected_mid][r.index]:

		if isinstance(r.index, str):
			await msg.remove_reaction(r.index)
		else:
			emoji = self._bot.client.get_emoji(r.index)
			await msg.remove_reaction(emoji)

		self.has_state = True
		bot.save()
		self.has_state = False

		await bot.reply("Yes! The role is no more! Oh, but any roles that people already had from that will not be automatically removed.")

	async def add_reactionrole(self, bot: PluginAPI):
		bot.require_op("rr-add")
		msg = await bot.select_message("Okay, sure! Which message in this server should I remove a reaction role from?")
		if msg is None:
			raise BotSyntxError("I'm sorry but I don't know what message you want to set up the reactions on! Use !rr-add to try again.'")

		rolemsg = await bot.prompt("Got it! And what role do you want to add?")
		if rolemsg is None:
			raise BotSyntaxError("I'm sorry but I don't know what role you want to add. Use !rr-add to try again.")
		role = util.parse_mention(rolemsg)
		if not role.is_role:
			raise BotSyntaxError("It doesn't look like that's a role, and I need a role to continue! Use !rr-add to try again.")

		react = await bot.prompt_for_emote("Okay! And what emoji should people react with to get that role?")
		if react is None:
			raise BotSyntaxError("I'm sorry but I don't know what emoji you want me to add. Use !rr-add to try again.")
		if not react.is_usable:
			raise BotSyntaxError("Oh no, it looks like I can't use that emote, is it from another server? Use !rr-add to try again.")

		if msg.channel.guild.id not in self._role_messages:
			self._role_messages[msg.channel.guild.id] = dict()
		if msg.id not in self._role_messages[msg.channel.guild.id]:
			self._role_messages[msg.channel.guild.id][msg.id] = dict()
			prev = str(msg.content)
			if len(prev) > 100:
				prev = prev[:100]
			self._message_previews[msg.id] = prev

		if react.index in self._role_messages[msg.channel.guild.id][msg.id]:
			rid = self._role_messages[msg.channel.guild.id][msg.id][react.index]
			existing_role = util.Mention(util.MentionType.ROLE, rid)
			raise BotSyntaxError("That emoji is already in use for the role " + str(existing_role) + "! Use !rr-add to try again.")

		self._role_messages[msg.channel.guild.id][msg.id][react.index] = role.id

		await bot.context.message.add_reaction(react.original)

		self.has_state = True
		bot.save()
		self.has_state = False

		await bot.reply("I have successfully set up that reaction role!")

	
	async def on_mention(self, bot: PluginAPI, metadata, message: str, mentions):
		await self._handle_mention(bot, message)

	# noinspection PyMethodMayBeStatic
	async def _handle_mention(self, bot: PluginAPI, message_text: str):
		analysis_chunks = message_to_analyzable_chunks(message_text)
		if len(analysis_chunks) < 1:
			return
		worst_sentiment = None
		neutral_present = False
		for message_text in analysis_chunks:
			sentiment = noticeme_analysis.analyze_sentiment(message_text)
			if sentiment == 0:
				neutral_present = True
				continue  # neutrals are checked next if no other is found
			if worst_sentiment is None:
				worst_sentiment = sentiment
			elif sentiment < worst_sentiment:
				worst_sentiment = sentiment
		if worst_sentiment is not None:
			_log.debug("got a mention; sentiment score is {:d}".format(worst_sentiment))
			if worst_sentiment > 0:
				if noticeme_analysis.contains_thanks(
						message_text, bot.get_bot_id(), "masabot", "masa", "masachan", "masa-chan"):
					reply_text = random.choice(positive_thanks_responses)
				else:
					reply_text = random.choice(positive_responses)
				await bot.reply(reply_text)
			elif worst_sentiment < 0:
				await bot.reply(random.choice(negative_responses))
		elif neutral_present:
			if random.random() < await bot.get_setting('neutral_reaction_chance'):
				emoji_text = random.choice(neutral_mention_reactions)
				min_reaction_delay_ms = await bot.get_setting('min_reaction_delay_ms')
				max_reaction_delay_ms = await bot.get_setting('max_reaction_delay_ms')
				# give a slight delay
				# random amount from min to max ms
				delay = min_reaction_delay_ms + (random.random() * (max_reaction_delay_ms - min_reaction_delay_ms))
				await asyncio.sleep((delay / 1000))
				await bot.react(emoji_text)


def message_to_analyzable_chunks(text: str):
	chunks = []
	paras = text.split('\n')
	for p in paras:
		sents = p.split('.')
		candidate = None
		has_more_than_one = False
		for s in sents:
			if s.strip(" \t\n\r\v") != "":
				if candidate is None:
					candidate = s
				else:
					has_more_than_one = True
					break
		if not has_more_than_one and candidate is not None:
			chunks.append(candidate)
	return chunks


BOT_MODULE_CLASS = RoleManagerModule