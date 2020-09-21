import os
import pathlib
import warnings

try:
    from ckan.common import config
except ImportError:
    config = None


if config:
    #: CKAN storage path (contains resources, uploaded group, user or
    #: organization images)
    CKAN_STORAGE = config.get('ckan.storage_path', "").rstrip("/")
else:
    # Attempt to load the configuration from the actual ckan.ini
    CKAN_STORAGE = None
    ckanini = pathlib.Path("/etc/ckan/default/ckan.ini")
    if ckanini.exists():
        # parse the ini file
        with open(ckanini) as fd:
            for line in fd.readlines():
                line = line.strip()
                if line.startswith("#") or line.startswith("["):
                    continue
                elif line.count("="):
                    key, value = line.split("=", 1)
                    if key == "ckan.storage_path":
                        CKAN_STORAGE = value.strip()
                        break
    if CKAN_STORAGE is None:
        warnings.warn("CKAN is not installed. Please make sure that the "
                      + "environment is active or the ckan.ini file is in "
                      + "its usual place. Some functionalities of "
                      + "dcor_shared are not available!")


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
    return pathlib.Path(path)
