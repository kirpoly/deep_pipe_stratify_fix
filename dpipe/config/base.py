import os

from dpipe.externals.resource_manager.resource_manager import ResourceManager, \
    get_resource, generate_config

CONFIG_DIR = os.path.abspath(os.path.dirname(__file__))
CONFIG_PATH = os.path.join(CONFIG_DIR, 'generated_config.json')
MODULES_FOLDER = os.path.abspath(os.path.join(CONFIG_DIR, os.pardir))

EXCLUDED_PATHS = ['externals', 'config']


def get_resource_manager(config) -> ResourceManager:
    generate_config(MODULES_FOLDER, CONFIG_PATH, 'dpipe', EXCLUDED_PATHS)
    return ResourceManager(config, get_resource=get_resource)


if __name__ == '__main__':
    generate_config(MODULES_FOLDER, CONFIG_PATH, 'dpipe', EXCLUDED_PATHS)
