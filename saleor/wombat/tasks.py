import os
try:
    import urlparse
except ImportError:
    # Python 3
    from urllib import parse as urlparse

import requests
import tempfile
from django.core.files.storage import default_storage
from django.core.files import File
from rest_framework.renderers import JSONRenderer
from . import WombatClient, logger
from . import serializers

wombat = WombatClient()


def push_data(queryset, serializer_class, wombat_name):
    serialized = serializer_class(queryset, many=True)
    json_data = JSONRenderer().render(serialized.data)
    wombat_response = wombat.push({wombat_name: json_data})
    try:
        wombat_response.raise_for_status()
    except requests.HTTPError:
        logger.exception('Data push failed')
    else:
        logger.info('Data successfully pushed to Wombat')


def push_products(queryset):
    return push_data(queryset, serializers.ProductSerializer, 'products')


def push_orders(queryset):
    return push_data(queryset, serializers.OrderSerializer, 'orders')


def download_image(image_url):
    temp = tempfile.mktemp()
    content = requests.get(image_url, stream=True)
    with open(temp, 'wb') as f:
        for chunk in content.iter_content():
            if chunk:
                f.write(chunk)
    file_name = ''.join(os.path.splitext(
        os.path.basename(urlparse.urlsplit(image_url).path)))
    new_path = default_storage.save(file_name, File(open(temp)))

    return new_path
