import pytest

from dcor_shared.parse import (
    ConfigOptionNotFoundError, get_ini_config_option, parse_ini_config
)


def test_parse_ini_config(tmp_path):
    path = tmp_path / "test.ini"
    path.write_text("[app:main]\n"
                    "# comment = ignored\n"
                    "ckan.site_id = default\n"
                    "sqlalchemy.url=postgresql://user:pass@host/db?a=b\n"
                    "no equals sign here\n")
    opts = parse_ini_config(path)
    assert opts == {
        "ckan.site_id": "default",
        "sqlalchemy.url": "postgresql://user:pass@host/db?a=b",
    }


def test_get_ini_config_option(tmp_path):
    path = tmp_path / "test.ini"
    path.write_text("[app:main]\nckan.storage_path = /data\n")
    assert get_ini_config_option("ckan.storage_path", path) == "/data"
    with pytest.raises(ConfigOptionNotFoundError, match="ckan.site_id"):
        get_ini_config_option("ckan.site_id", path)
