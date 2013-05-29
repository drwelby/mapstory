from django.conf import settings
from django.db import connection
from geonode.maps.models import Map
from mapstory.models import Annotation
import psycopg2
import re

"""
Migrate annotations from a geoserver schema to the django schema.

Make changes to the flags below (who needs options) and run like:

  PYTHONPATH=.. DJANGO_SETTINGS_MODULE=mapstory.settings python scripts/migrate_annotations.py
"""

# if True, drops geoserver annotations tables
drop_tables = False
# if True, drop existing destination records
drop_existing = False

src = psycopg2.connect("dbname='" + settings.DB_DATASTORE_DATABASE + "' user='" + settings.DB_DATASTORE_USER + "'  password='" + settings.DB_DATASTORE_PASSWORD + "' port=" + settings.DB_DATASTORE_PORT + " host='" + settings.DB_DATASTORE_HOST + "'")

src_cursor = src.cursor()
dest_cursor = connection.cursor()

query = lambda sql: src_cursor.execute(sql) or set( t[0] for t in src_cursor.fetchall())

if drop_existing:
    dest_cursor.execute('delete from "mapstory_annotation"')

matcher = re.compile('_map_(\d+)_annotations')
matched = ( matcher.match(t) for t in query('''select "tablename" from pg_tables where "tableowner"='geonode';'''))
matched = [ m for m in matched if m ]

for m in matched:
    try:
        map_obj = Map.objects.get(id=m.group(1))
    except Map.DoesNotExist:
        print 'no map for %s' % m.group(1)
    src_cursor.execute('select * from "%s"' % m.group())
    objs = []
    for r in src_cursor.fetchall():
        a = Annotation()
        a.map = map_obj
        a.title = r[1]
        a.content = r[2]
        a.the_geom = r[3]
        a.start_time = r[4]
        a.end_time = r[5]
        a.in_timeline = r[6] or False
        a.in_map = r[7] or False
        a.appearance = r[8]
        objs.append(a)
    if objs:
        Annotation.objects.bulk_create(objs)
    drop = 'DROP TABLE "%s";' % m.group()
    if drop_tables:
        src_cursor.execute(drop)
    else:
        print 'would execute %s ' % drop

