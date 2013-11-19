from django.contrib import admin, messages
from django.contrib.sites.admin import Site, SiteAdmin

from djvidscraper.forms import CreateVideoForm, CreateFeedForm
from djvidscraper.models import Feed, Video, VideoFile, FeaturedVideo


class AddAdmin(admin.ModelAdmin):
    add_fieldsets = None
    add_form = None

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return super(AddAdmin, self).get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        """
        Different form during video creation.

        """
        defaults = {}
        if obj is None:
            defaults.update({
                'form': self.add_form,
                'fields': admin.util.flatten_fieldsets(self.add_fieldsets),
            })
        defaults.update(kwargs)
        return super(AddAdmin, self).get_form(request, obj, **defaults)


class VideoFileInline(admin.TabularInline):
    extra = 0
    model = VideoFile


class VideoAdmin(AddAdmin):
    add_form = CreateVideoForm
    readonly_fields = (
        'modified_timestamp',
        'created_timestamp',
        'published_datetime',
    )
    raw_id_fields = ('owner_session', 'owner')
    radio_fields = {'status': admin.VERTICAL}
    list_filter = ('status', 'created_timestamp', 'feed')
    fieldsets = (
        (None, {
            'fields': ('original_url', 'status')
        }),
        ('Metadata', {
            'fields': ('name',
                       'description',
                       'web_url',
                       'thumbnail',
                       'embed_code',
                       'flash_enclosure_url',
                       'guid'),
        }),
        ('Owner', {
            'fields': ('owner', 'owner_email', 'owner_session')
        }),
        ('External data', {
            'description': "These fields should generally not need "
                           "to be edited.",
            'classes': ('collapse',),
            'fields': ('external_user_username',
                       'external_user_url',
                       'external_thumbnail_url',
                       'external_thumbnail_tries',
                       'external_published_datetime')
        }),
        ('Internal data', {
            'classes': ('collapse',),
            'fields': ('created_timestamp',
                       'modified_timestamp',
                       'published_datetime')
        }),
    )
    add_fieldsets = (
        (None, {
            'fields': ('original_url',)
        }),
    )
    inlines = [VideoFileInline]
    actions = ['hide_videos', 'publish_videos']

    def hide_videos(self, request, queryset):
        queryset.update(status=Video.HIDDEN)
    hide_videos.short_description = 'Hide selected videos'

    def publish_videos(self, request, queryset):
        queryset.update(status=Video.PUBLISHED)
    publish_videos.short_description = 'Publish selected videos'

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super(VideoAdmin, self).get_inline_instances(request, obj)

    def save_form(self, request, form, change):
        return form.save(commit=False, request=request)


class FeedAdmin(AddAdmin):
    add_form = CreateFeedForm
    add_fieldsets = (
        (None, {
            'fields': ('original_url',
                       'moderate_imported_videos',
                       'enable_automatic_imports'),
        }),
    )
    fieldsets = (
        (None, {
            'fields': ('original_url',)
        }),
        ('Metadata', {
            'fields': ('name', 'description', 'web_url', 'thumbnail'),
        }),
        ('Import settings', {
            'fields': ('moderate_imported_videos',
                       'enable_automatic_imports',
                       'stop_if_seen',
                       'should_update_metadata')
        }),
        ('Owner', {
            'fields': ('owner', 'owner_email', 'owner_session'),
        }),
        ('External data', {
            'description': "These fields should generally not need "
                           "to be edited.",
            'classes': ('collapse',),
            'fields': ('external_etag',
                       'external_last_modified')
        }),
        ('Internal data', {
            'classes': ('collapse',),
            'fields': ('created_timestamp',
                       'modified_timestamp')
        }),
    )
    readonly_fields = (
        'modified_timestamp',
        'created_timestamp',
    )

    actions = ['run_imports']

    def _message_import_result(self, feed, request):
        feed_import = feed.imports.latest()
        if feed_import.is_complete:
            if feed_import.import_count or not feed_import.error_count:
                messages.success(request, "Imported {0} new videos"
                                 "".format(feed_import.import_count))
            if feed_import.error_count:
                messages.error(request, "Encountered {0} errors"
                               "".format(feed_import.error_count))

    def save_form(self, request, form, change):
        return form.save(commit=False, request=request)

    def save_related(self, request, form, formsets, change):
        # This is where form.save_m2m (which runs the imports) is called.
        super(FeedAdmin, self).save_related(request, form, formsets, change)
        self._message_import_result(form.instance, request)

    def run_imports(self, request, queryset):
        for feed in queryset:
            feed.start_import()
            self._message_import_result(feed, request)
    run_imports.short_description = 'Run imports for selected feeds'


admin.site.register(Feed, FeedAdmin)
admin.site.register(Video, VideoAdmin)


class FeaturedVideoInline(admin.TabularInline):
    model = FeaturedVideo
    extra = 1
    raw_id_fields = ('video',)
    ordering = ('order', '-created_timestamp')


class NewSiteAdmin(SiteAdmin):
    inlines = (FeaturedVideoInline,)


admin.site.unregister(Site)
admin.site.register(Site, NewSiteAdmin)
