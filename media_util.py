import requests, re
from cache.cache import TimedObjCache
import config

# YouTube utilities

_yt_sigs = ["youtube.com", "youtu.be"]
_yt_headers = {"User-Agent": config.useragent}
_yt_video_url = "https://www.googleapis.com/youtube/v3/videos?part={type}&id={id}"
_yt_last_time = 0
_yt_cache = TimedObjCache(expiration=1800)	# 30 min

_yt_video_pattern = re.compile("(?:youtube\.com/(?:(?:watch|attribution_link)\?.*v(?:=|%3D)|embed/)|youtu\.be/)([a-zA-Z0-9-_]+)")
_yt_playlist_pattern = re.compile("youtube\.com/playlist\?list=([a-zA-Z0-9-_]+)")
_yt_channel_pattern = re.compile("youtube\.com/(?:channel|user)/([a-zA-Z0-9-_]+)")

def is_youtube_link(url):
	url = url.lower()
	for sig in _yt_sigs:
		if sig in url:
			return True
	return False

def is_youtube_video(url):
	if not is_youtube_link(url):
		return False
	video_id = get_youtube_video_id(url)
	return not video_id is None

def get_youtube_video_id(url):
	match = _yt_video_pattern.findall(url)
	if len(match) > 0:
		return match[0]
	return None

def get_youtube_channel(url):
	match = _yt_channel_pattern.findall(url)
	if len(match) > 0:
		return match[0], None
	
	match = _yt_video_pattern.findall(url)
	if len(match) > 0:
		return _get_channel_from_video(match[0])
	
	match = _yt_playlist_pattern.findall(url)
	if len(match) > 0:
		return _get_channel_from_playlist(match[0])

def _get_channel_from_video(video_id):
	url = _yt_video_url.format(type="snippet", id=video_id)
	response = _youtube_request(url)
	if response is None:
		return None
	if len(response["items"]) == 0:
		return None
	
	video_info = response["items"][0]
	if video_info["kind"] == "youtube#video" and "snippet" in video_info:	# Sanity check
		snippet = video_info["snippet"]
		channelId = snippet["channelId"]
		channelName = snippet["channelTitle"]
		return channelId, channelName
	
	return None

def _get_channel_from_playlist(playlist_id):
	# TODO: fix
	return None
	
	chan_info = _yt_channel_cache.get(playlist_id)
	if chan_info is not None:
		return chan_info
	
	playlist_info = _youtube_request("playlists", playlist_id)
	if playlist_info is None:
		return None
	
	author = playlist_info["feed"]["author"][0]
	author_info = ("UC"+author["yt$userId"]["$t"], author["name"]["$t"])
	#print("ID={}, name={}".format(*author_info))
	_yt_channel_cache.store(playlist_id, author_info)
	return author_info

def get_youtube_video_description(url):
	video_id = get_youtube_video_id(url)
	if not video_id is None:
		url = _yt_video_url.format(type="snippet", id=video_id)
		response = _youtube_request(url)
		if response is None:
			return None
		
		video_info = response["items"][0]
		if video_info["kind"] == "youtube#video" and "snippet" in video_info:	# Sanity check
			description = video_info["snippet"]["description"]
			return description
	
	return None

def get_youtube_uploader_comments(url):
	pass

def _youtube_request(request_url):
	global _yt_last_time
	
	cache_result = _yt_cache.get(request_url)
	if cache_result is not None:
		return cache_result
	
	url = request_url+"&key="+config.youtube_api_key
	
	_yt_last_time = _requst_wait(_yt_last_time, 0)
	response = requests.get(url, headers=_yt_headers)
	
	if response.status_code == 200:
		#print("Success!")
		good_stuff = response.json()
		_yt_cache.store(request_url, good_stuff)
		return good_stuff
	else:
		print("YouTube request failed ({}): {}".format(response.status_code, url))
		return None

# Misc. helpers

from time import time, sleep

def _requst_wait(last_time, delay):
	time_since = time() - last_time
	if 0 < time_since < delay:
		sleep(delay - time_since)
	return time()
