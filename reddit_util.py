import praw, requests
from requests.auth import HTTPBasicAuth
import re
from time import time

# Initialization

_oauth_scopes = {"identity", "edit", "modposts", "modwiki", "privatemessages", "read", "report", "wikiread", "submit", "modcontributors"}
_oauth_start = 0
_oauth_length = 3300

def init_reddit_session():
	global _oauth_start, _oauth_length
	
	try:
		import config
		
		print("Connecting to reddit...", end=" ")
		r = praw.Reddit(user_agent=config.useragent)
		
		print("logging in...", end=" ")
		if config.username is None or config.password is None:
			return None
		
		client_auth = HTTPBasicAuth(config.oauth_id, config.oauth_secret)
		headers = {"User-Agent": config.useragent}
		data = {"grant_type": "password", "username": config.username, "password": config.password}
		response = requests.post("https://www.reddit.com/api/v1/access_token", auth=client_auth, headers=headers, data=data)
		response_content = response.json()
		if "error" in response_content and response_content["error"] != 200:
			print("failed!\nResponse code = {}".format(response_content["error"]))
			return None
		
		token = response_content["access_token"]
		if response_content["token_type"] != "bearer":
			return None
		_oauth_start = time()
		_oauth_length = response_content["expires_in"] - 300
		r.set_oauth_app_info(config.oauth_id, config.oauth_secret, "http://example.com/unused/redirect/uri")
		r.set_access_credentials(_oauth_scopes, access_token=token)
		r.config.api_request_delay = 1
		
		print("done!")
		return r
	
	except Exception as e:
		print("failed! Couldn't connect: {}".format(e))
		raise e

def destroy_reddit_session(r):
	r.clear_authentication()

def renew_reddit_session(r):
	if time() - _oauth_start >= _oauth_length:
		print("Renewing oauth token")
		return init_reddit_session()
	return r

# Thing getting

_last_new_time = -1

def get_all_new(subreddit, limit=200, save_last=True):
	global _last_new_time
	posts = []
	
	after = None
	while len(posts) < limit:
		new_posts = list(subreddit.get_new(limit=100, params={"after": after}))
		if len(new_posts) == 0:
			break
		
		posts.extend(new_posts)
		after = "t3_"+posts[-1].id
		after_time = posts[-1].created_utc
		
		if len(new_posts) < 50 or (save_last and after_time < _last_new_time):
			break
	
	if save_last and len(posts) > 0:
		_last_new_time = posts[0].created_utc
	return posts

_last_comment_time = -1

def get_all_comments(subreddit_or_user, limit=300, save_last=True):
	global _last_comment_time
	comments = []
	
	after = None
	while len(comments) < limit:
		new_comments = list(subreddit_or_user.get_comments(limit=100, params={"after": after}))
		if len(new_comments) == 0:
			break
		
		comments.extend(new_comments)
		after = "t1_"+comments[-1].id
		after_time = comments[-1].created_utc
		
		if len(new_comments) < 100 or (save_last and after_time < _last_comment_time):
			break
	
	if save_last and len(comments) > 0:
		_last_comment_time = comments[0].created_utc
	return comments

_last_submitted_time = -1

def get_all_submitted(user, limit=200, save_last=True):
	global _last_submitted_time
	posts = []
	
	after = None
	while len(posts) < limit:
		new_posts = list(user.get_submitted(limit=100, params={"after": after}))
		if len(new_posts) == 0:
			break
		
		posts.extend(new_posts)
		after = "t3_"+posts[-1].id
		after_time = posts[-1].created_utc
		
		if len(new_posts) < 100 or (save_last and after_time < _last_submitted_time):
			break
	
	if save_last and len(posts) > 0:
		_last_submitted_time = posts[0].created_utc
	return posts

def get_wiki_page(r, subreddit_name, page_name):
	return r.get_wiki_page(subreddit_name, page_name)

# Thing doing

#TODO: remove
def comment_on(comment_text, post=None, comment=None, distinguish=False):
	"""
	Note: deprecated
	"""
	reply = None
	if post is not None:
		reply = post.add_comment(comment_text)
	elif comment is not None:
		reply = comment.reply(comment_text)
	
	if distinguish and reply is not None:
		response = reply.distinguish()
		if len(response) > 0 and len(response["errors"]) > 0:
			print("Error when distinguishing: {0}".format(response["errors"]))

def submit_text_post(r, subreddit, title, body):
	try:
		r.submit(subreddit, title, text=body, send_replies=False)
	except Exception as e:
		print("!!! Error when submitting text post")
		print(e)
		print(vars(e))

def send_modmail(r, subreddit, title, body):
	r.send_message("/r/"+subreddit, title, body)

def send_pm(r, user, title, body, from_sr=None):
	r.send_message(user, title, body, from_sr=from_sr)

def reply_to(thing, body, distinguish=False):
	reply = None
	if isinstance(thing, praw.objects.Submission):
		reply = thing.add_comment(body)
	elif isinstance(thing, praw.objects.Inboxable):
		reply = thing.reply(body)
	
	if distinguish and reply is not None:
		response = reply.distinguish()
		if len(response) > 0 and len(response["errors"]) > 0:
			print("Error when distinguishing: {0}".format(response["errors"]))

def set_flair(r, subreddit, thing, flair_text, flair_css):
	r.set_flair()

# Utilities

redditReductionPattern = re.compile("https?://(?:.+\.)?(?:reddit\.com(?:(/r/\w+/comments/\w+/?)(?:(?:\w+/?)(.*))?|(?:(/(?:u|user|m|message|r/\w+)/.+)))|(redd.it/\w+))")

def reduce_reddit_link(link, include_prefix=False):
	global redditReductionPattern
	
	match = redditReductionPattern.match(link)
	if match:
		prefix = ("http://reddit.com" if include_prefix else "")
		
		#Normal comment page permalink, uses two groups (one optional)
		if match.group(1) is not None:
			return prefix+match.group(1)+("-/"+match.group(2) if match.group(2) is not None and len(match.group(2)) > 0 else "")
		#Other (user pages, messages, 
		if match.group(4) is not None:
			return prefix+match.group(4)
		#Shortlink
		if match.group(6) is not None:
			return prefix+match.group(6)
	
	return link

def is_post(thing):
	return isinstance(thing, praw.objects.Submission)

def is_comment(thing):
	return isinstance(thing, praw.objects.Comment)

def is_message(thing):
	return isinstance(thing, praw.objects.Message)
