import pathlib

from .ckan import get_ckan_storage_path, get_ckan_webassets_path  # noqa: F401
from .ckan import get_ckan_config_path  # noqa: F401


def get_nginx_config_path():
    return pathlib.Path("/etc/nginx/sites-enabled/ckan")


def get_supervisord_worker_config_path():
    return pathlib.Path("/etc/supervisor/conf.d/ckan-worker.conf")


def get_uwsgi_config_path():
    return pathlib.Path("/etc/ckan/default/ckan-uwsgi.ini")
