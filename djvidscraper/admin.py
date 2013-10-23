from django.contrib import admin

from djvidscraper.forms import CreateVideoForm
from djvidscraper.models import Feed, Video, VideoFile


class VideoFileInline(admin.TabularInline):
    extras = 0
    model = VideoFile


class VideoAdmin(admin.ModelAdmin):
    readonly_fields = (
        'modified_timestamp',
        'created_timestamp',
        'published_datetime',
    )
    raw_id_fields = ('owner_session', 'owner')
    fieldsets = (
        (None, {
            'fields': ('original_url',)
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

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return super(VideoAdmin, self).get_fieldsets(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        """
        Different form during video creation.

        """
        defaults = {}
        if obj is None:
            defaults.update({
                'form': CreateVideoForm,
                'fields': admin.util.flatten_fieldsets(self.add_fieldsets),
            })
        defaults.update(kwargs)
        return super(VideoAdmin, self).get_form(request, obj, **defaults)

    def get_inline_instances(self, request, obj=None):
        if obj is None:
            return []
        return super(VideoAdmin, self).get_inline_instances(request, obj)


admin.site.register(Feed, admin.ModelAdmin)
admin.site.register(Video, VideoAdmin)
