from django.http import Http404
from django.views.generic import ListView, DetailView, TemplateView

from djvidscraper.models import Video, Feed


class IndexView(TemplateView):
    template_name = 'djvidscraper/index.html'

    def get_context_data(self, **kwargs):
        context = super(IndexView, self).get_context_data(**kwargs)
        context['videos'] = Video.objects.filter(status=Video.PUBLISHED)[:5]
        return context


class VideoDetailView(DetailView):
    template_name = 'djvidscraper/videos/detail.html'
    queryset = Video.objects.filter(status=Video.PUBLISHED)
    context_object_name = 'video'


class VideoListView(ListView):
    template_name = 'djvidscraper/videos/list.html'
    queryset = Video.objects.filter(status=Video.PUBLISHED)
    context_object_name = 'videos'


class FeedDetailView(ListView):
    template_name = 'djvidscraper/feeds/detail.html'
    context_object_name = 'videos'

    def get_objects(self):
        try:
            self.feed = Feed.objects.get(pk=self.kwargs['pk'])
        except Feed.DoesNotExist:
            raise Http404

        return self.feed.videos.filter(status=Video.PUBLISHED)

    def get_context_data(self, **kwargs):
        context = super(FeedDetailView, self).get_context_data(**kwargs)
        context['feed'] = self.feed
        return context


class FeedListView(ListView):
    model = Feed
    context_object_name = 'feeds'
    template_name = 'djvidscraper/feeds/list.html'
