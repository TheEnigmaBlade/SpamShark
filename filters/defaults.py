__author__ = "Enigma"

from spam_shark import Filter, FilterResult, LinkFilter, PostFilter, safe_format
import media_util
from cache import TimedObjCache
import config
from logging import info, warning

class YouTubeChannelFilter(Filter, LinkFilter):
	"""
	Wiki configuration:
		action: "ban" or "watch" [required]
		ids: list of YouTube channel IDs or names [required]
	"""
	
	filter_id = "youtube-channel"
	filter_name = "YouTube Channel Bans and Monitors"
	filter_descr = None
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
		
		info("Bans: {}".format(self.ban_list))
		info("Watches: {}".format(self.watch_list))
		
		return False
	
	def process_link(self, link, thing):
		if media_util.is_youtube_link(link):
			channel_info = media_util.get_youtube_channel(link)
			if channel_info is None:
				warning("Failed to get channel info for \"{}\"".format(link))
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
	"""
	Wiki configuration:
		None
	"""
	
	filter_id = "youtube-votemanip"
	filter_name = "YouTube Vote Manipulation Monitoring"
	filter_descr = None
	filter_author = "Enigma"
	
	def init_filter(self, configs):
		ex = 300
		if len(configs) > 0 and "check_after" in configs:
			ex = configs["check_after"]
		info("Check after: {}".format(ex))
		self.post_cache = TimedObjCache(expiration=ex)
		
	def update(self):
		to_check = self.post_cache._prune()
		
		for url, post in to_check:
			# Video description
			desc = media_util.get_youtube_video_description(url)
			if not desc is None and self._wow_such_vote_solicitation(desc):
				yield self._get_response(url, post)
			
			# Video comments
			# Might be better to only check uploader comments
			comments = media_util.get_youtube_comments(url)
			if not comments is None:
				for comment in comments:
					if self._wow_such_vote_solicitation(comment):
						yield self._get_response(url, post)
	
	def process_post(self, post):
		if not post.is_self and media_util.is_youtube_video(post.url):
			self.post_cache.store(post.url, post)
		return False
	
	@staticmethod
	def _wow_such_vote_solicitation(text):
		text = text.lower()
		return "reddit.com/r/"+config.subreddit in text or "redd.it" in text or ("upvote" in text and "reddit" in text)
	
	@staticmethod
	def _get_response(video_url, post):
		title = "Possible YouTube vote solicitation"
		body = "Check the video description to see if they're asking for upvotes.\n\n" \
			   "* Video: {video_url}\n" \
			   "* User: {author}\n" \
			   "* Permalink: {permalink}\n"
		body = safe_format(body, video_url=video_url)
		
		return FilterResult.MESSAGE, {"log": (title, body), "modmail": (title, body)}

class YouTubeDurationFilter(Filter, PostFilter):
	"""
	Wiki configuration:
		min_duration: length in seconds [optional]
		max_duration: length in seconds [optional]
		reply: comment to leave on removed posts [optional]
	"""
	filter_id = "youtube-duration"
	filter_name = "YouTube Video Duration Filter"
	filter_descr = None
	filter_author = "Enigma"
	
	min_dur = -1
	max_dur = -1
	enabled = False
	reply = None
	
	failed_posts = []
	num_retries = 20
	
	def init_filter(self, configs):
		if len(configs) > 1:
			warning("Too many configs!")
		
		if len(configs) >= 1:
			c = configs[0]
			if "min_duration" in c:
				self.min_dur = c["min_duration"]
				info("Min duration: {}".format(self.min_dur))
			if "max_duration" in c:
				self.max_dur = c["max_duration"]
				info("Max duration: {}".format(self.max_dur))
			enabled = self.min_dur > -1 or self.max_dur > -1
			if not enabled:
				info("Not enabled because there are no settings!")
			
			if "reply" in c:
				self.reply = c["reply"]
				info("Reply:")
				info(self.reply)
			else:
				info("Removing silently")
			
		return False
	
	def update(self):
		failed = self.failed_posts[:]
		self.failed_posts.clear()
		
		for post_tuple in failed:
			post, retries = post_tuple
			result = self.process_post(post)
			if result > 0:
				yield result
			elif retries < self.num_retries:
				self.failed_posts.append((post, retries+1))
		
		yield False
	
	def process_post(self, post, add_fail=True):
		if self.enabled and not post.is_self:
			if media_util.is_youtube_video(post.url):
				print("Checking video: {}".format(post.permalink))
				length = media_util.get_youtube_video_duration(post.url)
				print("  duration = {}".format(length))
				if length is not None:
					if length > 0:
						if self.min_dur > -1 and length < self.min_dur:
							return self._get_response_min(post.url, post)
						if self.max_dur > -1 and length > self.max_dur:
							return self._get_response_max(post.url, post)
					elif add_fail:
						print("  Is none!")
						self.failed_posts.append((post, 0))
		return False
	
	def _get_response_min(self, video_url, post):
		title = "YouTube video duration too short"
		body = "This video should have been in a self post.\n\n" \
			   "* Video: {video_url}\n" \
			   "* User: {author}\n" \
			   "* Permalink: {permalink}\n"
		body = safe_format(body, video_url=video_url)
		
		reply = self.reply + "\n\n---\n\n" \
				"*This action was performed by a bot. If you believe it is a mistake, please [message the mods](https://reddit.com/message/compose?to=%2Fr%2F{subreddit}).*"
		
		print("Video too short!")
		return FilterResult.REMOVE, {"log": (title, body), "reply": reply}
	
	def _get_response_max(self, video_url, post):
		title = "YouTube video duration too long"
		body = "This video should have been in a self post.\n\n" \
			   "* Video: {video_url}\n" \
			   "* User: {author}\n" \
			   "* Permalink: {permalink}\n"
		body = safe_format(body, video_url=video_url)
		
		reply = self.reply + "\n\n---\n\n" \
				"*This action was performed by a bot. If you believe it is a mistake, please [message the mods](https://reddit.com/message/compose?to=%2Fr%2F{subreddit}).*"
		
		print("Video too long!")
		return FilterResult.REMOVE, {"log": (title, body), "reply": reply}
