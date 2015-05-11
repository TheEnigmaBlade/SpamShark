from spam_shark import Filter, FilterResult, LinkFilter
import reddit_util, media_util

class YouTubeChannelFilter(Filter, LinkFilter):
	filter_id = "youtube-channel"
	
	ban_list = []
	watch_list = []
	
	def init_filter(self, configs):
		#print("Updating YouTube channel filter config...")
		self.ban_list.clear()
		self.watch_list.clear()
		
		# Update successful
		if "youtube-channel" in configs:
			if "ban" in configs["youtube-channel"]:
				self.ban_list.extend(configs["youtube-channel"]["ban"])
			if "watch" in configs["youtube-channel"]:
				self.watch_list.extend(configs["youtube-channel"]["watch"])
		
		#print("  Bans: {}".format(self.ban_list))
		#print("  Watches: {}".format(self.watch_list))
		#print("done!")
	
	def process_link(self, link, thing):
		print("Processing link: {}".format(link))
		if media_util.is_youtube_link(link):
			channel_info = media_util.get_youtube_channel(link)
			if not channel_info is None:
				print("  Channel ID={}, name={}".format(*channel_info))
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
