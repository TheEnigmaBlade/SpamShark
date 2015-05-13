from spam_shark import Filter, FilterResult, LinkFilter, PostFilter
import reddit_util, media_util
from cache.cache import TimedObjCache

class YouTubeChannelFilter(Filter, LinkFilter):
	filter_id = "youtube-channel"
	
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
					return FilterResult.REMOVE, self._get_ban_info(channel_info, thing)
				if channel_info[0] in self.watch_list or channel_info[1] in self.watch_list:
					return FilterResult.MESSAGE, self._get_watch_info(channel_info, thing)
				
		return False
	
	@staticmethod
	def _get_ban_info(channel_info, thing):
		channel_id, channel_name = channel_info
		user = thing.author.name
		permalink = thing.permalink
		
		title = "Banned YouTube channel: {}".format(channel_name)
		body = "A banned channel was removed.\n\n" \
				"* Channel: {} ({})\n" \
				"* User: /u/{}\n" \
				"* Permalink: {}" \
					.format(channel_name, channel_id, user, reddit_util.reduce_reddit_link(permalink))
		
		return {"log": (title, body), "modmail": (title, body)}
	
	@staticmethod
	def _get_watch_info(channel_info, thing):
		channel_id, channel_name = channel_info
		user = thing.author.name
		permalink = thing.permalink
		
		title = "Monitored YouTube channel: {}".format(channel_name)
		body = "A monitored channel was submitted.\n\n" \
				"* Channel: {} ({})\n" \
				"* User: /u/{}\n" \
				"* Permalink: {}" \
					.format(channel_name, channel_id, user, permalink)
		
		return {"log": (title, body)}

class YouTubeVoteManipFilter(Filter, PostFilter):
	filter_id = "youtube-votemanip"
	
	def init_filter(self, configs):
		self.post_cache = TimedObjCache(expiration=300)
	
	def update(self):
		to_check = self.post_cache._prune()
		
		if len(to_check) > 0:
			print("Checking descriptions of {} videos".format(len(to_check)))
			
		for url, post in to_check:
			print("  URL: ".format(url))
			desc = media_util.get_youtube_video_description(url)
			if "reddit.com" in desc or "redd.it" in desc:
				print("    WOW! Vote solicitation!")
				user = post.author.name
				permalink = post.permalink
				
				title = "Possible YouTube vote solicitation"
				body = "Check the video description to see if they're asking for upvotes.\n\n" \
					   "* Video: {}\n" \
					   "* User: {}\n" \
					   "* Permalink: {}\n" \
					   		.format(url, user, reddit_util.reduce_reddit_link(permalink))
				return FilterResult.MESSAGE, {"modmail": (title, body)}, post
	
	def process_post(self, post):
		if not post.is_self and media_util.is_youtube_video(post.url):
			print("Storing video for later!")
			self.post_cache.store(post.url, post)
		return False
