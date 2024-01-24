import pathlib

from .ckan import get_ckan_config_path, get_ckan_config_option
from .ckan import get_ckan_storage_path, get_ckan_webassets_path  # noqa: F401

from .parse import get_ini_config_option


def get_dcor_depot_path():
    return pathlib.Path(get_ckan_config_option(
        "ckanext.dcor_depot.depots_path"))


def get_dcor_users_depot_path():
    depot = get_dcor_depot_path()
    return depot / get_ini_config_option(
        "ckanext.dcor_depot.users_depot_name",
        get_ckan_config_path())


def get_nginx_config_path():
    return pathlib.Path("/etc/nginx/sites-enabled/ckan")


def get_supervisord_worker_config_path():
    return pathlib.Path("/etc/supervisor/conf.d/ckan-worker.conf")


def get_uwsgi_config_path():
    return pathlib.Path("/etc/ckan/default/ckan-uwsgi.ini")
