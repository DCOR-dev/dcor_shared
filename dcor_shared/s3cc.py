"""CKAN S3 convenience module

Contains methods to directly interact with CKAN resources that are on S3
via just the resource ID.
"""
from __future__ import annotations
import io
import functools
import pathlib
from typing import Literal

import dclab
from dclab.rtdc_dataset import fmt_hdf5, fmt_s3
import h5py

from .ckan import (
    get_ckan_config_option, get_resource_dc_config, get_resource_info,
    is_resource_private
)

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
        filename: str = None,
        ret_expiration: bool = False,
        ):
    """Create a presigned URL for a given artifact of a CKAN resource

    Parameters
    ----------
    resource_id : str
        ID of the resource
    artifact:
        Which artifact to create the presigned URL for
    expiration:
        Requested lifetime of the presigned URL (may vary up to 10%)
    filename:
        Filename to use so a download agent can save the file under the
        correct name
    ret_expiration:
        Return the absolute expiration time (seconds since epoch)

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    return s3.create_presigned_url(bucket_name=bucket_name,
                                   object_name=object_name,
                                   expiration=expiration,
                                   filename=filename,
                                   ret_expiration=ret_expiration,
                                   )


def get_s3_attributes_for_artifact(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Return all attribute for an artifact in the S3 object store

    Returns
    -------
    meta: dict
        Metadata dictionary with the keys "etag", "server", "size",
        and "success".
    """
    bucket_name, object_name = get_s3_bucket_object_for_artifact(
        resource_id=resource_id, artifact=artifact)
    s3_client, _, _ = s3.get_s3()
    attr_info = s3_client.head_object(Bucket=bucket_name, Key=object_name)
    # Example output from MinIO::
    #
    #     {'AcceptRanges': 'bytes',
    #      'ContentLength': 904729,
    #      'ContentType': 'application/octet-stream',
    #      'ETag': '"108d47e80f3e5f35110493b1fdcd30d5"',
    #      'LastModified': datetime.datetime(2024, 3, 7, 8, 15,
    #                                        tzinfo=tzutc()),
    #      'Metadata': {},
    #      'ResponseMetadata': {
    #         'HTTPHeaders': {
    #             'accept-ranges': 'bytes',
    #             'content-length': '904729',
    #             'content-type': 'application/octet-stream',
    #             'date': 'Thu, 07 Mar 2024 08:15:02 GMT',
    #             'etag': '"108d47e80f3e5f35110493b1fdcd30d5"',
    #             'last-modified': 'Thu, 07 Mar 2024 '
    #                              '08:15:00 GMT',
    #             'server': 'MinIO',
    #             'strict-transport-security': 'max-age=31536000; '
    #                                          'includeSubDomains',
    #             'vary': 'Origin, Accept-Encoding',
    #             'x-amz-id-2': 'dd9025bab4ad464b049177c95eb6e...',
    #             'x-amz-request-id': '17BA6D680CB67A2C',
    #             'x-amz-tagging-count': '1',
    #             'x-content-type-options': 'nosniff',
    #             'x-xss-protection': '1; mode=block'},
    #         'HTTPStatusCode': 200,
    #         'HostId': 'dd9025bab4ad464b049177c95eb6ebf3...',
    #         'RequestId': '17BA6D680CB67A2C',
    #         'RetryAttempts': 0}
    #      }
    meta = {}
    for key, funcs in [
        ("etag", [lambda m: m.get("ETag"),
                  lambda m: m.get("ResponseMetadata",
                                  {}).get("HTTPHeaders",
                                          {}).get("etag"),
                  ]),
        ("server", [lambda m: m.get("ResponseMetadata",
                                    {}).get("HTTPHeaders",
                                            {}).get("server", "unknown")
                    ]),
        ("size", [lambda m: m.get("ContentLength"),
                  lambda m: m.get("ResponseMetadata",
                                  {}).get("HTTPHeaders",
                                          {}).get("content-length"),
                  ]),
        ("success", [lambda m: m.get("ResponseMetadata",
                                     {}).get("HTTPStatusCode", 404) == 200
                     ]),
    ]:
        for fn in funcs:
            val = fn(attr_info)
            if val is not None:
                meta[key] = val
                break
    return meta


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
    ds_dict, _ = get_resource_info(resource_id)
    bucket_name = get_ckan_config_option(
        "dcor_object_store.bucket_name").format(
        organization_id=ds_dict["organization"]["id"])
    return bucket_name


def get_s3_dc_handle(
        resource_id: str,
        artifact: Literal["condensed", "preview", "resource"] = "resource"):
    """Return an instance of :class:`RTDC_S3`

    The data are accessed directly via S3 using DCOR's access credentials.
    Use this if you need to access the original raw file.

    The resource with the identifier `resource_id` must exist in the
    CKAN database.
    """
    s3_url = get_s3_url_for_artifact(resource_id, artifact=artifact)
    ds = fmt_s3.RTDC_S3(
        url=s3_url,
        access_key_id=get_ckan_config_option(
            "dcor_object_store.access_key_id"),
        secret_access_key=get_ckan_config_option(
            "dcor_object_store.secret_access_key"),
        # Disable basins, because they could point to files on the
        # local file system (security).
        enable_basins=False,
    )
    return ds


def get_s3_dc_handle_basin_based(resource_id):
    """Return a :class:`RTDC_HTTP`-basin-backed instance of :class:`RTDC_HDF5`

    The returned instance does not contain any feature data, but has
    basins defined that link to the original data on S3. The upside
    over :func:`get_s3_dc_handle` is that the returned dataset
    includes the basin with the condensed data and that the returned
    instance does not contain the DCOR S3 credentials. The downside is
    that initialization takes slightly longer and that, if private
    resources are accessed, the presigned URLs in the basins are only
    valid for a fixed time period.

    Parameters
    ----------
    resource_id : str
        CKAN resource identifier

    Returns
    -------
    ds: RTDCBase
        basin-based dclab dataset
    """
    artifacts = ["resource", "condensed"]
    basin_paths = []
    private = is_resource_private(resource_id)
    for artifact in artifacts:
        if private:
            bp = create_presigned_url(resource_id, artifact=artifact)
        else:
            bp = get_s3_url_for_artifact(resource_id, artifact=artifact)
        basin_paths.append(bp)

    fd = io.BytesIO()
    with h5py.File(fd, "w", libver="latest") as hv:
        # We don't use RTDCWriter as a context manager to avoid overhead
        # during __exit__, but then we have to make sure "events" is there.
        hv.require_group("events")
        hw = dclab.RTDCWriter(hv)
        hw.store_metadata(get_resource_dc_config(resource_id))
        for bp, artifact in zip(basin_paths, artifacts):
            hw.store_basin(
                basin_name=f"{artifact}-{resource_id[:5]}",  # "resource-92a12"
                basin_format="http",
                basin_type="remote",
                basin_locs=[bp],
                # Don't verify anything. This would only cost time,
                # and we know these objects exist.
                verify=False,
                perishable=private,
                )
    ds = fmt_hdf5.RTDC_HDF5(fd)
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
        ds_dict, _ = get_resource_info(resource_id)
        private = ds_dict["private"]

    rid = resource_id
    s3_url = s3.upload_file(
        bucket_name=bucket_name,
        object_name=f"{artifact}/{rid[:3]}/{rid[3:6]}/{rid[6:]}",
        path=path_artifact,
        sha256=sha256,
        private=private,
        override=override)
    return s3_url
