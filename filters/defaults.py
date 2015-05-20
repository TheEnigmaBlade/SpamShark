__author__ = "Enigma"

from spam_shark import Filter, FilterResult, LinkFilter, PostFilter, safe_format
import media_util
from cache import TimedObjCache
import config

class YouTubeChannelFilter(Filter, LinkFilter):
	filter_id = "youtube-channel"
	filter_name = "YouTube Channel Bans and Monitors"
	filter_descr = ""
	filter_author = "Enigma"
	
	ban_list = []
	watch_list = []
	
	def init_filter(self, configs):
		self.ban_list.clear()
		self.watch_list.clear()
		
		# Update successful
		for config in configs:
			ids = config["ids"]
			action = config["action"]
			if action == "ban":
				self.ban_list.extend(ids)
			if action == "watch":
				self.watch_list.extend(ids)
		
		print("Bans: {}".format(self.ban_list))
		print("Watches: {}".format(self.watch_list))
		
		return False
	
	def process_link(self, link, thing):
		if media_util.is_youtube_link(link):
			channel_info = media_util.get_youtube_channel(link)
			if channel_info is None:
				print("Warning: failed to get channel info for \"{}\"".format(link))
			else:
				# Check channel ID and name
				if channel_info[0] in self.ban_list or channel_info[1] in self.ban_list:
					return FilterResult.REMOVE, self._get_ban_info(channel_info)
				if channel_info[0] in self.watch_list or channel_info[1] in self.watch_list:
					return FilterResult.MESSAGE, self._get_watch_info(channel_info)
				
		return False
	
	@staticmethod
	def _get_ban_info(channel_info):
		channel_id, channel_name = channel_info
		title = "Banned YouTube channel: {}".format(channel_name)
		body = "A banned channel was removed.\n\n" \
				"* Channel: {channel_name} ({channel_id})\n" \
				"* User: {author}\n" \
				"* Permalink: {permalink}"
		body = safe_format(body, channel_name=channel_name, channel_id=channel_id)
		
		return {"log": (title, body), "modmail": (title, body)}
	
	@staticmethod
	def _get_watch_info(channel_info):
		channel_id, channel_name = channel_info
		title = "Monitored YouTube channel: {}".format(channel_name)
		body = "A monitored channel was submitted.\n\n" \
				"* Channel: {channel_name} ({channel_id})\n" \
				"* User: {author}\n" \
				"* Permalink: {permalink}"
		body = safe_format(body, channel_name=channel_name, channel_id=channel_id)
		
		return {"log": (title, body)}

class YouTubeVoteManipFilter(Filter, PostFilter):
	filter_id = "youtube-votemanip"
	filter_name = "YouTube Vote Manipulation Monitoring"
	filter_descr = ""
	filter_author = "Enigma"
	
	def init_filter(self, configs):
		self.post_cache = TimedObjCache(expiration=300)
	
	def update(self):
		to_check = self.post_cache._prune()
		
		for url, post in to_check:
			# Video description
			desc = media_util.get_youtube_video_description(url)
			if not desc is None and self._wow_such_vote_solicitation(desc):
				return self._get_response(url, post)
			
			# Video comments
			# Might be better to only check uploader comments
			comments = media_util.get_youtube_comments(url)
			if not comments is None:
				for comment in comments:
					if self._wow_such_vote_solicitation(comment):
						return self._get_response(url, post)
		
		return False
	
	def process_post(self, post):
		if not post.is_self and media_util.is_youtube_video(post.url):
			self.post_cache.store(post.url, post)
		return False
	
	@staticmethod
	def _wow_such_vote_solicitation(text):
		return "reddit.com/r/"+config.subreddit in text or "redd.it" in text
	
	@staticmethod
	def _get_response(video_url, post):
		title = "Possible YouTube vote solicitation"
		body = "Check the video description to see if they're asking for upvotes.\n\n" \
			   "* Video: {video_url}\n" \
			   "* User: {author}\n" \
			   "* Permalink: {permalink}\n"
		body = safe_format(body, video_url=video_url)
		
		return FilterResult.MESSAGE, {"modmail": (title, body)}, post
