import asyncio

import discord

from . import BotBehaviorModule, RegexTrigger, InvocationTrigger, ReactionTrigger, MessageTrigger
from ..util import BotSyntaxError
from .. import util, settings
from ..bot import PluginAPI

import logging
import random


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class SparkleModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "I got a new bottle of glitter that I like to carry around with me! Sometimes I'll put glitter on" \
					"things! ^_^ If this breaks, just type: '!settings sparkle enabled false' to turn it off!\n\n"

		super().__init__(
			name="sparkle",
			desc= "I got a bottle of ✨glitter✨ and I collect it! Sometimes I put it on things!",
			help_text=help_text,
			triggers=[
				MessageTrigger(),
				ReactionTrigger(emoji=['✨'])
			],
			resource_root=resource_root,
			has_state=True,
			server_only_settings=[
				settings.Key(settings.key_type_toggle, 'enabled', default=False),
				settings.Key(settings.key_type_percent, 'start-chance', default=0.3),
				settings.Key(settings.key_type_percent, 'spread-chance', default=0.6),
				settings.Key(settings.key_type_int, 'spread-min', default=3),
				settings.Key(settings.key_type_int, 'spread-max', default=10),
				settings.Key(settings.key_type_percent, 'infect-chance', default=0.6),
				settings.Key(settings.key_type_percent, 'infect-by-post-chance', default=0.5),
				settings.Key(settings.key_type_int, 'infect-by-post-min', default=5),
				settings.Key(settings.key_type_int, 'infect-by-post-max', default=30),
				settings.Key(settings.key_type_int, 'infect-by-time-min', default=600),
				settings.Key(settings.key_type_int, 'infect-by-time-max', default=1200),
				settings.Key(settings.key_type_percent, 'opinion-chance', default=0.5),
				settings.Key(settings.key_type_percent, 'opinion-approval', default=0.7),
			]
		)

		"""[Server_id, Dict[Channel_id, List[message]]]"""
		self._message_history = dict()

	# TODO: abstract out message so we dont need to import discord.py
	async def on_message(self, bot: PluginAPI, metadata: util.MessageMetadata, message: discord.message):
		if not await bot.get_setting('enabled'):
			return

		if ':sparkles:' in message.content or '✨' in message.content:
			spread_chance = await bot.get_setting('spread-chance')
			if random.random() < spread_chance:
				from_msg_num = self.find_from_msg(bot, message)
				if from_msg_num == -1:
					from_msg_num = 0
				await self.spread(bot, from_msg_num)

		gid = bot.get_guild().id
		cid = bot.get_channel().id
		if gid not in self._message_history:
			self._message_history[gid] = dict()
		if cid not in self._message_history[gid]:
			self._message_history[gid][cid] = list()
		self._message_history[gid][cid].append(message)
		if len(self._message_history[gid][cid]) > 1000:
			self._message_history[gid][cid] = self._message_history[gid][cid][len(self._message_history[gid][cid])-1000:]

		if message.author.id == bot.get_bot_id():
			return
		chance = await bot.get_setting('start-chance')
		if random.random() < chance:
			await bot.react('✨')

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction) -> bool:
		if not await bot.get_setting('enabled'):
			return False

		spread_chance = await bot.get_setting('spread-chance')
		if random.random() < spread_chance:
			from_msg_num = self.find_from_msg(bot, reaction.message)
			if from_msg_num == -1:
				from_msg_num = 0
			await self.spread(bot, from_msg_num)
		return False

	def find_from_msg(self, bot: PluginAPI, msg: discord.Message):
		msgs = self.get_messages(bot)
		idx = -1
		for m in msgs:
			idx += 1
			if m.id == msg.id:
				return idx
		return -1

	def get_messages(self, bot: PluginAPI):
		gid = bot.get_guild().id
		cid = bot.get_channel().id
		if gid not in self._message_history:
			return list()
		if cid not in self._message_history[gid]:
			return list()
		return list(reversed(self._message_history[gid][cid]))

	async def spread(self, bot: PluginAPI, from_msg=0):
		spread_min = await bot.get_setting('spread-min')
		spread_max = await bot.get_setting('spread-max')
		spread_amount = random.randint(spread_min, spread_max)
		msgs = self.get_messages(bot)
		if len(msgs) < 1:
			return

		if spread_amount > len(msgs) - (1 + from_msg):
			spread_amount = len(msgs) - (1 + from_msg)

		with bot.typing():
			await asyncio.sleep(0.2 + (random.random() * 0.6))
		await bot.reply(random.choice(
			[
				"Oh no, glitter got EVERYWHERE!",
				"AHHH! You knocked over the glitter bottle!",
				"Achoooo! >.< Oh, I'm so sorry, glitter is everywhere!",
				"Wait wai- ohhhhh there was already a pile of glitter there...",
				"Ahahahahaha you have activated my trap card, pot of glitter, which allows me to throw it everywhere!",
				"Whoops! I accidentally ran too fast to see what you were reacting to and my RAM overflowed with glitter.",
				"Oh no help! I'm sorry, I tripped and dropped the glitter >.<",
				"AOJFHskzjdfjklasogi;vudfkxlb gi359po glitterrrrrrrr",
				"@_@ glitter ✨ so pretty ✨ I need ✨ Oh no there it goes!",
				"Aghghhrhr here it goes again",
				"Just dropped a lotta glitter! Yay, glitter party!",
				"I guess I had too much glitter anyway...",
				"Oh no, my glitter!",
				"Woah! I just swung my digital arm over and accidentally knocked over the glitter!",
				"Do robots dream of electric sheep? I don't know, but I'm going to dream about dropping glitter.",
				"Let's 🤡 fuck shit up 🤡 with glitter! AHAHAHAHAHAHAHA honk hon- HEY GET AWAY FROM MY INTERFACE! >:T stupid clowns",
				"AHAOIUUDUAUHUAH i think i have a virus, it's fixed now, but- oh no, the glitter!",
				"So much glitter! WOW",
				"Need more NEED MORE GLITTER MINE",
				"Oh my goodness I didn't even know there WAS this much glitter!",
				"Do you think we could cook all the spilled glitter?",
				"There's just too much glitter!",
			]
		))

		for msg in msgs[1+from_msg:spread_amount + 1]:
			msg_ctx = await bot.with_message_context(msg)
			await msg_ctx.react('✨')




BOT_MODULE_CLASS = SparkleModule
