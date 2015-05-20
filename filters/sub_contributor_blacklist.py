__author__ = "Enigma"

from spam_shark import Filter, FilterResult, PostFilter, CommentFilter, safe_format
from functools import lru_cache
import reddit_util

class SubContributorBlacklist(Filter, PostFilter, CommentFilter):
	filter_id = "sub-blacklist"
	filter_name = "Subreddit Contributor Blacklist"
	filter_descr = "Removes submissions from contributors to blacklisted subreddits"
	filter_author = "Enigma"
	
	def init_filter(self, configs):
		if len(configs) < 1:
			print("Warning: config block needed")
		elif len(configs) > 1:
			print("Warning: only one config block needed")
		else:
			config = configs[0]
			if "blacklist" in config:
				self.blacklist = config["blacklist"]
	
	def process_comment(self, comment):
		subs = self._get_user_subreddits(comment.author)
		for sub in subs:
			if sub in self.blacklist:
				return self._get_response(sub)
		return False
	
	def process_post(self, post):
		subs = self._get_user_subreddits(post.author)
		for sub in subs:
			if sub in self.blacklist:
				return self._get_response(sub)
		return False
	
	@staticmethod
	def _get_response(bl_subreddit):
		title = "Blacklisted subreddit contributor"
		body = "A contributor to a blacklisted subreddit was removed.\n\n" \
			   "* Blacklisted subreddit: {bl_sub}" \
			   "* User: {author}\n" \
			   "* Permalink: {permalink}\n"
		body = safe_format(body, bl_sub=bl_subreddit)
		
		return FilterResult.REMOVE, {"log": (title, body)}
	
	# Utilities
	
	_thing_to_sub = lambda t: t.subreddit.name
	
	@classmethod
	@lru_cache(maxsize=512)
	def _get_user_subreddits(cls, user):
		comments = reddit_util.get_all_comments(user, limit=100)
		posts = reddit_util.get_all_submitted(user, limit=100)
		return set(map(comments, cls._thing_to_sub)).union(set(map(posts, cls._thing_to_sub)))
