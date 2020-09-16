import os
import warnings

try:
    from ckan.common import config
except ImportError:
    config = None
    warnings.warn("CKAN is not installed. Please make sure that the "
                  + "environment is active. Some functionalities of "
                  + "dcor_shared are not available!")


if config:
    #: CKAN storage path (contains resources, uploaded group, user or
    #: organization images)
    CKAN_STORAGE = config.get('ckan.storage_path', "").rstrip("/")


def get_resource_path(rid, create_dirs=False):
    resources_path = CKAN_STORAGE + "/resources"
    pdir = "{}/{}/{}".format(resources_path, rid[:3], rid[3:6])
    path = "{}/{}".format(pdir, rid[6:])
    if create_dirs:
        try:
            os.makedirs(pdir)
            os.chown(pdir,
                     os.stat(resources_path).st_uid,
                     os.stat(resources_path).st_gid)
        except OSError:
            pass
    return path
