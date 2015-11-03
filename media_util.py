from functools import lru_cache
import requests, re, isodate
from cache import TimedObjCache
import config

# YouTube utilities

_yt_sigs = ["youtube.com", "youtu.be"]
_yt_headers = {"User-Agent": config.useragent}
_yt_api_base = "https://www.googleapis.com/youtube/v3/"
_yt_video_url = _yt_api_base+"videos?part={type}&id={id}"
_yt_playlist_url = _yt_api_base+"playlists?part={type}&id={id}"
_yt_comments_url = _yt_api_base+"commentThreads?part={type}&textFormat=plainText&videoId={id}"
_yt_last_time = 0
_yt_cache = TimedObjCache(expiration=1800)	# 30 min

_yt_video_pattern = re.compile("(?:youtube\.com/(?:(?:watch|attribution_link)\?(?:.*(?:&|%3F|&amp;))?v(?:=|%3D)|embed/|v/)|youtu\.be/)([a-zA-Z0-9-_]{11})")
_yt_playlist_pattern = re.compile("youtube\.com/playlist\?list=([a-zA-Z0-9-_]+)")
_yt_channel_pattern = re.compile("youtube\.com/(?:#/)?(?:channel|user)/([a-zA-Z0-9-_]+)")

def is_youtube_link(url):
	url = url.lower()
	for sig in _yt_sigs:
		if sig in url:
			return True
	return False

def is_youtube_video(url):
	if not is_youtube_link(url):
		return False
	video_id = _get_youtube_video_id(url)
	return not video_id is None

def _get_youtube_video_id(url):
	match = _yt_video_pattern.findall(url)
	if len(match) > 0:
		return match[0]
	return None

def is_youtube_playlist(url):
	if not is_youtube_link(url):
		return False
	video_id = _get_youtube_playlist_id(url)
	return not video_id is None

def _get_youtube_playlist_id(url):
	match = _yt_playlist_pattern.findall(url)
	if len(match) > 0:
		return match[0]
	return None

## Getting channel information

def get_youtube_channel(url):
	match = _yt_channel_pattern.findall(url)
	if len(match) > 0:
		return match[0], None
	
	ytid = _get_youtube_video_id(url)
	if not ytid is None:
		return _get_channel_from_video(ytid)
	
	ytid = _get_youtube_playlist_id(url)
	if not ytid is None:
		return _get_channel_from_playlist(ytid)

@lru_cache()
def _get_channel_from_video(video_id):
	url = _yt_video_url.format(type="snippet", id=video_id)
	response = _youtube_request(url)
	if response is None or len(response["items"]) == 0:
		return None
	
	video_info = response["items"][0]
	if video_info["kind"] == "youtube#video" and "snippet" in video_info:	# Sanity check
		snippet = video_info["snippet"]
		channelId = snippet["channelId"]
		channelName = snippet["channelTitle"]
		return channelId, channelName
	
	return None

@lru_cache()
def _get_channel_from_playlist(playlist_id):
	url = _yt_playlist_url.format(type="snippet", id=playlist_id)
	response = _youtube_request(url)
	if response is None or len(response["items"]) == 0:
		return None
	
	video_info = response["items"][0]
	if video_info["kind"] == "youtube#playlist" and "snippet" in video_info:	# Sanity check
		snippet = video_info["snippet"]
		channelId = snippet["channelId"]
		channelName = snippet["channelTitle"]
		return channelId, channelName
	
	return None

## Getting video information

def get_youtube_video_description(url):
	video_id = _get_youtube_video_id(url)
	if not video_id is None:
		url = _yt_video_url.format(type="snippet", id=video_id)
		response = _youtube_request(url)
		if response is None or len(response["items"]) == 0:
			return None
		
		video_info = response["items"][0]
		if video_info["kind"] == "youtube#video" and "snippet" in video_info:	# Sanity check
			description = video_info["snippet"]["description"]
			return description
	
	return None

def get_youtube_video_duration(url):
	video_id = _get_youtube_video_id(url)
	if not video_id is None:
		url = _yt_video_url.format(type="contentDetails", id=video_id)
		response = _youtube_request(url)
		if response is None or len(response["items"]) == 0:
			return None
		
		video_info = response["items"][0]
		if video_info["kind"] == "youtube#video" and "contentDetails" in video_info:	# Sanity check
			duration = video_info["contentDetails"]["duration"]
			duration = isodate.parse_duration(duration).total_seconds()
			return duration
	
	return None

def get_youtube_comments(url):
	video_id = _get_youtube_video_id(url)
	if not video_id is None:
		url = _yt_comments_url.format(type="snippet", id=video_id)
		response = _youtube_request(url)
		if response is None or len(response["items"]) == 0:
			return None
		
		comment_threads = response["items"]
		whargarbl = []
		for comment_thread in comment_threads:
			comment = comment_thread["snippet"]["topLevelComment"]["snippet"]
			text = comment["textDisplay"]
			if text.endswith("\ufeff"):
				text = text[:-1]
			whargarbl.append(text)
		return whargarbl
		
	return None

def _youtube_request(request_url):
	global _yt_last_time
	
	cache_result = _yt_cache.get(request_url)
	if cache_result is not None:
		return cache_result
	
	url = request_url+"&key="+config.youtube_api_key
	
	_yt_last_time = _requst_wait(_yt_last_time, 0.25)
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
