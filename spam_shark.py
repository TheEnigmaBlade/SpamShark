#!/usr/bin/env python3
from abc import ABCMeta, abstractmethod
from enum import IntEnum, unique
from requests import HTTPError
import sys, yaml, re, traceback
from threading import Thread, Event
from praw.errors import ModeratorRequired, ModeratorOrScopeRequired

import config, reddit_util, media_util
from cache.cache import load_cached_storage

# Globals
r = None

##################
# Initialization #
##################

def build_local_config():
	config.subreddit = config.subreddit.lower()
	config.user_whitelist = [s.lower() for s in config.config_whitelist]
	config.submitter_blacklist = [s.lower() for s in config.submitter_blacklist]
	if not config.username or not config.password or not config.oauth_id or not config.oauth_secret:
		raise ValueError("All authentication parameters must be specified")
	config.username = config.username.lower()

def get_remote_config():
	r2 = reddit_util.init_reddit_session_old()
	if r2 is None:
		return None
	result = r2.get_wiki_page(config.config_subreddit, config.config_page)
	reddit_util.destroy_reddit_session(r2)
	return result

def build_remote_config():
	wiki_config = get_remote_config()
	if not wiki_config:
		print("Error: wiki page doesn't exist")
		return None
	
	try:
		parsed = yaml.safe_load_all(wiki_config.content_md)
		
		# TODO: make dynamic
		lists = {"youtube-channel": {"ban": [], "watch": []}}
		for group in parsed:
			category = group["filter"].lower()
			action = group["action"].lower()
			ids = group["ids"]
			
			if category != "youtube-channel":
				print("Site \"{}\" not supported".format(category))
				return None
			if action != "ban" and action != "watch":
				print("Type \"{}\" not supported".format(action))
				return None
			
			lists[category][action].extend(ids)
		
		return lists
		
	except (yaml.YAMLError, KeyError) as e:
		print("Error: failed to parse config, {}".format(e))
		return None

def get_filters():
	import os, glob
	import importlib
	
	filters = []
	files = glob.glob("filters/*.py")
	for file in files:
		name = os.path.splitext(os.path.basename(file))[0]
		print(name)
		module = importlib.import_module("filters." + name)
		print(module)
		for member in dir(module):
			if member.startswith("__") \
					or member == "Filter" \
					or member == "LinkFilter" \
					or member == "PostFilter" \
					or member == "CommentFilter":
				continue
			
			member_inst = getattr(module, member)
			if isinstance(member_inst, Filter.__class__):
				filters.append(member_inst)
	
	return filters

###########
# Filters #
###########

class Filter(metaclass=ABCMeta):
	filter_id = None
	
	@abstractmethod
	def init_filter(self, configs):
		pass
	
	def update(self):
		pass

@unique
class FilterResult(IntEnum):
	REMOVE = 1
	MESSAGE = 2
	LOG = 3

class LinkFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_link(self, link, thing):
		return False
	
class PostFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_post(self, link):
		"""
		:return: {"modmail": (modmail_title, modmail_body]), "reply": reply_text, "log": (log_title, log_body)}
		"""
		return False

class CommentFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_comment(self, comment):
		return False

########
# Main #
########

all_filters = []
link_filters = []
post_filters = []
comment_filters = []

def init_filters():
	# Load filters if not already loaded
	if len(all_filters) == 0:
		print("Initializing filters")
		new_filters = get_filters()
		from pprint import pprint
		pprint(new_filters)
		
		for filter_class in new_filters:
			if filter_class.filter_id is None:
				print("Filter {} must specify a filter_id".format(nf.__module__+"."+nf.__name__))
				continue
			
			nf = filter_class()
			if nf.filter_id in config.enabled_filters:
				all_filters.append(nf)
				if issubclass(nf, LinkFilter):
					link_filters.append(nf)
				if issubclass(nf, PostFilter):
					post_filters.append(nf)
				if issubclass(nf, CommentFilter):
					comment_filters.append(nf)
	
		print("  All filters: {}".format(all_filters))
		print("  Link filters: {}".format(link_filters))
		print("  Post filters: {}".format(post_filters))
		print("  Comment filters: {}".format(comment_filters))
	
	# Initialize filters with wiki config
	configs = build_remote_config()
	print("Configs: ", end="")
	print(configs)
	for f in all_filters:
		# TODO: filter configs by filter ID
		f.init_filter(configs)

# Processing

def process_post(post):
	# Check post filters first
	for f in post_filters:
		results = f.process_post(post)
		if results and results[0]:
			if results[1]:
				post.remove()
			_send_messages(results[3], post)
			return True
	
	# Link check
	links = []
	
	# Extract links if text post
	if post.is_self and post.selftext_html is not None:
		text = post.selftext
		links.extend(extract_submission_links(text))
	# Otherwise get the post link
	elif not post.is_self:
		links.append(post.url)
	
	# Process links
	for link in links:
		results = process_link(link, post)
		if results and results[0]:
			if results[0] <= FilterResult.REMOVE:
				post.remove()
			if results[0] <= FilterResult.MESSAGE:
				_send_messages(results[1], post)
			if results[0] <= FilterResult.LOG:
				_log_result(results[1])
			return True
	
	return False

def process_comment(comment):
	# Check comment filters
	for f in comment_filters:
		results = f.process_comment(comment)
		if results and results[0]:
			if results[1]:
				comment.remove()
			_send_messages(results[1], comment)
			return True
	
	# Link check
	links = []

	# Extract links
	text = comment.body
	links.extend(extract_submission_links(text))

	# Process links
	for link in links:
		results = process_link(link, comment)
		if results and results[0]:
			if results[0] <= FilterResult.REMOVE:
				comment.remove()
			if results[0] <= FilterResult.MESSAGE:
				_send_messages(results[1], comment)
			if results[0] <= FilterResult.LOG:
				_log_result(results[1])
			return True
	
	return False

def process_link(link, thing):
	for f in link_filters:
		results = f.process_link(link, thing)
		print("  Link filter results: {}".format(results))
		if results and results[0]:
			return results
	return False

def _send_messages(messages, thing=None):
	#TODO: post/comment info replacement
	
	if "modmail" in messages:
		title = "[SpamShark] "+messages["modmail"][0]
		body = messages["modmail"][1]
		reddit_util.send_modmail(r, config.subreddit, title, body)
	if not thing is None:
		if "reply" in messages:
			#TODO: test this
			body = messages["reply"]
			reddit_util.reply_to(thing, body)
		if "pm" in messages:
			#TODO: test this
			author = thing.author.name
			title = messages["pm"][0]
			body = messages["pm"][1]
			# TODO: see if current subreddit can be pulled from post/comment
			#from_sr = thing.subreddit if len(messages["pm"]) > 2 and messages["pm"][2] else None
			reddit_util.send_pm(r, author, title, body)

def _log_result(messages):
	if "log" in messages:
		title = messages["log"][0]
		body = messages["log"][1]
		reddit_util.submit_text_post(r, config.log_subreddit, title, body)

# Actual main

running = True
waitEvent = Event()

post_cache = load_cached_storage(config.post_cache_file)
comment_cache = load_cached_storage(config.comment_cache_file)

def process_loop():
	# Get reddit connection
	global r
	r = reddit_util.init_reddit_session()
	
	# Go! Go! Go!
	while running:
		try:
			r = reddit_util.renew_reddit_session(r)
			
			# Check for update messages
			#print("Checking for messages...", end=" ")
			update = len(all_filters) == 0					# Guarantee update if on first iteration (assuming filters exist)
			unread = r.get_unread(limit=None)
			for message in unread:
				print("New message: {}".format(message))
				message.mark_as_read()
				
				if message.subject.lower() == config.subreddit and message.body == "update" \
						and (len(config.config_whitelist) == 0 or message.author.name.lower() in config.config_whitelist):
					update = True
			#print("done!")
			
			# Initialize filters if non-initialized or requested
			if update:
				print("Updating filters...", end=" ")
				init_filters()
				print("done!")
			
			# Do some moderation!
			subreddit = r.get_subreddit(config.subreddit)
			
			for f in all_filters:
				f.update()
			
			#print("Processing new posts...", end=" ")
			new_posts = reddit_util.get_all_new(subreddit)
			new_posts = post_cache.get_diff(new_posts)
			for post in new_posts:
				process_post(post)
			#print("done!")
			
			#print("Processing new comments...", end=" ")
			new_comments = reddit_util.get_all_comments(subreddit)
			new_comments = comment_cache.get_diff(new_comments)
			for comment in new_comments:
				process_comment(comment)
			#print("done!")
			
		except (ModeratorRequired, ModeratorOrScopeRequired, HTTPError) as e:
			if not isinstance(e, HTTPError) or e.response.status_code == 403:
				print("Error: No moderator permission")
			ex_type, ex, tb = sys.exc_info()
			print("Error: {}".format(e))
			traceback.print_tb(tb)
			del tb
		except Exception as e:
			ex_type, ex, tb = sys.exc_info()
			print("Error: {}".format(e))
			traceback.print_tb(tb)
			del tb
		
		if running:
			if waitEvent.wait(timeout=20):
				break

def main():
	build_local_config()
	
	# Start
	processing_thread = Thread(target=process_loop, name="SpamShark-process-thread")
	processing_thread.start()
	
	global running
	while running:
		try:
			raw_cmd = input()
			cmds = raw_cmd.split()
			cmd = cmds[0]
			
			if cmd == "stop":
				print("Stopping...")
				running = False
				waitEvent.set()
			else:
				print("Command \""+cmds[0]+"\" not found")
		
		except KeyboardInterrupt:
			running = False
			waitEvent.set()
		except Exception as e:
			ex_type, ex, tb = sys.exc_info()
			if ex_type == EOFError:
				running = False
				waitEvent.set()
			else:
				print("Error: {0}".format(e))
				traceback.print_tb(tb)
			del tb
	
	processing_thread.join()
	
	# Clean up
	print("Saving and cleaning up...", end=" ")
	reddit_util.destroy_reddit_session(r)
	
	post_cache.save()
	comment_cache.save()
	
	print("done!")

#############
# Utilities #
#############

_link_pattern = re.compile("((?:[a-z]+://)?(?:[a-z0-9]+\.)+[a-z]{2,}(?:[^)\]}\* \t\r\n]*)?)", flags=re.IGNORECASE)

def extract_submission_links(markdown_text):
	matched = _link_pattern.findall(markdown_text)
	
	links = []
	for link in matched:
		links.append(link)
	
	return links

if __name__ == "__main__":
	main()
