from django.dispatch import Signal

#: Lets a vidscraper video be modified before it's used to create a Video.
pre_video_import = Signal(providing_args=["vidscraper_video"])
#: Lets action be taken on a Video which has been created.
post_video_import = Signal(providing_args=["instance", "vidscraper_video"])

#: Sent right before videos from a feed import are marked published. Receivers
#: can return a Q object or filter dictionary.
pre_feed_import_publish = Signal(providing_args=['to_publish'])
#: Lets action be taken on a qs of videos that have just been marked
#: "published" during an import.
post_feed_import_publish = Signal(providing_args=['published'])
