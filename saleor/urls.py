from ajax_select import urls as ajax_select_urls
from django.conf import settings
from django.conf.urls import url, include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps import views
from django.contrib.staticfiles.views import serve
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView

from saleor.graphql.views import AuthGraphQLView
from .core.sitemaps import sitemaps
from .search.urls import urlpatterns as search_urls


def graphql_token_view():
    view = csrf_exempt(AuthGraphQLView.as_view(graphiql=settings.DEBUG))
    return view

urlpatterns = [
    url(r'^graphql', graphql_token_view()),
    url(r'^graphiql', include('django_graphiql.urls')),
    url(r'^search/', include(search_urls, namespace='search')),
    url(r'^sitemap\.xml$', views.index, {'sitemaps': sitemaps}),
    url(r'^sitemap-(?P<section>.+)\.xml$', views.sitemap, {'sitemaps': sitemaps},
        name='django.contrib.sitemaps.views.sitemap'),

    url(r'^robots\.txt$', include('robots.urls')),

    url(r'^oye/', include('saleor_oye.urls', namespace='oye')),
    url(r'^admin/', include(admin.site.urls)),
    # place it at whatever base url you like
    url(r'^ajax_select/', include(ajax_select_urls)),
]

if settings.DEBUG:
    # static files (images, css, javascript, etc.)
    urlpatterns += [
        url(r'^static/(?P<path>.*)$', serve)
    ] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
