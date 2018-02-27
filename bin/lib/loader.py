# Original Code from this page copied from the Home Assistant project
# https://github.com/home-assistant/home-assistant/blob/678f284015a2c52f96a7687979cfd9f785e4527a/homeassistant/util/yaml.py
#
# Additions by Jason Carter
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# or in the "license" file accompanying this file.
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

from collections import OrderedDict
from typing import Union, List, Dict
import datetime
import os
import sys
import yaml
import logging

_LOGGER = logging.getLogger(__name__)


class NodeListClass(list):
    """Wrapper class to be able to add attributes on a list."""
    pass


class NodeStrClass(str):
    """Wrapper class to be able to add attributes on a string."""
    pass


# pylint: disable=too-many-ancestors
class SafeLineLoader(yaml.SafeLoader):
    """Loader class that keeps track of line numbers."""

    def compose_node(self, parent: yaml.nodes.Node, index) -> yaml.nodes.Node:
        """Annotate a node with the first line it was seen."""
        last_line = self.line  # type: int
        node = super(SafeLineLoader,
                     self).compose_node(parent, index)  # type: yaml.nodes.Node
        node.__line__ = last_line + 1
        return node


def _add_reference(obj, loader, node):
    """Add file reference information to an object."""
    if isinstance(obj, list):
        obj = NodeListClass(obj)
    if isinstance(obj, str):
        obj = NodeStrClass(obj)
    setattr(obj, '__config_file__', loader.name)
    setattr(obj, '__line__', node.start_mark.line)
    return obj


def load_yaml(fname: str) -> Union[List, Dict]:
    """Load a YAML file."""
    try:
        with open(fname, encoding='utf-8') as conf_file:
            # If configuration file is empty YAML returns None
            # We convert that to an empty dict
            return yaml.load(conf_file, Loader=SafeLineLoader) or OrderedDict()
    except yaml.YAMLError as exc:
        _LOGGER.error(exc)
    except UnicodeDecodeError as exc:
        _LOGGER.error("Unable to read file %s: %s", fname, exc)


def _include_yaml(loader: SafeLineLoader,
                  node: yaml.nodes.Node) -> Union[List, Dict]:
    """Load another YAML file and embeds it using the !include tag.
    Example:
        device_tracker: !include device_tracker.yaml
    """
    fname = os.path.join(os.path.dirname(loader.name), node.value)
    return _add_reference(load_yaml(fname), loader, node)


def _include_dir_merge_named_yaml(loader: SafeLineLoader,
                                  node: yaml.nodes.Node) -> OrderedDict:
    """Load multiple files from directory as a merged dictionary."""
    mapping = OrderedDict()  # type: OrderedDict
    loc = os.path.join(os.path.dirname(loader.name), node.value)
    for fname in _find_files(loc, '*.yaml'):
        if os.path.basename(fname) == SECRET_YAML:
            continue
        loaded_yaml = load_yaml(fname)
        if isinstance(loaded_yaml, dict):
            mapping.update(loaded_yaml)
    return _add_reference(mapping, loader, node)


def _ordered_dict(loader: SafeLineLoader,
                  node: yaml.nodes.MappingNode) -> OrderedDict:
    """Load YAML mappings into an ordered dictionary to preserve key order."""
    loader.flatten_mapping(node)
    nodes = loader.construct_pairs(node)

    seen = {}  # type: Dict
    for (key, _), (child_node, _) in zip(nodes, node.value):
        line = child_node.start_mark.line

        try:
            hash(key)
        except TypeError:
            fname = getattr(loader.stream, 'name', '')
            raise yaml.MarkedYAMLError(
                context="invalid key: \"{}\"".format(key),
                context_mark=yaml.Mark(fname, 0, line, -1, None, None)
            )

        if key in seen:
            fname = getattr(loader.stream, 'name', '')
            _LOGGER.error(
                'YAML file %s contains duplicate key "%s". '
                'Check lines %d and %d.', fname, key, seen[key], line)
        seen[key] = line

    return _add_reference(OrderedDict(nodes), loader, node)


def _construct_seq(loader: SafeLineLoader, node: yaml.nodes.Node):
    """Add line number and file name to Load YAML sequence."""
    obj, = loader.construct_yaml_seq(node)
    return _add_reference(obj, loader, node)


def _env_var_yaml(loader: SafeLineLoader,
                  node: yaml.nodes.Node):
    """Load environment variables and embed it into the configuration YAML."""
    args = node.value.split()

    # Check for a default value
    if len(args) > 1:
        return os.getenv(args[0], ' '.join(args[1:]))
    elif args[0] in os.environ:
        return os.environ[args[0]]
    else:
        _LOGGER.error("Environment variable %s not defined.", node.value)
        raise Error(node.value)


def _load_secret_yaml(secret_path: str) -> Dict:
    """Load the secrets yaml from path."""
    secret_path = os.path.join(secret_path, SECRET_YAML)
    if secret_path in __SECRET_CACHE:
        return __SECRET_CACHE[secret_path]

    _LOGGER.debug('Loading %s', secret_path)
    try:
        secrets = load_yaml(secret_path)
        if 'logger' in secrets:
            logger = str(secrets['logger']).lower()
            if logger == 'debug':
                _LOGGER.setLevel(logging.DEBUG)
            else:
                _LOGGER.error("secrets.yaml: 'logger: debug' expected,"
                              " but 'logger: %s' found", logger)
            del secrets['logger']
    except FileNotFoundError:
        secrets = {}
    __SECRET_CACHE[secret_path] = secrets
    return secrets


# pylint: disable=protected-access
def _secret_yaml(loader: SafeLineLoader,
                 node: yaml.nodes.Node):
    """Load secrets and embed it into the configuration YAML."""
    secret_path = os.path.dirname(loader.name)
    while True:
        secrets = _load_secret_yaml(secret_path)

        if node.value in secrets:
            _LOGGER.debug("Secret %s retrieved from secrets.yaml in "
                          "folder %s", node.value, secret_path)
            return secrets[node.value]

        if secret_path == os.path.dirname(sys.path[0]):
            break  # sys.path[0] set to config/deps folder by bootstrap

        secret_path = os.path.dirname(secret_path)
        if not os.path.exists(secret_path) or len(secret_path) < 5:
            break  # Somehow we got past the .homeassistant config folder

    _LOGGER.error("Secret %s not defined", node.value)
    raise Error(node.value)


yaml.SafeLoader.add_constructor('!include', _include_yaml)
yaml.SafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
                                _ordered_dict)
yaml.SafeLoader.add_constructor('!env_var', _env_var_yaml)
yaml.SafeLoader.add_constructor('!secret', _secret_yaml)
yaml.SafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_SEQUENCE_TAG, _construct_seq)
yaml.SafeLoader.add_constructor('!include_dir_merge_named',
                                _include_dir_merge_named_yaml)

yaml.SafeDumper.add_representer(
    OrderedDict,
    lambda dumper, value:
    represent_odict(dumper, 'tag:yaml.org,2002:map', value))

yaml.SafeDumper.add_representer(
    NodeListClass,
    lambda dumper, value:
    dumper.represent_sequence('tag:yaml.org,2002:seq', value))