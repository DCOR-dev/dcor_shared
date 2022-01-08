class ConfigOptionNotFoundError(BaseException):
    pass


def get_ini_config_option(option, path):
    opt_dict = parse_ini_config(path)
    if option in opt_dict:
        value = opt_dict[option]
    else:
        raise ConfigOptionNotFoundError("Could not find '{}'!".format(option))
    return value


def parse_ini_config(ini):
    opt_dict = {}
    with open(ini) as fd:
        for line in fd.readlines():
            line = line.strip()
            if line.startswith("#") or line.startswith("["):
                continue
            elif line.count("="):
                key, value = line.split("=", 1)
                opt_dict[key.strip()] = value.strip()
    return opt_dict
