import logging
import babel.core

from pylons import config
from paste.deploy.converters import asbool

from adhocracy.lib import cache, staticpage
from adhocracy.lib.helpers import url as _url
from adhocracy.lib.helpers.adhocracy_service import RESTAPI

log = logging.getLogger(__name__)


@cache.memoize('staticpage_url')
def url(staticpage, **kwargs):
    pid = staticpage.key + '_' + staticpage.lang
    return _url.build(None, 'static', pid, **kwargs)


def get_lang_info(lang):
    locale = babel.core.Locale(lang)
    return {'id': lang, 'name': locale.display_name}


def can_edit():
    return staticpage.can_edit()


def get_body(key, default=''):
    res = staticpage.get_static_page(key)
    if res is None:
        return default
    return res.body


def use_kotti_navigation():
    return asbool(config.get('adhocracy.use_kotti_navigation', 'false'))


def render_kotti_navigation():
    api = RESTAPI()
    result = api.staticpages_get()
    nav = result.json()
    if nav is None:
        log.error('Kotti based navigation not found for configured languages')
        return ''

    def render_navigation_item(item, path=''):

        if path != '':
            path = '%s/%s' % (path, item['name'])
        else:
            path = item['name']

        self_html = u'<a href="%s">%s</a>' % (path, item['title'])

        if item['children']:
            children_html = u'<ul class="children">%s</ul>' % (
                ''.join(map(lambda child: render_navigation_item(child, path),
                            item['children'])))
        else:
            children_html = ''

        return '<li>%s%s</li>' % (self_html, children_html)

    return ''.join(map(render_navigation_item, nav['children']))
