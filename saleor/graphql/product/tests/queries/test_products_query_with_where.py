from datetime import timedelta

import graphene
import pytest
from django.utils import timezone

from saleor.product.models import Product, ProductChannelListing

from ....tests.utils import get_graphql_content

PRODUCTS_WHERE_QUERY = """
    query($where: ProductWhereInput!, $channel: String) {
      products(first: 10, where: $where, channel: $channel) {
        edges {
          node {
            id
            name
            slug
          }
        }
      }
    }
"""


def test_product_filter_by_ids(api_client, product_list, channel_USD):
    # given
    ids = [
        graphene.Node.to_global_id("Product", product.pk)
        for product in product_list[:2]
    ]
    variables = {"channel": channel_USD.slug, "where": {"id": ids}}

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    returned_slugs = {node["node"]["slug"] for node in products}
    assert returned_slugs == {
        product_list[0].slug,
        product_list[1].slug,
    }


@pytest.mark.parametrize(
    "where, indexes",
    [
        ({"eq": "Test product 1"}, [0]),
        ({"eq": "Non-existing"}, []),
        ({"oneOf": ["Test product 1", "Test product 2"]}, [0, 1]),
        ({"oneOf": ["Test product 1", "Non-existing"]}, [0]),
        ({"oneOf": ["Non-existing 1", "Non-existing 2"]}, []),
    ],
)
def test_product_filter_by_name(where, indexes, api_client, product_list, channel_USD):
    # given
    variables = {"channel": channel_USD.slug, "where": {"name": where}}

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    nodes = data["data"]["products"]["edges"]
    assert len(nodes) == len(indexes)
    returned_slugs = {node["node"]["slug"] for node in nodes}
    assert returned_slugs == {product_list[index].slug for index in indexes}


@pytest.mark.parametrize(
    "where, indexes",
    [
        ({"eq": "test-product-a"}, [0]),
        ({"eq": "non-existing"}, []),
        ({"oneOf": ["test-product-a", "test-product-b"]}, [0, 1]),
        ({"oneOf": ["test-product-a", "non-existing"]}, [0]),
        ({"oneOf": ["non-existing-1", "non-existing-2"]}, []),
    ],
)
def test_product_filter_by_slug(where, indexes, api_client, product_list, channel_USD):
    # given
    variables = {"channel": channel_USD.slug, "where": {"slug": where}}

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    nodes = data["data"]["products"]["edges"]
    assert len(nodes) == len(indexes)
    returned_slugs = {node["node"]["slug"] for node in nodes}
    assert returned_slugs == {product_list[index].slug for index in indexes}


def test_product_filter_by_product_types(
    api_client, product_list, channel_USD, product_type_list
):
    # given
    product_list[0].product_type = product_type_list[0]
    product_list[1].product_type = product_type_list[1]
    product_list[2].product_type = product_type_list[2]
    Product.objects.bulk_update(product_list, ["product_type"])

    type_ids = [
        graphene.Node.to_global_id("ProductType", type.pk)
        for type in product_type_list[:2]
    ]
    variables = {
        "channel": channel_USD.slug,
        "where": {"productType": {"oneOf": type_ids}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    returned_slugs = {node["node"]["slug"] for node in products}
    assert returned_slugs == {
        product_list[0].slug,
        product_list[1].slug,
    }


def test_product_filter_by_product_type(
    api_client, product_list, channel_USD, product_type_list
):
    # given
    product_list[0].product_type = product_type_list[0]
    Product.objects.bulk_update(product_list, ["product_type"])

    type_id = graphene.Node.to_global_id("ProductType", product_type_list[0].pk)

    variables = {
        "channel": channel_USD.slug,
        "where": {"productType": {"eq": type_id}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 1
    assert product_list[0].slug == products[0]["node"]["slug"]


def test_product_filter_by_categories(
    api_client, product_list, channel_USD, category_list
):
    # given
    product_list[0].category = category_list[0]
    product_list[1].category = category_list[1]
    product_list[2].category = category_list[2]
    Product.objects.bulk_update(product_list, ["category"])

    category_ids = [
        graphene.Node.to_global_id("Category", category.pk)
        for category in category_list[:2]
    ]
    variables = {
        "channel": channel_USD.slug,
        "where": {"category": {"oneOf": category_ids}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    returned_slugs = {node["node"]["slug"] for node in products}
    assert returned_slugs == {
        product_list[0].slug,
        product_list[1].slug,
    }


def test_product_filter_by_category(
    api_client, product_list, channel_USD, category_list
):
    # given
    product_list[1].category = category_list[1]
    Product.objects.bulk_update(product_list, ["category"])

    category_id = graphene.Node.to_global_id("Category", category_list[1].pk)

    variables = {
        "channel": channel_USD.slug,
        "where": {"category": {"eq": category_id}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 1
    assert product_list[1].slug == products[0]["node"]["slug"]


def test_product_filter_by_collections(
    api_client, product_list, channel_USD, collection_list
):
    # given
    product_list[0].collection = collection_list[0]
    product_list[1].collection = collection_list[1]
    product_list[2].collection = collection_list[2]
    Product.objects.bulk_update(product_list, ["Collection"])

    collection_ids = [
        graphene.Node.to_global_id("Collection", collection.pk)
        for collection in collection_list[:2]
    ]
    variables = {
        "channel": channel_USD.slug,
        "where": {"collection": {"oneOf": collection_ids}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    returned_slugs = {node["node"]["slug"] for node in products}
    assert returned_slugs == {
        product_list[0].slug,
        product_list[1].slug,
    }


def test_product_filter_by_collection(
    api_client, product_list, channel_USD, collection_list
):
    # given
    product_list[1].collection = collection_list[1]
    Product.objects.bulk_update(product_list, ["collection"])

    collection_id = graphene.Node.to_global_id("Collection", collection_list[1].pk)

    variables = {
        "channel": channel_USD.slug,
        "where": {"collection": {"eq": collection_id}},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 1
    assert product_list[1].slug == products[0]["node"]["slug"]


def test_product_filter_by_is_available(api_client, product_list, channel_USD):
    # given
    ProductChannelListing.objects.filter(
        product=product_list[1], channel=channel_USD
    ).update(available_for_purchase_at=timezone.now() + timedelta(days=1))
    variables = {
        "channel": channel_USD.slug,
        "where": {"isAvailable": True},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    assert product_list[0].slug == products[0]["node"]["slug"]
    assert product_list[2].slug == products[1]["node"]["slug"]


def test_product_filter_by_is_published(api_client, product_list, channel_USD):
    # given
    ProductChannelListing.objects.filter(
        product=product_list[1], channel=channel_USD
    ).update(is_published=False)
    variables = {
        "channel": channel_USD.slug,
        "where": {"isPublished": True},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    assert product_list[0].slug == products[0]["node"]["slug"]
    assert product_list[2].slug == products[1]["node"]["slug"]


def test_product_filter_by_is_visible_in_listing(api_client, product_list, channel_USD):
    # given
    ProductChannelListing.objects.filter(
        product=product_list[1], channel=channel_USD
    ).update(visible_in_listings=False)
    variables = {
        "channel": channel_USD.slug,
        "where": {"isVisibleInListing": True},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    assert product_list[0].slug == products[0]["node"]["slug"]
    assert product_list[2].slug == products[1]["node"]["slug"]


def test_product_filter_by_published_from(api_client, product_list, channel_USD):
    # given
    timestamp = timezone.now()
    ProductChannelListing.objects.filter(
        product__in=product_list, channel=channel_USD
    ).update(published_at=timestamp + timedelta(days=1))
    ProductChannelListing.objects.filter(
        product=product_list[0], channel=channel_USD
    ).update(published_at=timestamp - timedelta(days=1))
    variables = {
        "channel": channel_USD.slug,
        "where": {"publishedFrom": timestamp},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 1
    assert product_list[0].slug == products[0]["node"]["slug"]


def test_product_filter_by_available_from(api_client, product_list, channel_USD):
    # given
    timestamp = timezone.now()
    ProductChannelListing.objects.filter(
        product__in=product_list, channel=channel_USD
    ).update(available_for_purchase_at=timestamp - timedelta(days=1))
    ProductChannelListing.objects.filter(
        product=product_list[0], channel=channel_USD
    ).update(available_for_purchase_at=timestamp + timedelta(days=1))
    variables = {
        "channel": channel_USD.slug,
        "where": {"availableFrom": timestamp},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    assert product_list[1].slug == products[0]["node"]["slug"]
    assert product_list[2].slug == products[1]["node"]["slug"]


def test_product_filter_by_has_category(api_client, product_list, channel_USD):
    # given
    product_list[1].category = None
    product_list[1].save(update_fields=["category"])
    variables = {
        "channel": channel_USD.slug,
        "where": {"hasCategory": True},
    }

    # when
    response = api_client.post_graphql(PRODUCTS_WHERE_QUERY, variables)

    # then
    data = get_graphql_content(response)
    products = data["data"]["products"]["edges"]
    assert len(products) == 2
    assert product_list[0].slug == products[0]["node"]["slug"]
    assert product_list[2].slug == products[1]["node"]["slug"]
