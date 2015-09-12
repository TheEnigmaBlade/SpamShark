# Reddit connection
useragent			= "script:SpamShark:v0.4 (by /u/TheEnigmaBlade)"
username			= ""
password			= ""
oauth_id			= ""					# Create a "script" application here: https://www.reddit.com/prefs/apps/
oauth_secret		= ""

# Subreddit
subreddit			= ""
submitter_blacklist	= ["AutoModerator"]

config_subreddit	= subreddit
config_page			= "spamshark"
config_whitelist	= []					# Whitelist of users able to trigger a config update (leave empty for no whitelist)

log_subreddit		= None					# Subreddit to which log messages are sent (leave None for no logging)

# Bot
cache_location		= "cache"
filter_location		= "filters"				# Relative directory containing filter files
enabled_filters		= ["youtube-channel", "youtube-votemanip"]

# Filters
youtube_api_key		= ""					# Create an API key by following these instructions: https://developers.google.com/youtube/registering_an_application
