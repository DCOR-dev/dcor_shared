"""CKAN S3 convenience module

Contains methods to directly interact with CKAN resources that are on S3
via just the resource ID.
"""
import functools

from typing import Literal

from dclab.rtdc_dataset import fmt_s3

from .ckan import get_ckan_config_option
from . import s3


def compute_checksum(resource_id):
    """Compute the SHA256 checksum of the corresponding CKAN resource"""
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact="resource")
    s3h = s3.compute_checksum(bucket_name=bucket_name, object_name=object_name)
    return s3h


def create_presigned_url(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource",
        expiration: int = 3600,
        filename: str = None):
    """Create a presigned URL for a given artifact of a CKAN resource

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    return s3.create_presigned_url(bucket_name=bucket_name,
                                   object_name=object_name,
                                   expiration=expiration,
                                   filename=filename)


def get_s3_bucket_object_for_artifact(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Return `bucket_name` and `object_name` for an artifact of a resource

    The value of artifact can be either "condensed", "preview", or "resource"
    (those are the keys under which the individual objects are stored in S3).

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    bucket_name = get_s3_bucket_name_for_resource(resource_id=resource_id)
    rid = resource_id
    return bucket_name, f"{artifact}/{rid[:3]}/{rid[3:6]}/{rid[6:]}"


@functools.lru_cache(maxsize=100)
def get_s3_bucket_name_for_resource(resource_id):
    """Return the bucket name to which a given resource belongs

    The bucket name is determined by the ID of the organization
    which the dataset containing the resource belongs to.

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    import ckan.logic
    res_dict = ckan.logic.get_action('resource_show')(
        context={'ignore_auth': True, 'user': 'default'},
        data_dict={"id": resource_id})
    ds_dict = ckan.logic.get_action('package_show')(
        context={'ignore_auth': True, 'user': 'default'},
        data_dict={'id': res_dict["package_id"]})
    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    return bucket_name


def get_s3_dc_handle(resource_id):
    """Return an instance of :class:`RTDC_S3`

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    s3_url = get_s3_url_for_artifact(resource_id)
    ds = fmt_s3.RTDC_S3(
        url=s3_url,
        secret_id=get_ckan_config_option(
            "dcor_object_store.access_key_id"),
        secret_key=get_ckan_config_option(
            "dcor_object_store.secret_access_key"),
    )
    return ds


def get_s3_url_for_artifact(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Return the S3 URL for a given artifact

    The value of artifact can be either "condensed", "preview", or "resource"
    (those are the keys under which the individual objects are stored in S3).

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    s3_endpoint = get_ckan_config_option("dcor_object_store.endpoint_url")
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    return f"{s3_endpoint}/{bucket_name}/{object_name}"


def make_resource_public(resource_id: str,
                         missing_ok: bool = True):
    """Make a resource, including all its artifacts, public

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    for artifact in ["condensed", "preview", "resource"]:
        bucket_name, object_name = get_s3_bucket_object_for_artifact(
            resource_id=resource_id, artifact=artifact)
        s3.make_object_public(bucket_name=bucket_name,
                              object_name=object_name,
                              missing_ok=missing_ok)


def object_exists(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Check whether an object is available on S3

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    return s3.object_exists(bucket_name=bucket_name, object_name=object_name)
