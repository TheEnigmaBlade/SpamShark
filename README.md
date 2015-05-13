# SpamShark

Modularized reddit moderation bot with a focus on spam prevention.

## Features

- Ability to create individual "filters" to perform individual functions
- Filters customizable through a subreddit wiki page using YAML
- Default filters
  - YouTube channel bans and monitors: affects link posts, text posts, and comments

## Getting started

#### Default filters

* YouTube channel bans: `youtube-channel`

## Creating filters

To create a new filter, create or edit a python file in the `filters` directory. Create a class extending `spam_shark.Filter` and one or more filter types.

#### Filter template

```python
from spam_shark import Filter, FilterResult, LinkFilter

class TemplateFilter(Filter, LinkFilter):
    filter_id = "filter-template"   # Required, used in wiki config
    
    def init_filter(self, configs):
        # Do filter initialization here
        # A list of parsed YAML rules are passed in through 'configs'
    
    def update(self):
      # OPTIONAL
      # Do stuff each iteration before posts and comments are processed
    
    def process_link(self, link, thing):
        # Process a link within a thing (post or comment)
        # Returns a filter result and map of message actions
        if "domain.spam" in link:
            return FilterResult.REMOVE, {"log": (log_title, log_body), "reply": reply_body}
```

#### Available filter types

Defined in module `spam_shark`

* `LinkFilter`: Requires definition of `process_link(self, link, thing)`
  
* `PostFilter`: Requires definition of `process_post(self, link)`
  
* `CommentFilter`: Requires definition of `process_comment(self, comment)`

#### Available filter results

Defined in enum `spam_shark.FilterResult`

* `REMOVE`: Removes the processed thing, performs message actions, and logs the action
* `MESSAGE`: Performs message actions and logs the action

  Requires one or more of the following defined in message actions:
  * ```"modmail": (log_title, log_body)```
  * ```"reply": reply_body```
  * ```"pm": (pm_title, pm_body)```

* `LOG`: Logs the action

  Requires ```"log": (log_title, log_body)``` defined in message actions
