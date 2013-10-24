from django.conf.urls import patterns, url

from djvidscraper.views import (VideoDetailView, VideoListView,
                                FeedDetailView, FeedListView,
                                IndexView)


urlpatterns = patterns('',
    url(r'^$',
        IndexView.as_view(),
        name='djvidscraper_index'),

    url(r'^videos/$',
        VideoListView.as_view(),
        name='djvidscraper_video_list'),
    url(r'^videos/(?P<pk>\d+)/$',
        VideoDetailView.as_view(),
        name='djvidscraper_video_detail'),

    url(r'^feeds/$',
        FeedListView.as_view(),
        name='djvidscraper_feed_list'),
    url(r'^feeds/(?P<pk>\d+)/$',
        FeedDetailView.as_view(),
        name='djvidscraper_feed_detail')
)
