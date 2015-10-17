#!/usr/bin/env python3
from abc import ABCMeta, abstractmethod
from enum import IntEnum
from requests import HTTPError
import os, sys, yaml, re, traceback, inspect
from threading import Thread, Event
from praw.errors import ModeratorRequired, ModeratorOrScopeRequired

import config, reddit_util
from cache import load_cached_storage

import warnings
warnings.simplefilter("ignore", ResourceWarning)

# Ensure proper files can be access if running with cron
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Globals
version = "0.4"
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

def build_remote_config():
	wiki_config = reddit_util.get_wiki_page(r, config.config_subreddit, config.config_page)
	if not wiki_config:
		print("Error: wiki page doesn't exist")
		return None
	
	try:
		parsed = yaml.safe_load_all(wiki_config.content_md)
		
		config_groups = {}
		for i, group in enumerate(parsed):
			if not "filter" in group:
				print("Warning: config {} not associated with filter".format(i+1))
				continue
			filter_id = group["filter"]
			del group["filter"]
			
			if not filter_id in config_groups:
				config_groups[filter_id] = []
			config_groups[filter_id].append(group)
		
		return config_groups
		
	except (yaml.YAMLError, KeyError) as e:
		print("Error: failed to parse config, {}".format(e))
		return None

def get_filters():
	import os, glob
	import importlib
	
	filters = []
	files = glob.glob(config.filter_location+"/*.py")
	for file in files:
		name = os.path.splitext(os.path.basename(file))[0]
		module = importlib.import_module(config.filter_location+"." + name)
		for member in dir(module):
			if member.startswith("__") \
					or member == "Filter" \
					or member == "LinkFilter" \
					or member == "PostFilter" \
					or member == "CommentFilter":
				continue
			
			member_class = getattr(module, member)
			if inspect.isclass(member_class):
				try:
					# Nasty workaround since a Filter imported into another module is different from the one used here
					if fake_isinstance(member_class, Filter):
						filters.append(member_class)
				except TypeError:
					# Not-so-neat way of avoiding uninitializable types with no built-in type checks, like enum
					pass
	
	return filters

###########
# Filters #
###########

class Filter(metaclass=ABCMeta):
	filter_id = None
	enabled = True
	
	@abstractmethod
	def init_filter(self, configs):
		pass
	
	def update(self):
		pass

class FilterResult(IntEnum):
	BAN = 1
	REMOVE = 2
	FLAIR = 3
	MESSAGE = 3
	LOG = 4
	REPORT = 5

class LinkFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_link(self, link, thing):
		return False
	
class PostFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_post(self, link):
		return False

class CommentFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_comment(self, comment):
		return False

class MessageFilter(metaclass=ABCMeta):
	@abstractmethod
	def process_message(self, message):
		return False

########
# Main #
########

all_filters = []
link_filters = []
post_filters = []
comment_filters = []
pm_filters = []

def init_filters(configure=True):
	print("Loading filters...", end=" ")
	
	# Load filters if not already loaded
	if len(all_filters) == 0:
		new_filters = get_filters()
		print("using {} filters...".format(len(new_filters)), end=" ")
		
		for nf_class in new_filters:
			if nf_class.filter_id is None:
				print("\n  Error: Filter {} must specify a filter_id\n".format(nf_class.__module__+"."+nf_class.__name__))
				continue
			
			if nf_class.filter_id in config.enabled_filters:
				nf = nf_class()
				all_filters.append(nf)
				if fake_isinstance(nf_class, LinkFilter):
					link_filters.append(nf)
				if fake_isinstance(nf_class, PostFilter):
					post_filters.append(nf)
				if fake_isinstance(nf_class, CommentFilter):
					comment_filters.append(nf)
	
	# Initialize filters with wiki config
	if configure:
		print("configuring filters...", end=" ")
		configs = build_remote_config()
		for f in all_filters:
			print("\nConfiguring {}".format(f.filter_id))
			print("--------------------")
			
			f_configs = configs[f.filter_id] if f.filter_id in configs else []
			try:
				f.enabled = True
				error = f.init_filter(f_configs)
				if error:
					print("\n  Error: Filter configuration failed for {} ({})\n".format(f.filter_id, error))
					f.enabled = False
			except Exception as e:
				ex_type, ex, tb = sys.exc_info()
				print("Error: Filter configuration unexpectedly failed for {} ({})".format(f.filter_id, e))
				traceback.print_tb(tb)
				del tb
			
		print("--------------------")
	
	print("done!")

def has_link_filters():
	return len(link_filters) > 0

def has_post_filters():
	return len(post_filters) > 0

def has_comment_filters():
	return len(comment_filters) > 0

def has_message_filters():
	return len(pm_filters) > 0

# Processing

def process_post(post):
	if not has_post_filters() and not has_link_filters():
		return False
	
	# Check post filters first
	for f in post_filters:
		results = f.process_post(post)
		if process_filter_results(results, post):
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
		if process_filter_results(results, post):
			return True
	
	return False

def process_comment(comment):
	if not has_comment_filters() and not has_link_filters():
		return False
	
	# Check comment filters
	for f in comment_filters:
		results = f.process_comment(comment)
		if process_filter_results(results, comment):
			return True
	
	# Link check
	links = []

	# Extract links
	text = comment.body
	links.extend(extract_submission_links(text))

	# Process links
	for link in links:
		results = process_link(link, comment)
		if process_filter_results(results, comment):
			return True
	
	return False

def process_link(link, thing):
	for f in link_filters:
		results = f.process_link(link, thing)
		if results and results[0]:
			return results
	return False

def process_message(message):
	for f in pm_filters:
		results = f.process_message(message)
		if process_filter_results(results, message):
			return True
	return False

def process_filter_results(results, thing):
	if results and len(results) == 2 and results[0]:
		if results[0] <= FilterResult.BAN:
			_ban_author(results[1], thing)
		if results[0] <= FilterResult.REMOVE:
			thing.remove()
		if results[0] <= FilterResult.MESSAGE:
			_send_messages(results[1], thing)
			_flair_thing(results[1], thing)
		if results[0] <= FilterResult.LOG:
			_log_result(results[1], thing)
		if results[0] == FilterResult.REPORT:
			thing.report(reason=results[1])
		return True
	return False

def _ban_author(messages, thing):
	note = msg = None
	dur = 0
	if dict_exists(messages, "ban"):
		ban_info = messages["ban"]
		if dict_exists(ban_info, "note"):
			note = ban_info["note"]
		if dict_exists(ban_info, "message"):
			msg = ban_info["message"]
		if dict_exists(ban_info, "duration"):
			dur = ban_info["duration"]
	thing.subreddit.add_ban(thing.author, params={"note": note, "ban_message": msg, "duration": dur})

def _send_messages(messages, thing):
	thing_info = _get_thing_info(thing)
	def fmt(text):
		return safe_format(text, **thing_info)
	
	if dict_exists(messages, "modmail"):
		title = "[SpamShark] "+fmt(messages["modmail"][0])
		body = fmt(messages["modmail"][1])
		reddit_util.send_modmail(r, config.subreddit, title, body)
	if not thing is None:
		if dict_exists(messages, "reply"):
			body = fmt(messages["reply"])
			reddit_util.reply_to(thing, body, distinguish=True)
		if dict_exists(messages, "pm"):
			#TODO: test this
			author = thing.author.name
			title = fmt(["pm"][0])
			body = fmt(messages["pm"][1])
			from_sr = thing.subreddit.display_name if len(messages["pm"]) > 2 and messages["pm"][2] and hasattr(thing, "subreddit") else None
			reddit_util.send_pm(r, author, title, body, from_sr=from_sr)

def _flair_thing(messages, thing):
	if not thing is None:
		if dict_exists(messages, "flair_user"):
			author = thing.author
			flair_text = messages["flair_user"][0]
			flair_css = messages["flair_user"][1]
			reddit_util.set_flair(r, config.subreddit, author, flair_text, flair_css)
		if dict_exists(messages, "flair_post") and reddit_util.is_post(thing):
			flair_text = messages["flair_post"][0]
			flair_css = messages["flair_post"][1]
			reddit_util.set_flair(r, config.subreddit, thing, flair_text, flair_css)

def _log_result(messages, thing):
	thing_info = _get_thing_info(thing)
	def fmt(text):
		return safe_format(text, **thing_info)
	
	if dict_exists(messages, "log") and not config.log_subreddit is None and len(config.log_subreddit) > 0:
		title = fmt(messages["log"][0])
		body = fmt(messages["log"][1])
		reddit_util.submit_text_post(r, config.log_subreddit, title, body)

def _get_thing_info(thing, link=None):
	if reddit_util.is_post(thing):
		return {
			"author": "/u/"+thing.author.name,
			"permalink": reddit_util.reduce_reddit_link(thing.permalink),
			"title": thing.title,
			"body": thing.selftext if thing.is_self else "",
			"link": thing.url if not thing.is_self else "",
			"subreddit": config.subreddit
		}
	if reddit_util.is_comment(thing):
		resp = {
			"author": "/u/"+thing.author.name,
			"permalink": reddit_util.reduce_reddit_link(thing.permalink),
			"body": thing.body,
			"subreddit": config.subreddit
		}
		if link:
			resp["link"] = link
		return resp
	if reddit_util.is_message(thing):
		print("IT'S A MESSAGE!")
		from pprint import pprint
		pprint(vars(thing))
		resp = {
			"author": "/u/"+thing.author.name,
			"permalink": reddit_util.reduce_reddit_link(thing.permalink),
			"title": thing.title,
			"body": thing.body,
		}
		if link:
			resp["link"] = link
		return resp
	return {}

# Actual main

args = None
running = True
waitEvent = Event()

def update_filters():
	def do_result(result_tuple):
		if result_tuple and len(result_tuple) == 3:
			process_filter_results((result_tuple[0], result_tuple[1]), result_tuple[2])
	
	for ff in all_filters:
		try:
			for result in ff.update():
				do_result(result)
			
		except Exception as e:
			ex_type, ex, tb = sys.exc_info()
			print("Error: Filter update unexpectedly failed for {} ({})".format(ff.filter_id, e))
			traceback.print_tb(tb)
			del tb

def process_loop():
	# Get reddit connection
	global r
	r = reddit_util.init_reddit_session()
	
	# Create/load caches
	os.makedirs(config.cache_location, exist_ok=True)
	post_cache = load_cached_storage(config.cache_location+"/posts.cache")
	comment_cache = load_cached_storage(config.cache_location+"/comments.cache")
	
	# Go! Go! Go!
	while running:
		try:
			r = reddit_util.renew_reddit_session(r)
			
			# Check for update messages
			update = len(all_filters) == 0			# Guarantee update if on first iteration (assuming filters exist)
			unread = r.get_unread(limit=None)
			new_messages = list()
			for message in unread:
				message.mark_as_read()
				
				if message.subject.lower() == config.subreddit:
					if message.body == "update" \
							and (len(config.config_whitelist) == 0 or message.author.name.lower() in config.config_whitelist):
						print("Update message received from {}".format(message.author.name))
						update = True
					else:
						new_messages.append(message)
			
			# Initialize filters if non-initialized or requested
			if update:
				init_filters()
			
			# Let filters do their update things
			update_filters()
			
			# Do some moderation!
			subreddit = r.get_subreddit(config.subreddit)
			
			## Messages
			for message in new_messages:
				process_message(message)
			
			## Posts
			new_posts = reddit_util.get_all_new(subreddit)
			new_posts = post_cache.get_diff(new_posts)
			for post in new_posts:
				process_post(post)
			
			## Comments
			new_comments = reddit_util.get_all_comments(subreddit)
			new_comments = comment_cache.get_diff(new_comments)
			for comment in new_comments:
				process_comment(comment)
			
			if running and waitEvent.wait(timeout=20):
				break
			
		except (ModeratorRequired, ModeratorOrScopeRequired, HTTPError) as e:
			if not isinstance(e, HTTPError) or e.response.status_code == 403:
				print("Error: No moderator permission")
			ex_type, ex, tb = sys.exc_info()
			print("Error: {}".format(e))
			traceback.print_tb(tb)
			del tb
		except KeyboardInterrupt:
			print("Stopped with keyboard interrupt")
		except Exception as e:
			ex_type, ex, tb = sys.exc_info()
			print("Error: {}".format(e))
			traceback.print_tb(tb)
			del tb
	
	post_cache.save()
	comment_cache.save()

def main():
	build_local_config()
	
	# Start
	if args.no_input:
		process_loop()
	else:
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
				elif cmd == "status":
					if running:
						print("I'm not dead yet!")
					else:
						print("Well now he's dead.")
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

def fake_isinstance(obj_cls, cls):
	return isinstance(obj_cls, cls) or cls.__name__ in list(map(lambda c: c.__name__, inspect.getmro(obj_cls)))

class _SafeDict(dict):
	def __missing__(self, key):
		return '{' + key + '}'

def safe_format(text, **kwargs):
	return text.format_map(_SafeDict(kwargs))

def dict_exists(messages, name):
	return name in messages and not messages[name] is None

###########
# Running #
###########

if __name__ == "__main__":
	import argparse
	parser = argparse.ArgumentParser(description="SpamShark, modular reddit moderation bot")
	parser.add_argument("--no-input", action="store_true", help="run in a single thread without stdin")
	parser.add_argument("--no-update", action="store_true", help="run without checking for config update messages")
	parser.add_argument("--list-filters", action="store_true", help="list available filters")
	parser.add_argument("-v", "--version", action="version", version="SpamShark "+version)
	args = parser.parse_args()
	
	if args.list_filters:
		filters = get_filters()
		print("Available filters:\n------------------")
		for i, f in enumerate(filters):
			print("{}. {}".format(i+1, f.filter_id), end="")
			if hasattr(f, "filter_name"):
				print(": {}".format(f.filter_name))
			else:
				print()
			if hasattr(f, "filter_descr") and not f.filter_descr is None:
				print("   {}".format(f.filter_descr))
			if hasattr(f, "filter_author") and not f.filter_author is None:
				print("   Created by {}".format(f.filter_author))
			print()
	else:
		main(args)
