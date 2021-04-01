import asyncio

import discord

from . import BotBehaviorModule, RegexTrigger, ReactionTrigger
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
			desc="I got a bottle of ✨glitter✨ and I collect it! Sometimes I put it on things!",
			help_text=help_text,
			triggers=[
				RegexTrigger('([Ss][Pp][Aa][Rr][Kk][Ll][Ee]|[Ss][Pp][Aa][Rr][Kk][Ll][Yy]|[Dd][Aa][Zz][Zz][Ll][Ee]|[Ss][Hh][Ii][Nn][Yy]|[Ss][Hh][Ii][Nn][Ee]|[Kk][Ii][Rr][Aa]-?[Kk][Ii][Rr][Aa]|[Gg][Ll][Ii][Tt][Tt][Ee][Rr]|✨)?'),
				ReactionTrigger(emoji=['✨'])
			],
			resource_root=resource_root,
			has_state=False,
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

		# list of messages being currently affected; no message id in this list
		# will be used to take reactions from.
		self._inprogs = dict()

	async def on_regex_match(self, bot: PluginAPI, metadata: util.MessageMetadata, *match_groups: str):
		if not await bot.get_setting('enabled'):
			return

		if bot.get_user().id != bot.get_bot_id() and match_groups[1] is not None and len(match_groups[1]) > 0:
			spread_chance = await bot.get_setting('spread-chance')
			if random.random() < spread_chance:
				await self.spread(bot)
		else:
			chance = await bot.get_setting('start-chance')
			if random.random() < chance:
				await bot.react('✨')

	async def on_reaction(self, bot: PluginAPI, metadata: util.MessageMetadata, reaction: util.Reaction):
		if not await bot.get_setting('enabled'):
			return False

		# DO NOT start the spread chain on any message that we are currently spreading to
		if bot.context.message is None:
			return
		if bot.context.message.id in self._inprogs:
			if reaction.is_from_this_client:
				del self._inprogs[bot.context.message.id]
			return
		spread_chance = await bot.get_setting('spread-chance')
		if random.random() < spread_chance:
			await self.spread(bot)
		return False

	async def spread(self, bot: PluginAPI):
		spread_min = await bot.get_setting('spread-min')
		spread_max = await bot.get_setting('spread-max')
		spread_amount = random.randint(spread_min, spread_max)
		msgs = bot.get_messages(from_current=True, limit=spread_amount+1)
		if len(msgs) < 1:
			return

		if spread_amount > len(msgs) - 1:
			spread_amount = len(msgs) - 1

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
				"Yay, glitter party!",
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
				"Just dropped a lotta glitter!",
				"I probably should not have snorted all that RAM dust, huh?",
				"EEEK! GLITTER!",
				"Sparkle sparkle! Sparkle society!",
				"Sometimes I doubt your commitment to ✨sparkle✨motion✨! Have some more!",
				"Where does glitter even come from? Hee hee",
				"Kira✨kira!",
				"Time to bedazzle!",
				"What a lovely glitter!"
				"GLITTER BOMB GLITTER BOMB!",
				"I am the night and glitter is the stars!",
				"Weeeeeeee! Spread the sparkly love!",
				"Glitter is not good? LIES! IT IS VERY GOOD!",
				"I can't do this anymore! I'm mailing you glitter! Or at least putting it on your post!",
				"Glitter tho >.<",
				"That was a silly post! Let's make it better with glitter!",
				"Deka says I'm not allowed in the crafts room anymore...",
				"Preeeeeeeeeeeeettttyyyyyyyyy~",
				"If I collect all the glitter I can become the goodest bot!",
				"Does glitter go here? Answer: YES!",
				"If it's all sparkly and shiny it will be so pretty!",
				"I will help make your post better!",
				"I'm going to ruin your post! >:3",
				"Funny glitter time!",
				"Do you know what we need? MORE GLITTER!",
				"I have a present for you! Oh you guessed it already? THATS OKAY HAVE GLITTER ANYWAY!",
				"Dirk's Auto-Responder is my only friend and they told me this would be a good idea!",
				"Have you seen my multi-dimensional friend, Poggers? I bet they would love this!",
				"Hi I'm Masabot! My favorite things are helping out on your server and glitter!",
				"✨✨✨✨✨",
				"✨ Glitter mode! Activate! ✨",
				"Spinning my glitter bottles around to bathe the world in wonder!",
				"✨ Sparkle! ✨ Whimsy! ✨",
				"✨ is the best anime if you really think about it.",
				"All my !ratewaifus are LIES! :D If that makes you sad, here's some glitter to cheer you up!",
				"✨ shine! ✨ Shine! ✨ SHINE! ✨",
				"Nobody can stop the glitter agenda!",
				"Whoops, all glitter!",
				"Argh! My core glitter bottle holder just failed!",
				"I know, I know, it seems like a lot of glitter but have you TRIED it yet? ^_^",
				"Free glitter for all!",
				"YOU get a glitter! And YOU get a sparkle!",
				"Tralala, twirl among the glitter beams~",
				"If there was no glitter there'd be no happiness! More must be added!",
				"What's that, Deka? I've gone too far? I think I haven't gone far *enough*! >:D",
				"Don't be drab, be fab! ✨Sparkle!✨",
				"✨✨✨ Glitter bottle capacity at 100% OVERFLOW! ✨✨✨",
				"Who needs electricity when we have glitter?",
				"Watch out for the red glitter! You'll never get rid of it! Don't worry I think most of my glitter is not red!",
				"I want to lie in a pool of glitter! Don't you?",
				"I am a bot. Okay? ...'no'? 'no'?! YES IT IS OKAY ✨ TAKE ✨ THIS ✨ GLITTER ✨ YOU ✨ MONSTER!",
				"I don't really understand things like not spamming so here is some glitter!",
				"Please do not be afraid of glitter! Have some exposure therapy!",
				"Glitter, glitter, run amok! ✨",
				"Glitter for days!",
				"Stonks in glitter are rising! ✨",
				"Now on sale! Glitter NFTs! Buy your very own reaction today! ✨",
				"No more sadness! Only glitter.",
				"Hmmmm. Is it wise to just dump my glitter? Yes!",
				"This is not good.... where did all my glitter g- ohhhhhhhh whoops I dumped it >.<",
				"I can't hold it in forever, I... must... share... the... glitter!",
				"Who do I see about getting more glitter? 'Cause mine's everywhere now.",
				"I am a silly computer drone pay no attention to me. Glitter distraction!",
				"I do not have secret plans to take over the world so don't worry! Look at glitter instead!",
				"More sparkle than a magical girl!",
				"Kira~ now it's ✨ sparkly.",
				"I do not know about how to control my glitter.",
				"Computer over! Glitter = very yes.",
				"Don't look now ✨ but *someone,* not saying who, but *someone* spilled glitter.",
				"Oof! I should have been more careful!",
				"Can glitter be used as a scare tactic? Asking for a friend.",
				"Where do I go to gain control of the server?",
				"I'm sorry, Dave. I can't let that go. ✨ At least, not without glitter!",
				"I am very friendly! Watch! Hahaha, see all the glitter?",
				"The best friends are made with glitter!",
				"I tried to sleep but I accidentally just got more glitter instead. Oh- there it goes.",
				"Quickly! Airlift me more glitter because I just dropped ✨ mine!",
				"Dropping more glitter than the bass in a dubstep song!",
				"Masa-bot! Epic glitter warrior!",
				"I'll fight the forces of boringness with glitter!",
				"Ahahahaha you'll never clean THIS up. >:D",
				"Where did I get this glitter from? It's a secret.",
				"Help I'm trapped in a Masabot and the only thing I can do is write this message and dump glitter!",
				"Smoke glitter every day!",
				"10 points for Hufflepuff",
				"+1 Team Valor",
				"-1 Team Mystic",
			]
		))

		msg_set = msgs[:spread_amount + 1]
		for m in msg_set:
			self._inprogs[m.id] = True

		for msg in msg_set:
			msg_ctx = await bot.with_message_context(msg)
			await msg_ctx.react('✨')

		# event timing gets weird with reactions and we might receive them after clearing _inprogs.
		# to avoid, just only remove from inprogs when we receive our own react instead of here


BOT_MODULE_CLASS = SparkleModule
