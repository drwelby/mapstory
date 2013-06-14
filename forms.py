from django import forms
from django.contrib.gis.geos import Point
from account.forms import SignupForm
from geonode.maps.models import Layer
from mapstory.models import ContactDetail
from mapstory.models import Annotation
from mapstory.util import datetime_to_seconds
import datetime
import json
import taggit


class LayerForm(forms.ModelForm):
    '''we have metadata needs/desires different from what geonode gives.
    ignore a bunch of stuff and make sure others are optional
    '''
    
    keywords = taggit.forms.TagField(required=False)
    abstract = forms.CharField(required=False)
    purpose = forms.CharField(required=False)
    supplemental_information = forms.CharField(required=False)
    data_quality_statement = forms.CharField(required=False)

    class Meta:
        model = Layer
        exclude = ('contacts','workspace', 'store', 'name', 'uuid', 'storeType', 'typename') + \
        ('temporal_extent_start', 'temporal_extent_end', 'topic_category') + \
        ('keywords_region','geographic_bounding_box','constraints_use','date','date_type')


class StyleUploadForm(forms.Form):
    
    layerid = forms.IntegerField()
    name = forms.CharField(required=False)
    update = forms.BooleanField(required=False)
    sld = forms.FileField()
    


class ProfileForm(forms.ModelForm):
    '''Unified user/contact/contactdetail form.
    Override the defaults with our requirements:
    hide some fields, make some required, others not
    allow saving some user fields here'''

    first_name = forms.CharField()
    last_name = forms.CharField()
    email = forms.EmailField()
    blurb = forms.CharField(widget=forms.Textarea)
    biography = forms.CharField(widget=forms.Textarea, required=False)
    education = forms.CharField(widget=forms.Textarea, required=False)
    expertise = forms.CharField(widget=forms.Textarea, required=False)

    def __init__(self, *args, **kw):
        super(ProfileForm, self).__init__(*args, **kw)
        # change the order they appear in
        order = ('first_name', 'last_name', 'blurb', 'email')
        fields = self.fields
        self.fields = type(fields)()
        for o in order:
            self.fields[o] = fields[o]
        self.fields.update(fields)
        user = self.instance.user
        # displaying the contents of user
        self.initial['first_name'] = user.first_name
        self.initial['last_name'] = user.last_name
        # display the user email if contact not set, change propogated on save
        if not self.initial['email']:
            self.initial['email'] = user.email

    def save(self, *args, **kw):
        data = self.cleaned_data
        first_name = data['first_name']
        last_name = data['last_name']
        # make the contactdetail.name field match first_name,last_name
        if all([first_name, last_name]):
            self.instance.name = '%s %s' % (first_name, last_name)
        super(ProfileForm, self).save(*args, **kw)
        # now copy first and last name to user
        user = self.instance.user
        user.first_name = first_name
        user.last_name = last_name
        # and copy the email in - already saved to contact above
        user.email = data['email']
        user.save(*args, **kw)
        # and verify profile completeness
        self.instance.update_audit()

    class Meta:
        model = ContactDetail
        exclude = ('user','fax','delivery','zipcode','area','links','name','voice')
        

class CheckRegistrationForm(SignupForm):
    '''add a honey pot field and verification of a hidden client generated field'''
    
    not_human = forms.BooleanField(
                widget=forms.HiddenInput,
                required = False)

    def clean(self):
        if not self.data.get('tos',None):
            raise forms.ValidationError('You must agree to the Terms of Service.')
        return self.cleaned_data

    def clean_not_human(self):
        if self.cleaned_data['not_human']:
            raise forms.ValidationError('')


class AnnotationForm(forms.ModelForm):
    def full_clean(self):
        if 'geometry' in self.data:
            # @todo - optimize me, round tripping json
            self.data['the_geom'] = json.dumps(self.data['geometry'])
        if 'lat' in self.data:
            self.data['the_geom'] = Point(float(self.data['lon']), float(self.data['lat']))
        self._convert_time('start_time')
        self._convert_time('end_time')
        super(AnnotationForm, self).full_clean()

    def _convert_time(self, key):
        val = self.data.get(key, None)
        if not val: return
        numeric = None
        try:
            numeric = int(val)
        except ValueError:
            pass
        if not numeric:
            fmts = (
                '%Y',
                '%Y-%m',
                '%Y-%m-%d',
                '%Y-%m-%dT%H:%M:%S',
            )
            parsed = None
            for f in fmts:
                try:
                    parsed = datetime.datetime.strptime(val, f)
                    break
                except:
                    pass
            if parsed is None:
                self._errors[key] = ['Unable to parse "%s"' % val]
                return
            numeric = int(datetime_to_seconds(parsed))

        self.data[key] = str(numeric)


    class Meta:
        model = Annotation