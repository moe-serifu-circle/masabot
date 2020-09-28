from typing import Optional

import discord

class BotContext(object):

	def __init__(self, message: Optional[discord.Message]):
		if message is not None:
			self.source = message.channel
			self.author = message.author
			self.is_pm = isinstance(message.channel, discord.DMChannel)
		else:
			self.source = None
			self.author = None
			self.is_pm = False
		self.message = message

	def mention(self):
		"""
		Gets a mention of the author that created the message.
		:return: The author
		"""
		return "<@!" + str(self.author.id) + ">"

	def author_name(self):
		return self.author.name + "#" + self.author.discriminator

	def channel_exists(self, ch_id):
		"""
		Check if the given channel ID is a channel located within the context. If the context is associated with a
		server, check if the id matches the id of a channel on the server. If the context is associated with a private
		channel, check if the ID matches the channel ID exactly.
		:type ch_id: str
		:param ch_id: The ID of the channel to check.
		:rtype: boolf
		:return: Whether the channel exists
		"""
		if self.is_pm:
			return ch_id == self.source.id
		else:
			for ch in self.source.server.channels:
				if ch.type == discord.ChannelType.text and ch.id == ch_id:
					return True
			return False

	def get_channel_name(self, ch_id):
		"""
		Get the name of a channel located within the context. If the context is associated with a server, get the name
		of the channel on the server whose id matches the given one. If the context is associated with a private
		channel, check if the ID matches the channel ID exactly, and return the name if so. Raises an exception in all
		other cases.
		:type ch_id: str
		:param ch_id: The ID of the channel to get the name for.
		:rtype: str
		:return: The name of the channel.
		"""
		if self.is_pm:
			if ch_id != self.source.id:
				raise ValueError(str(ch_id) + " is not a channel in this context")
			return self.source.name
		else:
			ch_match = None
			for ch in self.source.server.channels:
				if ch.type == discord.ChannelType.text and ch.id == ch_id:
					ch_match = ch
					break
			if ch_match is None:
				raise ValueError(str(ch_id) + " is not a channel in this context")
			return ch_match.name

	async def to_dm_context(self):
		"""
		Create a copy of this context for sending DMs to the author.
		:return: The DM context.
		"""
		dm_context = BotContext(None)
		dm_context.author = self.author
		dm_context.source = await self.author.create_dm()
		dm_context.is_pm = True
		return dm_context

	def is_nsfw(self):
		"""
		Return whether the context allows nsfw content. This will always be true in a dm context.

		:rtype: bool
		:return: Whether NSFW content is allowed.
		"""
		if self.is_pm:
			return True
		else:
			return self.source.is_nsfw()