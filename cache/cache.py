from collections import deque, Iterable, OrderedDict
from abc import ABCMeta, abstractmethod
from time import time
import bz2, pickle, os, sys

#sys.path.append(os.path.join(os.path.dirname(__file__), "cache"))
#sys.path.append(os.path.dirname(__file__))

def load_cached_storage(cache_file, default_size=1000):
	if cache_file is not None and os.path.exists(cache_file):
		print("Loading cache: {0}".format(cache_file))
		with bz2.open(cache_file, "rb") as file:
			try:
				cache = pickle.load(file)
				return cache
			except pickle.PickleError and EOFError:
				return None
	return ThingCache(cache_size=default_size, file=cache_file)

class Cache(Iterable, metaclass=ABCMeta):
	def __init__(self, cache_file):
		self.cache_file = cache_file
	
	def __setitem__(self, key, value):
		pass
	
	@abstractmethod
	def __iter__(self):
		return None
	
	@abstractmethod
	def data(self):
		return None
	
	def save(self):
		if self.cache_file is not None:
			with bz2.open(self.cache_file, "wb") as file:
				pickle.dump(self, file)

class TimedObjCache(Cache):
	def __init__(self, expiration=3600, file=None):
		super().__init__(file)
		
		self._data =  OrderedDict()
		self.expiration = expiration
	
	def _prune(self):
		old = []
		for key in self._data.keys():
			data, added = self._data[key]
			time_since = time() - added
			if time_since >= self.expiration:
				old.append((key, self._data[key]))
				del self._data[key]
			else:
				break
		return old
	
	def get(self, key):
		self._prune()
		
		if key in self._data.keys():
			return self._data[key][0]
		return None
	
	def store(self, key, data):
		self._data[key] = (data, time())
	
	def data(self):
		return self._data
	
	def __iter__(self):
		self._data.__iter__()

class ThingCache(Cache):
	def __init__(self, cache_size=1000, file=None):
		super().__init__(file)
		
		self._post_ids = deque()
		self._post_ids_max = cache_size
	
	def _add_post_ids(self, post_ids):
		#Remove old posts
		new_len = len(self._post_ids) + len(post_ids)
		if new_len > self._post_ids_max:
			for n in range(0, new_len - self._post_ids_max):
				self._post_ids.popleft()
		#Add new posts
		for postID in post_ids:
			self._post_ids.append(postID)
		
		self.save()
	
	def get_diff(self, posts):
		posts = list(posts)
				
		#Get IDs not in the cache
		new_post_ids = [post.id for post in posts]
		new_post_ids = list(set(new_post_ids).difference(set(self._post_ids)))
				
		#Get new posts from IDs
		new_posts = []
		for postID in new_post_ids:
			for post in posts:
				if post.id == postID:
					new_posts.append(post)
		
		#Update cache
		self._add_post_ids(new_post_ids)
		
		return new_posts
	
	def data(self):
		return self._post_ids
	
	def __iter__(self):
		return self._post_ids.__iter__()
	
