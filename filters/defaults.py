from spam_shark import Filter, FilterResult, LinkFilter
import reddit_util, media_util

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
