import os
import pathlib

from .parse import get_ini_config_option


def get_ckan_config_option(option):
    """Return the CKAN configuration option

    If `ckan.common.config` is imported, then the configuration is
    taken from there. Else, the configuration is taken from the
    configuration file returned by :func:`get_ckan_config_path`.
    """
    from ckan import common as ckan_common
    if ckan_common.config:
        # Get from current configuration (The `get` method in CKAN 2.10
        # returns default values if not placeholder is specified)
        opt = ckan_common.config.get(option)
    else:
        opt = get_ini_config_option(option,
                                    get_ckan_config_path())
    return opt


def get_ckan_config_path():
    """Return path to ckan.ini (prefer from environment)"""
    default = "/etc/ckan/default/ckan.ini"
    return pathlib.Path(os.environ.get("CKAN_INI", default))


def get_ckan_storage_path():
    """Return ckan.storage_path

    contains resources, uploaded group, user or organization images
    """
    return pathlib.Path(get_ckan_config_option("ckan.storage_path"))


def get_ckan_webassets_path():
    """Return path to CKAN webassets"""
    return pathlib.Path(get_ckan_config_option("ckan.webassets.path"))


def get_resource_path(rid, create_dirs=False):
    resources_path = get_ckan_storage_path() / "resources"
    pdir = resources_path / rid[:3] / rid[3:6]
    path = pdir / rid[6:]
    if create_dirs:
        try:
            pdir.mkdir(parents=True, exist_ok=True)
            os.makedirs(pdir)
            os.chown(pdir,
                     os.stat(resources_path).st_uid,
                     os.stat(resources_path).st_gid)
        except OSError:
            pass
    return pathlib.Path(path)
