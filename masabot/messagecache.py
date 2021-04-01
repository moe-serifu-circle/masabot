from typing import Callable, List
import discord


class MessageHistoryCache(object):
	def __init__(self, get_limit: Callable[[], int]):
		self._guilds = dict()
		self._dms = dict()
		self._groups = dict()
		self.get_limit = get_limit

	def save(self, message: discord.Message):
		ch = message.channel
		if isinstance(ch, discord.TextChannel):
			gid = ch.guild.id
			cid = ch.id
			if gid not in self._guilds:
				self._guilds[gid] = dict()
			if cid not in self._guilds[gid]:
				self._guilds[gid][cid] = list()
			self._guilds[gid][cid].append(message)
			if len(self._guilds[gid][cid]) > self.get_limit():
				start = len(self._guilds[gid][cid]) - self.get_limit()
				self._guilds[gid][cid] = self._guilds[gid][cid][start:]
		elif isinstance(ch, discord.DMChannel):
			uid = ch.recipient.id
			if uid not in self._dms:
				self._dms[uid] = list()
			self._dms[uid].append(message)
			if len(self._dms[uid]) > self.get_limit():
				start = len(self._dms[uid]) - self.get_limit()
				self._dms[uid] = self._dms[uid][start:]
		elif isinstance(ch, discord.GroupChannel):
			cid = ch.id
			if cid not in self._groups:
				self._groups[cid] = list()
			self._groups[cid].append(message)
			if len(self._groups[cid]) > self.get_limit():
				start = len(self._groups[cid]) - self.get_limit()
				self._groups[cid] = self._groups[cid][start:]
		else:
			raise TypeError("Cannot handle unknown message type in history cache: " + str(type(ch)))

	def for_channel(self, guild_id: int, channel_id: int) -> List[discord.Message]:
		if guild_id not in self._guilds:
			return list()
		if channel_id not in self._guilds[guild_id]:
			return list()
		return list(reversed(self._guilds[guild_id][channel_id]))

	def for_dm(self, user_id: int) -> List[discord.Message]:
		if user_id not in self._dms:
			return list()
		return list(reversed(self._dms[user_id]))

	def for_group(self, group_id: int) -> List[discord.Message]:
		if group_id not in self._groups:
			return list()
		return list(reversed(self._groups[group_id]))