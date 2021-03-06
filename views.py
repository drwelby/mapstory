from geonode.maps.models import Map
from geonode.maps.models import Layer
from geonode.maps.models import MapLayer
from geonode.maps.models import Thumbnail
from geonode.maps.utils import forward_mercator
from geonode.maps.views import json_response

from geoserver.catalog import ConflictingDataError

from mapstory import models
from mapstory.util import lazy_context
from mapstory.util import render_manual
from mapstory.util import unicode_csv_dict_reader
from mapstory.forms import AnnotationForm
from mapstory.forms import CheckRegistrationForm
from mapstory.forms import StyleUploadForm
from mapstory.forms import LayerForm
import account.views

from dialogos.models import Comment

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.paginator import Paginator
from django.core.paginator import EmptyPage
from django.core.exceptions import PermissionDenied
from django.core.urlresolvers import reverse
from django.conf import settings
from django.db.models import signals
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.http import HttpResponseForbidden
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.template import loader
from django.template import defaultfilters as filters
from django.contrib.contenttypes.models import ContentType

from provider.oauth2.models import AccessToken
from django.utils.timezone import now as provider_now


from lxml import etree
import csv
import json
import math
import os
import random

def alerts(req): 
    return render_to_response('mapstory/alerts.html', RequestContext(req))

@lazy_context
def lazy_tiles():
    return ''.join( [ _render_map_tile(m) for m in get_map_carousel_maps()] )

def index(req):
    # resolve video to use
    # two modes of operation here
    # 1) don't specify publish and one will randomly be chosen
    # 2) specify one or more publish links and one will be chosen

    essays = list(models.Essay.objects.filter(publish=True))
    random.shuffle(essays)
    return render_to_response('index.html', RequestContext(req,{
        "video" : models.VideoLink.objects.front_page_video(),
        "tiles" : lazy_tiles(),
        "essays" : essays
    }))

def how_to(req):
    return render_to_response('mapstory/how_to.html', RequestContext(req,{
        'videos' : models.VideoLink.objects.how_to_videos()
    }))
    
def reflections(req):
    return render_to_response('mapstory/reflections.html', RequestContext(req,{
        'videos' : models.VideoLink.objects.reflections_videos()
    }))
    
def admin_manual(req):
    if not req.user.is_staff:
        return HttpResponse("Not Allowed", status=400)
    html = render_manual('admin.rst')
    return render_to_response('mapstory/manual.html', RequestContext(req,{
        'content' : html
    }))
    
def manual(req):
    html = render_manual('manual.rst')
    if 'test' in req.GET:
        return HttpResponse(html)
    return render_to_response('mapstory/manual.html', RequestContext(req,{
        'content' : html
    }))


def _get_requested_page(req):
    try:
        return int(req.REQUEST.get('page',1)) if req else 1
    except ValueError, ex:
        if settings.DEBUG:
            raise ex
        return 1


def _related_stories_pager(section=None, map_obj=None):
    if section:
        target = get_object_or_404(models.Section, slug=section)
    else:
        target = map_obj
    related = models.get_related_stories(target)
    return target, Paginator(related, 5)


def _related_stories_page(req, section=None, map_obj=None):
    target, pager = _related_stories_pager(section=section, map_obj=map_obj)
    page_num = _get_requested_page(req)
    page = None
    try:
        page = pager.page(page_num)
    except EmptyPage:
        raise Http404()
    return target, page


def related_mapstories_pager(req, map_id):
    map_obj = get_object_or_404(Map, id=map_id)
    target, page = _related_stories_page(req, map_obj=map_obj)
    return _story_tiles(req, page)


def _story_tiles(req, page):
    link = tiles = ''
    if page:
        tiles = ''.join([ loader.render_to_string("mapstory/_story_tile_left.html",
                        {'map':r, 'when':r.last_modified}) for r in page])
        link = "<a href='%s?page=%s' class='next'></a>" % (req.path, page.next_page_number()) if page.has_next() else ''
    return HttpResponse('<div>%s%s</div>' % (tiles,link))


def section_tiles(req, section):
    sec, page = _related_stories_page(req, section=section)
    return _story_tiles(req, page)


def section_detail(req, section):
    sec, pager = _related_stories_page(req, section=section)
    return render_to_response('mapstory/section_detail.html', RequestContext(req,{
        'section' : sec,
        'pager' : pager
    }))


def resource_detail(req, resource):
    res = get_object_or_404(models.Resource, slug=resource)
    return render_to_response('mapstory/resource.html', RequestContext(req,{
        'can_edit' : req.user.is_superuser,
        'resource' : res
    }))


def get_map_carousel_maps():
    '''Get the carousel ids/thumbnail dict either
    1. as specified (model does not exist yet...)
    2. by some rating/view ranking (not implemented)
    3. any map that has a thumbnail (current)
    '''
    
    favorites = models.Favorite.objects.favorite_maps_for_user(User.objects.get(username='admin'))
    if favorites.count() > 3:
        favorites = random.sample(favorites, min(10,favorites.count()))
        return [ f.content_object for f in favorites ]
    
    # get all Map thumbnails
    thumb_type = ContentType.objects.get_for_model(Map)
    thumbs = Thumbnail.objects.filter(content_type__pk=thumb_type.id)
    thumbs = thumbs.filter(object_id__in = Map.objects.filter(publish__status='Public'))
    # trim this down to a smaller set
    thumbs = random.sample(thumbs, min(10,len(thumbs)))
    # and make sure they have a valid file path
    return [ t.content_object for t in thumbs if os.path.exists(t.get_thumbnail_path())]

def map_tiles(req):
    maps = get_map_carousel_maps()
    return HttpResponse(''.join( [ _render_map_tile(m) for m in maps] ))

def _render_map_tile(obj,req=None):
    template = 'mapstory/_story_tile.html'
    ctx = {'map':obj,'when':obj.last_modified}
    if req:
        return render_to_response(template, RequestContext(req,ctx))
    return loader.render_to_string(template,ctx)

def map_tile(req, mapid):
    obj = get_object_or_404(Map,pk=mapid)
    return _render_map_tile(obj,req=req)


@login_required
def favoriteslinks(req):
    ident = req.GET['ident']
    layer_or_map, id = ident.split('-')
    if layer_or_map == 'map':
        obj = get_object_or_404(Map, pk = id)
        maps = models.PublishingStatus.objects.get_in_progress(req.user,Map)
    elif layer_or_map == 'layer':
        obj = get_object_or_404(Layer, pk = id)
        maps = None
    # only create these links if the user is an Org
    elif layer_or_map == 'owner' and models.Org.objects.filter(user=req.user).count():
        obj = get_object_or_404(User, username = id)
        maps = None
    else:
        return HttpResponse('')
    return render_to_response("simplesearch/_widget_search_favorites.html",{
        layer_or_map : obj,
        "maps" : maps,
        "user" : req.user
    });


@login_required
def favoriteslist(req):
    ctx = {
        "favorites" : models.Favorite.objects.favorites_for_user(req.user),
        "in_progress_maps" : Map.objects.filter(owner=req.user).exclude(publish__status='Public'),
        "in_progress_layers" : Layer.objects.filtered().filter(owner=req.user).exclude(publish__status='Public')
    }
    return render_to_response("mapstory/_widget_favorites.html",ctx)


def _error_response(message, extra='', extra_class=''):
    return ("<div class='mrg-top errorlist'><p class='alert %s'>%s</p>%s</div>" %
        (extra_class, message, extra))


@login_required
def layer_metadata(request, layername):
    '''ugh, override the default'''
    layer = get_object_or_404(Layer, typename=layername)
    if not request.user.has_perm('maps.change_layer', obj=layer):
        return HttpResponse(loader.render_to_string('401.html', 
            RequestContext(request, {'error_message': 
                "You are not permitted to modify this layer's metadata"})), status=401)
    if request.method == "POST":
        form = LayerForm(request.POST, prefix="layer")
        if form.is_valid():
            # @todo should we allow redacting metadata once the layer is 'published'?
            layer.title = form.cleaned_data['title']
            layer.keywords.add(*form.cleaned_data['keywords'])
            layer.abstract = form.cleaned_data['abstract']
            layer.purpose = form.cleaned_data['purpose']
            layer.language = form.cleaned_data['language']
            layer.supplemental_information = form.cleaned_data['supplemental_information']
            layer.data_quality_statement = form.cleaned_data['data_quality_statement']
            if not models.audit_layer_metadata(layer):
                msg = _error_response((
                    'The metadata was updated but is incomplete.<br>'
                    'You will not be able to publish until completed.'
                ))
                # roll back to private if changes have invalidated metadata
                models.PublishingStatus.objects.set_status(layer, 'Private')
                resp = HttpResponse(msg, status=400)
            else:
                resp = HttpResponse('OK')
            layer.save()
            return resp
        else:
            errors = _error_response('There were errors in the data provided:',
                                     form.errors.as_ul(), 'alert-error')
            return HttpResponse(errors, status=400)
    # old 'geonode' api, just redirect to layer page
    return HttpResponseRedirect(reverse('data_detail', args=[layer.typename]))
    
@login_required
def favorite(req, subject, id):
    if subject == 'map':
        obj = get_object_or_404(Map, pk = id)
    elif subject == 'layer':
        obj = get_object_or_404(Layer, pk = id)
    elif subject == 'user':
        obj = get_object_or_404(User, pk = id)
    models.Favorite.objects.create_favorite(obj, req.user)
    return HttpResponse('OK', status=200)

@login_required
def delete_favorite(req, id):
    models.Favorite.objects.get(user=req.user, pk=id).delete()
    return HttpResponse('OK', status=200)


@login_required
def publish_status(req, layer_or_map, layer_or_map_id):
    if req.method != 'POST':
        return HttpResponse('POST required',status=400)
    model = Map if layer_or_map == 'map' else Layer
    obj = _resolve_object(req, model, 'mapstory.change_publishingstatus',
                          allow_owner=True, id=layer_or_map_id)

    status = req.POST['status']

    # allow superuser to fix stuff no matter and we'll allow junk in Private
    if not req.user.is_superuser and status != 'Private':
        # verify metadata is completed or reject
        if isinstance(obj, Layer):
            layers = [obj]
        else:
            layers = obj.local_layers
            if not models.audit_map_metadata(obj):
                return HttpResponse('META', status=200)
        for l in layers:
            if not models.audit_layer_metadata(l):
                return HttpResponse('META', status=200)

    models.PublishingStatus.objects.set_status(obj, status)
    # this updates status of the current user's layers unless admin (does all)
    obj.publish.update_related(ignore_owner=req.user.is_superuser)

    return HttpResponse('OK', status=200)


@login_required
def add_to_map(req,id,typename):
    if req.method != 'POST':
        return HttpResponse('POST required',status=400)
    mapobj = get_object_or_404(Map, id=id)
    if mapobj.owner != req.user and not req.user.has_perm('maps.change_map', mapobj):
        return HttpResponse('Not sufficient permissions',status=401)
    layer = get_object_or_404(Layer, typename=typename)
    existing = MapLayer.objects.filter(map = mapobj)
    vs_url = settings.GEOSERVER_BASE_URL + '%s/%s/wms' % tuple(layer.typename.split(':'))
    stack_order = max([l.stack_order for l in existing]) + 1
    # have to use local name, not full typename when using ows_url
    maplayer = MapLayer(name = layer.name, ows_url=vs_url, map=mapobj, stack_order=stack_order)
    maplayer.save()
    # if bounding box is equivalent to default, compute and save
    ints = lambda t: map(int,t)
    if ints(mapobj.center) == ints(forward_mercator(settings.DEFAULT_MAP_CENTER)):
        bbox = layer.resource.latlon_bbox[0:4]
        # @todo copy-paste from geonode.maps.views - extract this for reuse
        minx, maxx, miny, maxy = [float(c) for c in bbox]
        x = (minx + maxx) / 2
        y = (miny + maxy) / 2

        center = forward_mercator((x, y))
        if center[1] == float('-inf'):
            center = (center[0], 0)

        if maxx == minx:
            width_zoom = 15
        else:
            width_zoom = math.log(360 / (maxx - minx), 2)
        if maxy == miny:
            height_zoom = 15
        else:
            height_zoom = math.log(360 / (maxy - miny), 2)

        mapobj.center_x = center[0]
        mapobj.center_y = center[1]
        mapobj.zoom = math.ceil(min(width_zoom, height_zoom))
        mapobj.save()
    return HttpResponse('OK', status=200)


def _by_storyteller_pager(req, user, what):
    if what == 'maps':
        query = models.PublishingStatus.objects.get_public(user, Map, req.user)
        exclude = req.GET.get('exclude', None) if req else None
        if exclude:
            query = query.exclude(id=exclude)
    elif what == 'layers':
        query = models.PublishingStatus.objects.get_public(user, Layer, req.user)
        for e in settings.LAYER_EXCLUSIONS:
            query = query.exclude(name__regex=e)
    else:
        return HttpResponse(status=400)

    return Paginator(query, 5)


def about_storyteller(req, username):
    user = get_object_or_404(User, username=username)
    return render_to_response('mapstory/about_storyteller.html', RequestContext(req,{
        "storyteller" : user,
    }))


def _storyteller_activity_pager(user, what):
    if what == 'actions':
        query = user.actor_actions.public()
    else:
        query = user.useractivity.other_actor_actions.all()
    return Paginator(query, 5, allow_empty_first_page=True)


def storyteller_activity_pager(req, username, what='actions'):
    user = get_object_or_404(User, username=username)
    from mapstory.templatetags.mapstory_tags import activity_item
    pager = _storyteller_activity_pager(user, what)
    page_num = _get_requested_page(req)
    page = None
    try:
        page = pager.page(page_num)
    except EmptyPage:
        raise Http404()
    link = tiles =  ''
    if page:
        show_link = what != 'actions'
        tiles = ''.join([activity_item(i, show_link) for i in page])
        link = "<a href='%s?page=%s' class='next'></a>" % (req.path, page.next_page_number()) if page.has_next() else ''
    return HttpResponse('<div>%s%s</div>' % (tiles,link))


def by_storyteller_pager(req, user, what):
    user = get_object_or_404(User, username=user)
    pager = _by_storyteller_pager(req, user, what)
    page_num = _get_requested_page(req)
    page = None
    try:
        page = pager.page(page_num)
    except EmptyPage:
        raise Http404()
    link = tiles = ''
    when = lambda o: o.last_modified if what == 'maps' else o.date
    if pager:
        tiles = ''.join([ loader.render_to_string("mapstory/_story_tile_left.html",
                   {'map': r, 'when': when(r)}) for r in page])
        link = "<a href='%s?page=%s' class='next'></a>" % (req.path, page.next_page_number()) if page.has_next() else ''
    return HttpResponse('<div>%s%s</div>' % (tiles,link))


def delete_story_comment(req, layer_or_map, layer_or_map_id):
    '''allow a user to delete comments attached to their layer or map'''
    pass


def flag_comment(req):
    ct = ContentType.objects.get_for_model(Comment)
    return render_to_response("flag/flag_form.html", RequestContext(req, {
        'object_id' : req.GET['id'],
        'content_type' : ct.id,
        'creator_field' : 'author',
        'flag_type' : 'inappropriate'
    }))
    
@login_required
def topics_api(req, layer_or_map, layer_or_map_id):
    if layer_or_map == 'map':
        obj = get_object_or_404(Map, pk = layer_or_map_id)
        perm = 'maps.change_map'
    else:
        obj = get_object_or_404(Layer, pk = layer_or_map_id)
        perm = 'maps.change_layer'
    if obj.owner != req.user and not req.user.has_perm(perm, obj):
        return HttpResponse('Not sufficient permissions',status=401)
        
    if req.method == 'GET':
        pass
    elif req.method == 'POST':
        topics = req.POST['topics']
        models.Topic.objects.tag(obj,topics)
    if req.method != 'POST':
        return HttpResponse(status=400)
    
    return HttpResponse('OK', status=200)

class SignupView(account.views.SignupView):

   form_class = CheckRegistrationForm

@transaction.commit_on_success()
def annotations(req, mapid):
    '''management of annotations for a given mapid'''
    #todo cleanup and break apart
    if req.method == 'GET':
        cols = [ 'title', 'content', 'start_time', 'end_time', 'in_map', 'in_timeline', 'appearance' ]

        mapobj = _resolve_object(req, models.Map, 'maps.view_map',
                                 allow_owner=True, id=mapid)
        ann = models.Annotation.objects.filter(map=mapid)
        ann = ann.order_by('start_time','end_time')
        if bool(req.GET.get('in_map', False)):
            ann = ann.filter(in_map=True)
        if bool(req.GET.get('in_timeline', False)):
            ann = ann.filter(in_timeline=True)
        if 'page' in req.GET:
            page = int(req.GET['page'])
            page_size = 25
            start = page * page_size
            end = start + page_size
            ann = ann[start:end]
        if 'csv' in req.GET:
            response = HttpResponse(mimetype='text/csv')
            response['Content-Disposition'] = 'attachment; filename=map-%s-annotations.csv' % mapobj.id
            response['Content-Encoding'] = 'utf-8'
            writer = csv.writer(response)
            writer.writerow(cols)
            sidx = cols.index('start_time')
            eidx = cols.index('end_time')
            # default csv writer chokes on unicode
            encode = lambda v: v.encode('utf-8') if isinstance(v, basestring) else str(v)
            get_value = lambda a, c: getattr(a, c) if c not in ('start_time','end_time') else ''
            for a in ann:
                vals = [ encode(get_value(a, c)) for c in cols ]
                vals[sidx] = a.start_time_str
                vals[eidx] = a.end_time_str
                writer.writerow(vals)
            return response
        # strip the superfluous id, it will be added at the feature level
        props = [ c for c in cols if c != 'id' ]
        def encoder(query_set):
            results = []
            for res in query_set:
                feature = { 'id' : res.id}
                if res.the_geom:
                    geometry = {}
                    geometry['type'] = res.the_geom.geom_type
                    geometry['coordinates'] = res.the_geom.coords
                    feature['geometry'] = geometry
                fp = feature['properties'] = {}
                for p in props:
                    val = getattr(res, p)
                    if val is not None:
                        fp[p] = val
                results.append(feature)
            return results

        return json_response({'type':'FeatureCollection','features':encoder(ann)})

    if req.method == 'POST':
        mapobj = _resolve_object(req, models.Map, 'maps.change_map',
                                 allow_owner=True, id=mapid)
        # either a bulk upload or a JSON change
        action = 'upsert'
        get_props = lambda r: r
        finish = lambda: None
        created = []
        form_mode = 'client'
        content_type = None
        overwrite = False
        error_format = None

        def id_collector(form):
            created.append(form.instance.id)

        if req.FILES:
            fp = iter(req.FILES.values()).next()
            # ugh, builtin csv reader chokes on unicode
            data = unicode_csv_dict_reader(fp)
            id_collector = lambda f: None
            form_mode = 'csv'
            content_type = 'text/html'
            ids = list(models.Annotation.objects.filter(map=mapobj).values_list('id', flat=True))
            # delete existing, we overwrite
            finish = lambda: models.Annotation.objects.filter(id__in=ids).delete()
            overwrite = True
            def error_format(row_errors):
                response = []
                for re in row_errors:
                    row = re[0] + 1
                    for e in re[1]:
                        response.append('[%s] %s : %s' % (row, e, re[1][e]))
                return 'The following rows had problems:<ul><li>' + '</li><li>'.join(response) + "</li></ul>"
        else:
            data = json.loads(req.body)
            if isinstance(data, dict):
                action = data.get('action', action)
            if 'features' in data:
                data = data.get('features')
                get_props = lambda r: r['properties']

        if action == 'delete':
            models.Annotation.objects.filter(pk__in=data['ids'], map=mapobj).delete()
            return json_response({'success' : True})

        errors = []
        i = None
        for i,r in enumerate(data):
            props = get_props(r)
            props['map'] = mapobj.id
            ann = None
            id = r.get('id', None)
            if id and not overwrite:
                ann = models.Annotation.objects.get(map=mapobj, pk=id)

            # form expects everything in the props, copy geometry in
            if 'geometry' in r:
                props['geometry'] = r['geometry']
            props.pop('id', None)
            form = AnnotationForm(props, instance=ann, form_mode=form_mode)
            if not form.is_valid():
                errors.append((i, form.errors))
            else:
                form.save()
            if id is None:
                id_collector(form)
        if i is None:
            errors = [ (0, 'No data could be read')]
        if errors:
            body = None
            if error_format:
                return HttpResponse(error_format(errors), status=400)
        else:
            finish()
            body = {'success' : True}
            if created:
                body['ids'] = created
        return json_response(body=body, errors=errors, content_type=content_type)

    return HttpResponse(status=400)


@login_required
def create_annotations_layer(req, mapid):
    '''Create an annotations layer with the predefined schema.
    
    @todo ugly hack - using existing view to allow this
    '''
    mapobj = get_object_or_404(Map,pk=mapid)
    
    if req.method != 'POST':
        return HttpResponse('POST required',status=400)
    
    if mapobj.owner != req.user:
        return HttpResponse('Not owner of map',status=401)
    
    atts = [
        #name, type, nillable
        ('title','java.lang.String',False),
        ('content','java.lang.String',False),
        ('the_geom','com.vividsolutions.jts.geom.Geometry',True),
        ('start_time','java.lang.Long',True),
        ('end_time','java.lang.Long',True),
        ('in_timeline','java.lang.Boolean',True),
        ('in_map','java.lang.Boolean',True),
        ('appearance','java.lang.String',True),
    ]
    
    # @todo remove this when hack is resolved. build our spec string
    atts = ','.join([ ':'.join(map(str,a)) for a in atts])
    
    return _create_layer(
        req.user,
        name = "_map_%s_annotations" % mapid,
        srs = 'EPSG:4326', # @todo how to obtain this in a nicer way...
        attributes = atts,
        skip_style = True
    )


@login_required
def upload_style(req):
    def respond(*args,**kw):
        kw['content_type'] = 'text/html'
        return json_response(*args,**kw)
    form = StyleUploadForm(req.POST,req.FILES)
    if not form.is_valid():
        return respond(errors="Please provide an SLD file.")
    
    data = form.cleaned_data
    layer = _resolve_object(req, Layer, "maps.change_layer", 
                            id=data['layerid'])
    
    sld = req.FILES['sld'].read()

    try:
        dom = etree.XML(sld)
    except Exception,ex:
        return respond(errors="The uploaded SLD file is not valid XML")
    
    el = dom.findall("{http://www.opengis.net/sld}NamedLayer/{http://www.opengis.net/sld}Name")
    if len(el) == 0 and not data.get('name'):
        return respond(errors="Please provide a name, unable to extract one from the SLD.")
    name = data.get('name') or el[0].text

    def find_style(name):
        styles = list(layer.styles) + [layer.default_style]
        for style in styles:
            if style.sld_name == name:
                return style

    cat = Layer.objects.gs_catalog
    if data['update']:
        match = find_style(name)
        if match is None:
            if cat.get_style(name) is not None:
                return respond(errors="""A style with this name is used by another layer.
                         Please choose a different name.""")
            return respond(errors="Cannot locate the existing style to update : " + name)
        match.update_body(sld)
    else:
        try:
            cat.create_style(name, sld)
            layer.styles = layer.styles + [ type('style',(object,),{'name' : name}) ]
            cat.save(layer.publishing)
        except ConflictingDataError,e:
            return respond(errors="""A style with this name exists. Select
                                     the update option if you want to update.""")
    return respond(body={'success':True,'style':name,'updated':data['update']})


@login_required
def invite_preview(req):
    # thanks for making this flexible, accounts app :(
    # the email formatting is embedded in the send method... so copy-paste
    protocol = getattr(settings, "DEFAULT_HTTP_PROTOCOL", "http")
    current_site = Site.objects.get_current()
    signup_url = u"%s://%s%s?%s" % (
        protocol,
        unicode(current_site.domain),
        reverse("account_signup"),
        "somerandomstringofletters"
    )
    ctx = {
        "signup_code": {
            "inviter" : req.user
        },
        "current_site": current_site,
        "signup_url": signup_url,
    }
    return render_to_response('account/email/invite_user.txt', ctx)


@login_required
def user_activity_api(req):
    user_activity = req.user.useractivity
    if 'notification_preference' in req.REQUEST:
        user_activity.notification_preference = req.REQUEST['notification_preference']
        user_activity.save()
        return HttpResponse('OK')


def org_page(req, org_slug):
    org = get_object_or_404(models.Org, slug=org_slug)
    content = org.orgcontent_set.filter(name='main')
    # have to resolve using both name and typename due to 'old non-ws-prefixed' layers
    using = models.get_maps_using_layers_of_user(org.user)
    ctx = dict(org=org, org_content=content[0].text if content else None,
               can_edit=req.user.is_superuser or req.user == org.user,
               using=using
               )
    ctx['favs'] = models.Favorite.objects.bulk_favorite_objects(org.user)
    resp = render_to_response('mapstory/orgs/org_page.html', RequestContext(req, ctx))
    return resp


def org_page_api(req, org_slug):
    org = get_object_or_404(models.Org, slug=org_slug)
    if not (req.user == org.user or req.user.is_superuser):
        raise PermissionDenied()
    val = req.POST.get('banner_image', None)
    if val is not None:
        org.banner_image = val
        org.save()
        return HttpResponse(val)
    val = req.POST.get('org_content', None)
    if val is not None:
        cnt, _ = org.orgcontent_set.get_or_create(name='main')
        cnt.text = val
        cnt.save()
        val = filters.escape(val)
        val = filters.urlize(val)
        val = filters.linebreaks(val)
        return HttpResponse(val)
    return HttpResponse("Invalid Request", status=400)


def org_links(req, org_slug, link_type='links'):
    org = get_object_or_404(models.Org, slug=org_slug)
    if not (req.user == org.user or req.user.is_superuser):
        raise PermissionDenied()
    return _process_links(req, org, 'mapstory/orgs/org_links.html', link_type)


def user_links(req, link_type='links'):
    user = req.user
    if not (user.is_authenticated() or user.is_superuser):
        raise PermissionDenied()
    return _process_links(req, user.get_profile(), 'profiles/edit_links.html',
                          link_type)


def resource_links(req, resource, link_type='links'):
    res = get_object_or_404(models.Resource, slug=resource)
    if not req.user.is_superuser:
        raise PermissionDenied()
    return _process_links(req, res, 'mapstory/resource_links.html', link_type)


def _process_links(req, instance, template, link_type):
    error = ''
    m2m = getattr(instance, link_type)
    if req.method == 'POST':
        if req.POST['id']:
            # before updating, make sure the object owns the link
            # will raise if not
            link = m2m.get(id = req.POST['id'])
        else:
            link = models.Link()
        if 'delete' in req.POST:
            link.delete()
        else:
            fields = ('name', 'href')
            if not all([req.POST[f] for f in fields]):
                error = 'Name and URL are required'
            else:
                fields += ('order',)
                for k,v in [ (f, req.POST[f]) for f in fields]:
                    if v: setattr(link, k, v)
                link.save()
                m2m.add(link)
    ctx = {
        'links' : m2m.all().order_by('order'),
        'link_type' : link_type,
        'obj' : instance,
        'error' : error
    }
    return render_to_response(template, RequestContext(req, ctx))


def layer_xml_metadata(req, layer_id):
    obj = _resolve_object(req, Layer, 'maps.view_layer', perm_required=True, id=layer_id)
    return render_to_response('mapstory/full_metadata.xml', {'layer': obj}, mimetype='text/xml')

def _resolve_object(req, model, perm, perm_required=False,
                    allow_owner=False, **kw):
    obj = get_object_or_404(model,**kw)
    allowed = True
    if perm:
        if perm_required or req.method != 'GET':
            if allow_owner:
                allowed = req.user == obj.owner
            if not allowed:
                allowed = req.user.has_perm(perm, obj=obj)
    if not allowed:
        raise PermissionDenied("You do not have adequate permissions")
    return obj
    
def _remove_annotation_layer(sender, instance, **kw):
    try:
        Layer.objects.get(name='_map_%s_annotations' % instance.id)
    except Layer.DoesNotExist:
        pass

signals.pre_delete.connect(_remove_annotation_layer, sender=Map)

def render_email(request):
    t = request.GET['t']
    if t.split('.')[-1].lower() == 'txt':
        mime = "text/plain"
    else:
        mime = "text/html"
    return render_to_response(t, {'user': {'first_name': 'FIRST NAME'}}, mimetype=mime)

def account_verify(request):

    access_token = request.GET.get('access_token', '')

    if not access_token:
        auth = request.META.get('HTTP_AUTHORIZATION', b'')
        if type(auth) == type(''):
            # Work around django test client oddness
            auth = auth.encode('iso-8859-1')
        auth = auth.split()
        if auth and auth[0].lower() == 'bearer':
            access_token = auth[1]

    try:
        token = AccessToken.objects.select_related('user')
        token = token.get(token=access_token, expires__gt=provider_now())
    except AccessToken.DoesNotExist:
        msg = 'No access token'
        return HttpResponseForbidden(msg)

    user = token.user

    if not user.is_active:
        msg = 'User inactive or deleted: %s' % user.username
        return HttpResponseForbidden(msg)
    return HttpResponse('{"id":"%s","first_name":"%s","last_name":"%s","username":"%s","email":"%s"}' 
            % (user.id, user.first_name, user.last_name, user.username, user.email), mimetype='application/json')


def essay(req, title):
    if req.method == 'GET':
        essay = get_object_or_404(models.Essay, slug=title)
    elif req.method == 'POST':
        from django.contrib.markup.templatetags import markup
        if not req.user.is_staff:
            raise PermissionDenied()
        essay = dict([ (k,req.POST.get(k, '')) for k in [ f.name for f in models.Essay._meta.fields]])
        essay['html'] = markup.textile(essay['content'])
    return render_to_response('mapstory/essay.html', RequestContext(req, {
        'essay' : essay
    }))
