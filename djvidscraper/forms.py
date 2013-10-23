from django import forms
import vidscraper

from djvidscraper.models import Video


class CreateVideoForm(forms.ModelForm):
    class Meta:
        fields = ('original_url',)

    def save(self, commit=True, request=None):
        kwargs = {
            'video': vidscraper.auto_scrape(self.cleaned_data['original_url']),
            'commit': False,
        }

        if request and request.user.is_authenticated():
            kwargs['owner'] = request.user

        instance = Video.from_vidscraper_video(**kwargs)

        def save_m2m():
            instance.save_m2m()

        if commit:
            instance.save()
            save_m2m()
        else:
            self.save_m2m = save_m2m
        return instance
