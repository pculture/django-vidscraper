import os
import urlparse

from daguerre.utils import make_hash, KEEP_FORMATS, DEFAULT_FORMAT
from django.core.files.base import File
from django.core.files.storage import default_storage
from django.core.files.temp import NamedTemporaryFile
from django.utils.encoding import iri_to_uri
from django.utils.timezone import now
import requests
try:
    from PIL import Image
except ImportError:
    import Image


API_KEY_MAP = {
    'vimeo_key': 'VIMEO_API_KEY',
    'vimeo_secret': 'VIMEO_API_SECRET',
    'ustream_key': 'USTREAM_API_KEY',
    'youtube_key': 'YOUTUBE_API_KEY',
}


def get_api_keys():
    from django.conf import settings
    return dict((k, getattr(settings, v))
                for k, v in API_KEY_MAP.iteritems()
                if getattr(settings, v, None) is not None)


def download_thumbnail(url, instance, field_name):
    """
    Downloads a thumbnail and stores it in the given instance field. Returns
    final storage path.

    """
    url = iri_to_uri(url)
    response = requests.get(url, stream=True)
    if response.status_code != 200:
        raise Exception

    temp = NamedTemporaryFile()
    # May raise IOError.
    temp.write(response.raw.read())

    temp.seek(0)
    # May raise various Exceptions.
    im = Image.open(temp)
    im.verify()

    ext = os.splitext(urlparse.urlsplit(url).path)[1]

    args = (url, now().isoformat())
    filename = ''.join((make_hash(*args, step=2), ext))

    f = instance._meta.get_field(field_name)
    storage_path = f.generate_filename(instance, filename)

    return default_storage.save(storage_path, File(temp))
