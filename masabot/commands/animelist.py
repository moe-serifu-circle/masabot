from typing import Dict

from . import BotBehaviorModule, InvocationTrigger
from ..util import BotModuleError, BotSyntaxError
from ..http import HttpAgent
from .. import util
from ..bot import PluginAPI


import urllib.parse
import requests
import logging
import json.decoder


_log = logging.getLogger(__name__)
_log.setLevel(logging.DEBUG)


class WatchListModule(BotBehaviorModule):

	def __init__(self, resource_root: str):
		help_text = "This module accesses your list on Anilist for viewing and updating! You can view your Anilist"
		help_text += " entries by typing `anilist` by itself, and you can view other users' Anilists by typing their"
		help_text += " name after the command.\n\nBefore using the anilist module, you will need to give me permission"
		help_text += " to access your Anilist. To do that, use the `anilist-auth` command!\n\nIf you want, you can"
		help_text += " update the episode count using the `anilist-update` command! Just give the name of the anime"
		help_text += " you want to update, and it'll increase the number of episodes seen by 1! Oh, and if you want to"
		help_text += " set the number of episodes seen to an exact number, you can give that number after the name."
		help_text += "\n\nTo view your own anilist: `anilist`\nTo view someone else's anilist: `anilist <mention-user>`"
		help_text += ".\nTo increase the seen episode count of a current show: `anilist <show name>`\nTo set the"
		help_text += " watched episodes to an exact number: `anilist <show name> <number of eps>`.\n\nOh! One last"
		help_text += " thing! Some shows on Anilist are R-18, and not everyone wants to see that! So, if you want to"
		help_text += " work with R-18 shows through my interface, you'll have to do it either in a DM or in a channel"
		help_text += " marked as NSFW, okay?"
		super().__init__(
			name="animelist",
			desc="Manages list of current anime on Anilist",
			help_text=help_text,
			triggers=[
				InvocationTrigger("anilist"),
				InvocationTrigger("anilist-update"),
				InvocationTrigger("anilist-auth"),
			],
			resource_root=resource_root,
			has_state=True
		)

		self._anilist_users = {}
		self._anilist_clients = {}
		""":type : dict[str, HttpAgent]"""
		self._anilist_secret = ""
		self._anilist_id = ""

	def load_config(self, config):
		if 'anilist-client-id' not in config:
			raise BotModuleError("Watchlist module requires the Anilist client ID")
		if 'anilist-client-secret' not in config:
			raise BotModuleError("Watchlist module requires the Anilist client secret")
		self._anilist_secret = config['anilist-client-secret']
		self._anilist_id = config['anilist-client-id']

	def set_global_state(self, state: Dict):
		if 'anilist-users' in state:
			self._anilist_users = {int(k): v for k, v in state['anilist-users'].items()}
		for uid in self._anilist_users:
			self._anilist_clients[uid] = self._create_anilist_client(uid)

	def get_global_state(self):
		return {
			'anilist-users': self._anilist_users,
		}

	async def on_invocation(self, bot: PluginAPI, metadata: util.MessageMetadata, command: str, *args: str):
		if command == "anilist-auth":
			if bot.get_user().id not in self._anilist_users:
				await self.authorize(bot)
			else:
				await bot.reply("I already have an access token for you!")
		elif command == "anilist":
			await self._show_anilist(bot, args)
		elif command == "anilist-update":
			await self._add_anilist_episode(*args)

	async def _add_anilist_episode(self, bot: PluginAPI, *args):
		if len(args) < 1:
			raise BotSyntaxError("I need to know the name of the show you want to mark down your progress on.")
		search = args[0]
		if len(args) > 1:
			try:
				ep_count = int(args[1])
			except ValueError:
				msg = "The second argument should be the number of episodes, and " + repr(args[1]) + " is not a whole"
				msg += " number!"
				raise BotSyntaxError(msg)
		else:
			ep_count = None

		uid = bot.get_user().id
		async with bot.typing():
			anime_list = self.get_user_anime_list(uid, include_nsfw=bot.context.is_nsfw())

			matching_titles = []
			for x in anime_list:
				if x['status'] != 'REPEATING' and x['status'] != 'CURRENT':
					continue
				titles = x['media']['title']

				if titles['romaji'] is not None:
					romaji = titles['romaji'].strip().lower()
				else:
					romaji = ''

				if titles['native'] is not None:
					native = titles['native'].strip()
				else:
					native = ''

				if titles['english'] is not None:
					eng = titles['english'].strip().lower()
				else:
					eng = ''

				lower_search = search.strip().lower()
				if lower_search in romaji or lower_search in native or lower_search in eng:
					matching_titles.append(x)

			if len(matching_titles) < 1:
				msg = "I couldn't find any show on your Anilist that matches that! Be sure to go online and add it first."
				raise BotModuleError(msg)

			if len(matching_titles) > 1:
				old_matching_titles = matching_titles
				matching_titles = []
				for x in old_matching_titles:
					titles = x['media']['title']
					romaji = titles['romaji']
					native = titles['native']
					eng = titles['english']

					if romaji is None:
						romaji = ''
					if native is None:
						native = ''
					if eng is None:
						eng = ''

					if search in romaji or search in native or search in eng:
						matching_titles.append(x)

			if len(matching_titles) > 1:
				msg = "I'm sorry, but you've got multiple shows that match that in your Anilist! Can you be a bit more"
				msg += " specific?"
				raise BotModuleError(msg)

			entry = matching_titles[0]
			if ep_count is None:
				ep_count = entry['progress'] + 1

			if ep_count > entry['media']['episodes']:
				raise BotModuleError("You've already watched all the episodes in that show!")

			if ep_count == entry['media']['episodes']:
				new_state = 'COMPLETED'
			else:
				new_state = None

			new_progress, new_status = self.update_user_list_entry(uid, entry['id'], ep_count, new_state)
			msg = "Okay! I've updated your Anilist watch count for " + repr(str(entry['media']['title']['userPreferred']))
			msg += " to " + str(new_progress) + " out of " + str(entry['media']['episodes']) + " episode"
			msg += ('s' if entry['media']['episodes'] != 1 else '') + '.'
			if new_status == 'COMPLETED':
				msg += " Wow! You finished it!"
		await bot.reply(msg)

	async def _show_anilist(self, bot: PluginAPI, args):
		uid = bot.get_user().id
		if len(args) > 0:
			try:
				mention = util.parse_mention(args[0], require_type=util.MentionType.USER)
			except BotSyntaxError as e:
				msg = "I can only look up the anime lists of users, and " + repr(str(args[0])) + " is not a user!"
				raise BotSyntaxError(msg) from e
			uid = mention.id
		async with bot.typing():
			anime_list = self.get_user_anime_list(uid, include_nsfw=bot.context.is_nsfw())
			pager = util.DiscordPager("_(" + bot.mention_user() + "'s Anilist, continued)_")
			pager.add_line("Okay! Here is " + bot.mention_user() + "'s Anilist:")
			pager.add_line()
			self.format_anime_list(anime_list, pager)
		for page in pager.get_pages():
			await bot.reply(page)

	# noinspection PyMethodMayBeStatic
	def format_anime_list(self, anime_list, pager):
		sorted_by_status = {
			'CURRENT': [],
			'PLANNING': [],
			'COMPLETED': [],
			'DROPPED': [],
			'PAUSED': [],
			'REPEATING': []
		}

		for anime in anime_list:
			sorted_by_status[anime['status']].append(anime)

		def format_eps(anime_list, heading, show_eps, p):
			if len(anime_list) > 0:
				p.add_line(heading + ":")
				p.start_code_block()
				for anime in anime_list:
					list_item = '* "'
					titles = anime['media']['title']
					if titles['english'] is not None:
						list_item += titles['english']
					elif titles['romaji'] is not None:
						list_item += titles['romaji']
					else:
						list_item += titles['native']
					list_item += '"'
					if show_eps:
						list_item += ' (' + str(anime['progress']) + "/" + str(anime['media']['episodes']) + " episodes)"
					p.add_line(list_item)
				p.end_code_block()

		format_eps(sorted_by_status['CURRENT'], "Current Anime", True, pager)
		format_eps(sorted_by_status['REPEATING'], "Repeating", True, pager)
		format_eps(sorted_by_status['COMPLETED'], "Completed", False, pager)
		format_eps(sorted_by_status['PAUSED'], "On-hold", True, pager)
		format_eps(sorted_by_status['DROPPED'], "Dropped", True, pager)
		format_eps(sorted_by_status['PLANNING'], "Plan-to-watch", False, pager)

		return pager

	def update_user_list_entry(self, uid, entry_id, ep_count=None, status=None):
		if ep_count is None and status is None:
			raise ValueError("Need to set at least one value")

		self._require_auth(uid)

		gql = (
			"mutation UpdateUserAnimeEpisodes($entry_id: Int, $status: MediaListStatus, $episodes: Int) {"
			"	SaveMediaListEntry(id: $entry_id, status: $status, progress: $episodes) {"
			"		id"
			"		status"
			"		progress"
			"		media {"
			"			episodes"
			"		}"
			"	}"
			"}"
		)

		cl = self._anilist_clients[uid]
		payload = {
			'query': gql,
			'variables': {
				"entry_id": entry_id
			}
		}
		if ep_count is not None:
			payload['variables']['episodes'] = ep_count
		if status is not None:
			payload['variables']['status'] = status

		_, resp = cl.request('POST', '/', payload=payload, auth=True)
		resp: dict = resp  # for pycharm type-checker
		actual_id = resp['data']['SaveMediaListEntry']['id']

		if actual_id != entry_id:
			raise ValueError("Returned ID not same as sent ID")

		new_status = resp['data']['SaveMediaListEntry']['status']
		new_progress = resp['data']['SaveMediaListEntry']['progress']
		return new_progress, new_status

	def get_user_anime_list(self, uid, include_private=False, include_nsfw=False):
		self._require_auth(uid)

		gql = (
			"query GetAnimeList($uid: Int, $page: Int, $sort: [MediaListSort]) {"
			"	Page(page: $page, perPage: 50) {"
			"		pageInfo {"
			"			total"
			"			currentPage"
			"			lastPage"
			"			hasNextPage"
			"			perPage"
			"		}"
			"		mediaList(userId: $uid, type: ANIME, sort: $sort) {"
			"			id"
			"			status"
			"			score"
			"			progress"
			"			private"
			"			startedAt {"
			"				year"
			"				month"
			"				day"
			"			}"
			"			completedAt {"
			"				year"
			"				month"
			"				day"
			"			}"
			"			media {"
			"				episodes"
			"				title {"
			"					english"
			"					romaji"
			"					native"
			"					userPreferred"
			"				}"
			"				isAdult"
			"			}"
			"		}"
			"	}"
			"}"
		)

		full_list = []
		page = 1
		cl = self._anilist_clients[uid]
		while True:
			payload = {
				'query': gql,
				'variables': {
					"uid": self._anilist_users[uid]['id'],
					"page": page
				}
			}
			_, resp = cl.request('POST', '/', payload=payload, auth=True)
			resp: dict = resp  # for pycharm type checker
			page_list = resp['data']['Page']['mediaList']
			for x in page_list:
				if x['private'] and not include_private:
					continue
				if x['media']['isAdult'] and not include_nsfw:
					continue
				full_list.append(x)
			page_info = resp["data"]["Page"]["pageInfo"]
			if page_info['currentPage'] == page_info['lastPage']:
				break
			else:
				page += 1

		return full_list

	async def authorize(self, bot: PluginAPI):
		auth_payload = {
			'client_id': self._anilist_id,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/blob/master/docs/oauth2-authorization-code.md",
			'response_type': 'code'
		}

		p = requests.Request('GET', 'https://anilist.co/api/v2/oauth/authorize', params=auth_payload).prepare()

		bot = await bot.with_dm_context()

		msg = "Oh! You want to authorize me to use your Anilist profile? Okay! I need you go to this website"
		msg += " and tell Anilist that it's okay for me to access your profile first, okay?\n\nWhen you finish at that"
		msg += " website, tell me what the authorization code is and then I'll be able to continue!\n\n" + p.url

		await bot.reply(msg)

		code_url = await bot.prompt("What's the authorization code?", timeout=120)
		if code_url is None:
			msg = "I really need you to access that website and tell me what the code is if you want to use Anilist!"
			msg += " Let me know if you want to try again sometime, okay?"
			raise BotModuleError(msg, bot.context)

		parsed_url = urllib.parse.urlparse(code_url)
		query = urllib.parse.parse_qs(parsed_url.query)
		if 'code' not in query:
			raise BotModuleError("That URL doesn't contain a valid authorization code in it!", bot.context)
		code = query['code']

		token_payload = {
			'grant_type': 'authorization_code',
			'client_id': self._anilist_id,
			'client_secret': self._anilist_secret,
			'redirect_uri': "https://github.com/moe-serifu-circle/masabot/blob/master/docs/oauth2-authorization-code.md",
			'code': code
		}

		async with bot.typing():
			_log.debug("Sending token request to Anilist...")
			resp = requests.post('https://anilist.co/api/v2/oauth/token', data=token_payload)
			_log.debug("Response from Anilist: " + repr(resp.text))
			try:
				resp_json = resp.json()
			except json.decoder.JSONDecodeError:
				msg = "Oh no! There was a problem with that request! Anilist told me:\n```\n" + resp.text + "\n```"
				raise BotModuleError(msg)

			# TODO: actually use the 'expires-in' response object
			if 'access_token' in resp_json:
				self._anilist_users[bot.get_user().id] = {
					'token': resp_json['access_token']
				}
				self._anilist_clients[bot.get_user().id] = self._create_anilist_client(bot.get_user().id)
				_log.debug("User " + str(bot.get_user().id) + " is now authenticated to use Anilist")
				_log.debug("Getting Anilist UID...")
				_, user_data = self._anilist_clients[bot.get_user().id].request('POST', '/', auth=True, payload={
					'query': "{Viewer{id}}"
				})
				user_data: dict = user_data  # for pycharm type-checker
				anilist_id = user_data['data']['Viewer']['id']
				_log.debug("Got back UID: " + str(anilist_id))

				self._anilist_users[bot.get_user().id]['id'] = anilist_id
			else:
				msg = "There was a problem when I tried to use that authorization code! Maybe we can try again in a"
				msg += " bit?"
				raise BotModuleError(msg, bot.context)
		await bot.reply("Hooray! Now you can use my Anilist functionality!")

	def _create_anilist_client(self, uid):
		def auth_func(req):
			req.headers['Authorization'] = 'Bearer ' + self._anilist_users[uid]['token']
			return req.prepare()

		client = HttpAgent("graphql.anilist.co", ssl=True, auth_func=auth_func)

		return client

	def _require_auth(self, uid):
		if uid not in self._anilist_users:
			msg = "I haven't been given permission to access <@" + str(uid) + ">'s Anilist profile yet! But they can"
			msg += " authorize me with the `anilist-auth` command."
			raise BotModuleError(msg)


BOT_MODULE_CLASS = WatchListModule
