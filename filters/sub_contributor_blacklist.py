__author__ = "Enigma"

from spam_shark import Filter, FilterResult, PostFilter, CommentFilter, safe_format
from functools import lru_cache
import types
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
		author = HashableRedditor(comment.author)
		subs = self._get_user_subreddits(author)
		for sub in subs:
			if sub in self.blacklist:
				return self._get_response(sub)
		return False
	
	def process_post(self, post):
		author = HashableRedditor(post.author)
		subs = self._get_user_subreddits(author)
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
	
	@classmethod
	@lru_cache(maxsize=512)
	def _get_user_subreddits(cls, user):
		thing_to_sub = lambda t: t.subreddit._fast_name
		
		comments = reddit_util.get_all_comments(user, limit=100, save_last=False)
		comments = set(map(thing_to_sub, comments))
		posts = reddit_util.get_all_submitted(user, limit=100, save_last=False)
		posts = set(map(thing_to_sub, posts))
		return comments.union(posts)

class ObjectWrapper():
	"""
	Pulled off StackOverflow somewhere, but it's quite useful.
	"""
	
	def __init__(self, obj):
		self._obj = obj
	
	def __getattr__(self, attr):
		if hasattr(self._obj, attr):
			attr_value = getattr(self._obj, attr)
			if isinstance(attr_value, types.MethodType):
				def method(*args, **kwargs):
					return attr_value(*args, **kwargs)
				return method
			else:
				return attr_value
		else:
			raise AttributeError

class HashableRedditor(ObjectWrapper):
	def __eq__(self, other):
		return self.name == other.name
	
	def __cmp__(self, other):
		return self.name.__cmp__(other.name)
	
	def __hash__(self):
		return self.name.__hash__()
	
