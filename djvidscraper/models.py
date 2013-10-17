from hashlib import sha1
import mimetypes
import traceback
import warnings

from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.validators import ipv4_re
from django.db import models
from django.utils.timezone import now
from django.utils.translation import ugettext_lazy as _
import requests
import vidscraper

from djvidscraper.utils import get_api_keys, download_thumbnail
from djvidscraper.signals import (pre_video_import, post_video_import,
                                  pre_feed_import_publish,
                                  post_feed_import_publish)


class FeedImportIdentifier(models.Model):
    """
    Represents a single identifier for a video, seen during an import of a
    given feed.

    """
    identifier_hash = models.CharField(max_length=40)
    feed = models.ForeignKey('Feed')

    def __unicode__(self):
        return self.identifier_hash


class FeedImport(models.Model):
    created_timestamp = models.DateTimeField(auto_now_add=True)
    modified_timestamp = models.DateTimeField(auto_now=True)
    is_complete = models.BooleanField(default=False)
    #: Denormalized field displaying (eventually accurate) count of
    #: errors during the import process.
    error_count = models.PositiveIntegerField(default=0)
    #: Denormalized field displaying (eventually accurate) count of
    #: videos imported during the import process.
    import_count = models.PositiveIntegerField(default=0)
    feed = models.ForeignKey('Feed')

    class Meta:
        get_latest_by = 'created_timestamp'
        ordering = ['-created_timestamp']

    def _get_identifier_hashes(self, vidscraper_video):
        identifiers = (
            vidscraper_video.guid,
            vidscraper_video.link,
            vidscraper_video.flash_enclosure_url,
            vidscraper_video.embed_code
        )
        if vidscraper_video.files is not None:
            identifiers += tuple(f.url for f in vidscraper_video.files
                                 if not f.expires)

        return [sha1(i).hexdigest() for i in identifiers if i]

    def is_seen(self, vidscraper_video):
        hashes = self._get_identifier_hashes(vidscraper_video)
        if not hashes:
            return False
        kwargs = {
            'feed': self.feed,
            'identifier_hash__in': hashes,
        }
        return FeedImportIdentifier.objects.filter(**kwargs).exists()

    def mark_seen(self, vidscraper_video):
        hashes = self._get_identifier_hashes(vidscraper_video)
        # TODO: Use bulk_create.
        for identifier_hash in hashes:
            kwargs = {
                'feed': self.feed,
                'identifier_hash': identifier_hash,
            }
            FeedImportIdentifier.objects.create(**kwargs)

    def run(self):
        auto_authors = list(self.feed.auto_authors.all())
        auto_categories = list(self.feed.auto_categories.all())
        try:
            iterators = self.feed.get_iterators()
        except Exception:
            self.record_step(FeedImportStep.IMPORT_ERRORED,
                             with_traceback=True)
            return
        for iterator in iterators:
            try:
                for vidscraper_video in iterator:
                    try:
                        vidscraper_video.load()
                        if self.is_seen(vidscraper_video):
                            self.record_step(FeedImportStep.VIDEO_SEEN)
                            if self.feed.stop_if_seen:
                                break
                            else:
                                continue
                        video = Video.from_vidscraper_video(
                            vidscraper_video,
                            status=Video.UNPUBLISHED,
                            commit=False,
                            feed=self.feed,
                            sites=self.feed.sites.all(),
                            authors=auto_authors,
                            categories=auto_categories,
                            update_index=False,
                        )
                        try:
                            video.clean_fields()
                            video.validate_unique()
                        except ValidationError:
                            self.record_step(FeedImportStep.VIDEO_INVALID,
                                             with_traceback=True)

                        video.save(update_index=False)
                        try:
                            video.save_m2m()
                        except Exception:
                            video.delete()
                            raise
                        self.mark_seen(vidscraper_video)
                        self.record_step(FeedImportStep.VIDEO_IMPORTED,
                                         video=video)
                    except Exception:
                        self.record_step(FeedImportStep.VIDEO_ERRORED,
                                         with_traceback=True)
                    # Update timestamp (and potentially counts) after each
                    # video.
                    self.save()
            except Exception:
                self.record_step(FeedImportStep.IMPORT_ERRORED,
                                 with_traceback=True)

        # Pt 2: Mark videos active all at once.
        if not self.feed.moderate_imported_videos:
            to_publish = Video.objects.filter(feedimportstep__feed_import=self,
                                              status=Video.UNPUBLISHED)
            for receiver, response in pre_feed_import_publish.send_robust(
                    sender=self, to_publish=to_publish):
                if response:
                    # Basic sanity check: should be a video queryset.
                    if (isinstance(response, models.Queryset) and
                            response.model == Video):
                        to_publish = response
                    else:
                        if isinstance(response, Exception):
                            warnings.warn("pre_feed_import_publish listener "
                                          "raised exception")
                        else:
                            warnings.warn("pre_feed_import_publish returned "
                                          "incorrect response")

            to_publish.update(status=Video.PUBLISHED)
            published = Video.objects.filter(feedimportstep__feed_import=self,
                                             status=Video.PUBLISHED,
                                             published_datetime=now())
            post_feed_import_publish.send_robust(sender=self,
                                                 published=published)

        Video.objects.filter(feedimportstep__feed_import=self,
                             status=Video.UNPUBLISHED
                             ).update(status=Video.NEEDS_MODERATION)
        self.is_complete = True
        self.save()

    def record_step(self, step_type, video=None, with_traceback=False):
        if step_type in (FeedImportStep.VIDEO_ERRORED,
                         FeedImportStep.IMPORT_ERRORED):
            self.error_count += 1
        if step_type == FeedImportStep.VIDEO_IMPORTED:
            self.import_count += 1
        tb = traceback.format_exc() if with_traceback else ''
        self.steps.create(step_type=step_type,
                          video=video,
                          traceback=tb)


class FeedImportStep(models.Model):
    #: Something errored on the import level.
    IMPORT_ERRORED = 'import errored'
    #: A video was found to already be in the database - i.e. previously
    #: imported.
    VIDEO_SEEN = 'video seen'
    #: Something semi-expected is wrong with the video which prevents
    #: it from being imported.
    VIDEO_INVALID = 'video invalid'
    #: Something unexpected happened during an import of a video.
    VIDEO_ERRORED = 'video errored'
    #: A video was successfully imported.
    VIDEO_IMPORTED = 'video imported'
    STEP_TYPE_CHOICES = (
        (IMPORT_ERRORED, _(u'Import errored')),
        (VIDEO_SEEN, _(u'Video seen')),
        (VIDEO_INVALID, _(u'Video invalid')),
        (VIDEO_ERRORED, _(u'Video errored')),
        (VIDEO_IMPORTED, _(u'Video imported')),
    )
    step_type = models.CharField(max_length=14,
                                 choices=STEP_TYPE_CHOICES)
    video = models.OneToOneField('Video',
                                 blank=True,
                                 null=True,
                                 on_delete=models.SET_NULL)
    traceback = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    feed_import = models.ForeignKey(FeedImport, related_name='steps')

    def __unicode__(self):
        return unicode(self.step_type)


class Feed(models.Model):
    """
    Represents an automated feed import in the database.

    """
    sites = models.ManyToManyField(Site)
    thumbnail = models.ImageField(
        upload_to='djvidscraper/feed/thumbnail/%Y/%m/%d/',
        blank=True,
        max_length=255)

    modified_timestamp = models.DateTimeField(auto_now=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)

    moderate_imported_videos = models.BooleanField(default=False)
    disable_automatic_imports = models.BooleanField(default=False)

    # Feeds are expected to stay in the same order.
    stop_if_seen = models.BooleanField(default=True)

    #: Original url entered by a user when adding this feed.
    original_url = models.URLField(max_length=400)

    # Feed metadata
    name = models.CharField(max_length=250, blank=True)
    description = models.TextField(blank=True)
    #: Webpage where the contents of this feed could be browsed.
    web_url = models.URLField(blank=True, max_length=400)

    # Cached information from the import.
    external_etag = models.CharField(max_length=250, blank=True)
    external_last_modified = models.DateTimeField()

    update_metadata = models.BooleanField(default=True)

    def __unicode__(self):
        return self.name

    def start_import(self):
        imp = FeedImport()
        imp.feed = self
        imp.save()
        imp.run()

    @models.permalink
    def get_absolute_url(self):
        return ('localtv_list_feed', [self.pk])

    def get_iterators(self):
        iterator = vidscraper.auto_feed(
            self.original_url,
            # We'll stop at the first previously-seen video.
            max_results=None,
            api_keys=get_api_keys(),
        )
        iterator.load()

        save = False

        etag = getattr(iterator, 'etag', None) or ''
        if (etag and etag != self.etag):
            self.etag = etag
            save = True

        if self.update_metadata:
            # If these fields have already been changed, don't
            # override those changes. Don't unset the name field
            # if no further data is available.
            if self.name == self.original_url:
                self.name = iterator.title or self.name
            if not self.external_url:
                self.external_url = iterator.webpage or ''
            if not self.description:
                self.description = iterator.description or ''
            # Only do this on the first run (for now.)
            self.update_metadata = False
            save = True

        if save:
            self.save()

        return [iterator]


class Video(models.Model):
    UNPUBLISHED = 'unpublished'
    NEEDS_MODERATION = 'needs moderation'
    PUBLISHED = 'published'
    HIDDEN = 'hidden'

    STATUS_CHOICES = (
        (UNPUBLISHED, _(u'Unpublished')),
        (NEEDS_MODERATION, _(u'Needs moderation')),
        (PUBLISHED, _(u'Published')),
        (HIDDEN, _(u'Hidden')),
    )

    # Video core data
    #: This field contains a URL which a user gave as "the" URL
    #: for this video. It may or may not be the same as ``external_url``
    #: or a file url. It may not even exist, if they're using embedding.
    original_url = models.URLField(max_length=400, blank=True)

    # Video metadata
    #: Canonical web home of the video as best as we can tell.
    web_url = models.URLField(max_length=400, blank=True)
    embed_code = models.TextField(blank=True)
    flash_enclosure_url = models.URLField(max_length=400, blank=True)
    name = models.CharField(max_length=250)
    description = models.TextField(blank=True)
    thumbnail = models.ImageField(
        upload_to='djvidscraper/video/thumbnail/%Y/%m/%d/',
        blank=True,
        max_length=255)
    guid = models.CharField(max_length=250, blank=True)

    # Owner info. Owner is the person who created the video. Should always
    # have editing access.
    owner = models.ForeignKey('auth.User', null=True, blank=True)
    owner_email = models.EmailField(max_length=250,
                                    blank=True)
    owner_session = models.ForeignKey('sessions.Session',
                                      blank=True, null=True)

    # Cached information from vidscraper.
    external_user_username = models.CharField(max_length=250, blank=True)
    external_user_url = models.URLField(blank=True, max_length=400)
    external_thumbnail_url = models.URLField(blank=True, max_length=400)
    external_thumbnail_tries = models.PositiveSmallIntegerField(default=0)
    external_published_datetime = models.DateTimeField(null=True, blank=True)

    # Other internal use.
    sites = models.ManyToManyField(Site)
    status = models.CharField(max_length=16,
                              choices=STATUS_CHOICES,
                              default=UNPUBLISHED)
    modified_timestamp = models.DateTimeField(auto_now=True)
    created_timestamp = models.DateTimeField(auto_now_add=True)
    published_datetime = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-published_datetime', '-modified_timestamp']

    def __unicode__(self):
        return self.name

    @classmethod
    def from_vidscraper_video(cls, video, status=None, commit=True,
                              feed=None, sites=None):
        """
        Builds a :class:`Video` instance from a
        :class:`vidscraper.videos.Video` instance. If `commit` is False,
        the :class:`Video` will not be saved, and the created instance will
        have a `save_m2m()` method that must be called after you call `save()`.

        """
        pre_video_import.send_robust(sender=cls, vidscraper_video=video)

        if status is None:
            status = cls.NEEDS_MODERATION

        instance = cls(
            guid=video.guid or '',
            name=video.title or '',
            description=video.description or '',
            published_datetime=now() if status == cls.PUBLISHED else None,
            status=status,
            external_url=video.link or '',
            external_published_datetime=video.publish_datetime,
            external_thumbnail_url=video.thumbnail_url or '',
            embed_code=video.embed_code or '',
            flash_enclosure_url=video.flash_enclosure_url or '',
            external_user_username=video.user or '',
            external_user_url=video.user_url or '',
            feed=feed,
        )

        if not sites:
            sites = [Site.objects.get_current()]

        def save_m2m():
            instance.sites = sites
            if video.files:
                for video_file in video.files:
                    if video_file.expires is None:
                        VideoFile.objects.create(video=instance,
                                                 url=video_file.url,
                                                 length=video_file.length,
                                                 mimetype=video_file.mime_type)
            instance.download_external_thumbnail()
            post_video_import.send_robust(sender=cls, instance=instance,
                                          vidscraper_video=video)

        if commit:
            instance.save()
            save_m2m()
        else:
            instance.save_m2m = save_m2m
        return instance

    def download_external_thumbnail(self, override_thumbnail=False):
        """Try to download and save an external thumbnail."""
        if not self.external_thumbnail_url:
            return
        if self.thumbnail and not override_thumbnail:
            return
        from django.conf import settings
        max_retries = getattr(settings,
                              'DJVIDSCRAPER_MAX_DOWNLOAD_RETRIES',
                              3)
        if self.external_thumbnail_tries > max_retries:
            return
        try:
            final_path = download_thumbnail(self.external_thumbnail_url,
                                            self,
                                            'thumbnail')
        except Exception:
            self.external_thumbnail_tries += 1
            self.save()
        else:
            try:
                self.thumbnail = final_path
                self.save()
            except Exception:
                default_storage.delete(final_path)

    download_external_thumbnail.alters_data = True


class VideoFile(models.Model):
    video = models.ForeignKey(Video, related_name='files')
    url = models.URLField(max_length=2048)
    length = models.PositiveIntegerField(null=True, blank=True)
    mimetype = models.CharField(max_length=60, blank=True)

    def fetch_metadata(self):
        """
        Do a HEAD request on self.url to try to get metadata
        (self.length and self.mimetype).

        Note that while this method fills in those attributes, it does *not*
        call self.save() - so be sure to do so after calling this method!

        """
        if not self.url:
            return

        try:
            response = requests.head(self.url, timeout=5)
            if response.status_code == 302:
                response = requests.head(response.headers['location'],
                                         timeout=5)
        except Exception:
            pass
        else:
            if response.status_code != 200:
                return
            self.length = response.headers.get('content-length')
            self.mimetype = response.headers.get('content-type', '')
            if self.mimetype in ('application/octet-stream', ''):
                # We got a not-useful MIME type; guess!
                guess = mimetypes.guess_type(self.url)
                if guess[0] is not None:
                    self.mimetype = guess[0]


class WatchManager(models.Manager):
    def from_request(self, request, video):
        """
        Creates a Watch based on an HTTP request.  If the request came
        from localhost, check to see if it was forwarded to (hopefully) get the
        right IP address.

        """
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        ip = request.META.get('REMOTE_ADDR', '0.0.0.0')
        if not ipv4_re.match(ip):
            ip = '0.0.0.0'

        if hasattr(request, 'user') and request.user.is_authenticated():
            user = request.user
        else:
            user = None

        self.create(video=video,
                    user=user,
                    ip_address=ip,
                    user_agent=user_agent)


class Watch(models.Model):
    """
    Record of a video being watched.

    """
    video = models.ForeignKey(Video)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey('auth.User', blank=True, null=True)
    ip_address = models.IPAddressField()
    # Watch queries may want to exlude "bot", "spider", "crawler", etc.
    # from counts.
    user_agent = models.CharField(max_length=255, blank=True)

    objects = WatchManager()
