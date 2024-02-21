"""CKAN S3 convenience module

Contains methods to directly interact with CKAN resources that are on S3
via just the resource ID.
"""
from __future__ import annotations
import functools
import pathlib
from typing import Literal
import warnings

from dclab.rtdc_dataset import fmt_s3

from .ckan import get_ckan_config_option
from .data import sha256sum
from . import s3


def artifact_exists(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Check whether an artifact is available on S3

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    return s3.object_exists(bucket_name=bucket_name, object_name=object_name)


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
        # Disable basins, because they could point to files on the
        # local file system (security).
        enable_basins=False,
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
    """Check whether an artifact is available on S3

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    warnings.warn("`s3cc.object_exists` is deprecated, please use"
                  "`s3cc.artifact_exists` instead",
                  DeprecationWarning)
    return artifact_exists(resource_id, artifact)


def upload_artifact(
        resource_id: str,
        path_artifact: str | pathlib.Path,
        artifact: Literal["condensed", "preview", "resource"] = "resource",
        sha256: str = None,
        private: bool = None,
        override: bool = False
):
    """Upload an artifact to S3

    Parameters
    ----------
    resource_id: str
        The resource identifier for the artifact
    path_artifact: pathlib.Path
        The path to the artifact file
    artifact: str
        The artifact type that the file represents
    sha256: str
        The SHA256 sum of `path_artifcat`, will be computed if not provided
    private: bool
        Whether the dataset that the resource belongs to is private.
        Leave this blank if you don't know and we will do a database
        look-up to determine the correct value.
    override: bool
        Whether to override a possibly existing object on S3.
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)

    if private is None:
        # User did not say whether the resource is private. We have to
        # find out ourselves.
        import ckan.logic
        res_dict = ckan.logic.get_action('resource_show')(
            context={'ignore_auth': True, 'user': 'default'},
            data_dict={"id": resource_id})
        ds_dict = ckan.logic.get_action('package_show')(
            context={'ignore_auth': True, 'user': 'default'},
            data_dict={'id': res_dict["package_id"]})
        private = ds_dict["private"]

    rid = resource_id
    s3.upload_file(
        bucket_name=bucket_name,
        object_name=f"{artifact}/{rid[:3]}/{rid[3:6]}/{rid[6:]}",
        path=path_artifact,
        sha256=sha256 or sha256sum(path_artifact),
        private=private,
        override=override)