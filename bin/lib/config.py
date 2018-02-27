# Copyright 2016 Amazon.com, Inc. or its affiliates.
# Additions by Jason Carter
# All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License").
# You may not use this file except in compliance with the License.
# A copy of the License is located at
#
#    http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file.
# This file is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
# CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

from troposphere import Template, Output, Export, Sub, ImportValue
from pprint import pformat
import lib.loader
import lib.const as CONST
import lib.policy as policy
import lib.cloudtrail as cloudtrail
import lib.s3 as buckets
import lib.groups as groups
import lib.users as users
import lib.roles as roles
import re
import datetime
import os
import sys
import json
import logging


_LOGGER = logging.getLogger(__name__)

class Config(object):
    """
        Helper method to load and hold config information
        for the project
    """


    def __setup_logging(self, level):
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.CRITICAL)
        console_handler.setFormatter(
            logging.Formatter('[%(levelname)s](%(name)s): %(message)s'))
        _LOGGER.addHandler(console_handler)
        logging.basicConfig(level=level)

    # Read our config file and build a few helper constructs from it.
    def __init__(self, config_file, level = logging.CRITICAL):
        self.__setup_logging(level)

        # Read our YAML
        current_path = os.path.dirname(os.path.realpath(sys.argv[0]))
        if (current_path.endswith(CONST.BIN_DIR)):
            self.BASEPATH = current_path.replace(CONST.BIN_DIR, "")
        else:
            self.BASEPATH = current_path

        accounts = False
        if config_file:
            filename = os.path.abspath(config_file)
            if os.path.exists(filename):
                self.config = json.loads(json.dumps(lib.loader.load_yaml(filename)))    # noqa
                self.config_name = os.path.splitext(
                    os.path.basename(filename))[0]
                if 'accounts' in self.config:
                    accounts = True

        if not accounts:
            error = "No configuration file with Account Data was Provided\n"
            + "One account should be present"
            _LOGGER.error(error)
            raise Exception(error)

        _LOGGER.debug("Parsed Config file")
        _LOGGER.debug(pformat(self.config))

        # We will use our current timestamp in UTC as our build version
        self.build_version = \
            datetime.datetime.utcnow().strftime("%Y-%m-%dZ%H:%M:%S")
        # To hold our Troposphere template objects
        self.template = {}
        # A list of our accounts by names and IDs.
        self.account_ids = []
        self.account_names = []
        # A hash of IDs to names to help in forward and reverse resolution.
        self.account_map_ids = {}
        self.account_map_names = {}
        # Our parent account.
        self.parent = ""
        # SAML Provider
        self.saml_provider = ""
        for account in self.config['accounts']:
            account_id = str(self.config['accounts'][account]['id'])
            # Append to our array of account IDS:
            _LOGGER.debug("Added Account {} ({}) ".format(account, account_id))
            self.account_ids.append(account_id)
            self.account_names.append(account)
            self.account_map_names[account_id] = account
            self.account_map_ids[account] = account_id
            self.template[account] = Template()
            self.template[account].add_version("2010-09-09")
            self.template[account].add_description(
                "Build " +
                self.build_version +
                " - IAM Users, Groups, Roles, and Policies for account " +
                account +
                " (" + self.account_map_ids[account] + ")"
            )
            self.template[account].add_output([
                Output(
                    "TemplateBuild",
                    Description="CloudFormation Template Build Number",
                    Value=self.build_version,
                    Export=Export(Sub("${AWS::StackName}-" + "TemplateBuild"))
                )
            ])
            if "parent" in self.config['accounts'][account]:
                if self.config['accounts'][account]['parent'] is True:
                    _LOGGER.debug("Is Parent: True")
                    self.parent_account = account
                    self.parent_account_id = account_id
                    if "saml_provider" in self.config['accounts'][account]:
                        self.saml_provider = \
                            self.config['accounts'][account]["saml_provider"]

        self.__check_global()
        _LOGGER.debug(pformat(self.config))

        if self.parent_account == "":
            error = ("No account is marked as parent in the configuration"
                     " file.  One account should have parent: true")
            _LOGGER.error(error)
            raise Exception(error)

    def __check_global(self):
        if 'global' not in self.config:
            self.config['global'] = {
                "names": {
                    "policies": False,
                    "roles": True,
                    "users": True,
                    "groups": True
                },
                "template_outputs": "enabled"
            }

    # CloudFormation names must be alphanumeric.
    # Our config might include non-alpha, so we'll scrub them here.
    def scrub_name(self, name):
        return(re.sub('[\W_]+', '', name))

    # Converts between friendly names and ids for accounts.
    def is_parent(self, account):
        return account == self.parent_account

    # Converts between friendly names and ids for accounts.
    def map_account(self, account):
        # If our account is numeric
        if re.match("^\d+$", account):
            return(self.account_map_names[account])
        else:
            return(self.account_map_ids[account])

    # Return an array of account names that our pattern matches
    def search_accounts(self, pattern_list=[]):

        _LOGGER.debug("Pattern_List: {}".format(pattern_list))
        # Make sure our pattern is actually a list.
        if not isinstance(pattern_list, list):
            raise Exception("search_accounts pattern list must be a list")

        matched = []
        # We permit a few special keywords to make our users lives easier.
        for pattern in pattern_list:
            found = False
            # If our pattern is a service name (denoted by a dot) we will
            # not raise an exception about an invalid account
            # but we won't populate our matched list.
            if '.' in pattern:
                found = True
            # If our pattern is a SAML provider we will not raise an exception
            # but won't populate a match.
            if pattern == self.saml_provider:
                found = True
            if pattern == "parent":
                matched.append(self.parent_account)
                found = True
            elif pattern == "children":
                matched = list(self.config['accounts'])
                matched.remove(self.parent_account)
                found = True
            elif pattern == "all":
                matched = list(self.config['accounts'])
                found = True
            else:
                # Iterate over all of our accounts by name and by ID .
                for account_id, account_name in \
                            zip(self.account_ids, self.account_names):
                    if re.match(pattern, account_id):
                        matched.append(
                            self.map_account(account_id)
                        )
                        found = True
                    if re.match(pattern, account_name):
                        matched.append(account_name)
                        found = True

            if found is False:
                raise ValueError(
                    "Unable to find account named '{}' in the accounts: "
                    " section of the config.yaml".format(pattern)
                )

        # uniqify our matches
        matched = list(set(matched))

        return(matched)

    def is_local_managed_policy(self, managed_policy):
        if managed_policy in self.config["policies"]:
            return True
        else:
            return False

    def is_managed_policy_in_account(self, managed_policy, account):
        if managed_policy in self.config["policies"]:
            if "in_accounts" in self.config["policies"][managed_policy]:
                policy_account_context = self.search_accounts(
                    self.config["policies"][managed_policy]["in_accounts"]
                )
                entity_account_context = self.search_accounts([account])
                if entity_account_context[0] in policy_account_context:
                    return True
                else:
                    return False
            # If there is no in_accounts section in our managed policy
            # it goes in all accounts.
            else:
                return True

    # Users, Groups and roles are simply by name versus an ARN.
    # We take them at face value as there's no way to verify their syntax
    # We will however check for import: values and substitute accordingly.
    def parse_imports(self, element_list):
        return_list = []
        for element in element_list:
            # See if we match an import
            if re.match("^import:", element):
                m = re.match("^import:(.*)", element)
                return_list.append(ImportValue(m.group(1)))
            # Otherwise we're verbatim as there's no real way to know if this
            # is within the template or existing.
            else:
                return_list.append(element)

        return(return_list)

    def load(self, output_format):
        policy.load_policies(self)
        roles.load_roles(self)
        groups.load_groups(self)
        users.load_users(self)
        buckets.load_buckets(self)
        cloudtrail.load_trails(self)
        _LOGGER.debug(pformat(self.config))
        self.write_files(output_format)

    def write_files(self, output_format=CONST.TO_JSON):
        # Write the files

        for account in self.search_accounts(["all"]):
            if len(json.loads(self.template[account].to_json())['Resources'])>0:     # noqa
                fh = open(
                    "{}/output_templates/{}_{}_{}.template".format(
                        self.BASEPATH,
                        account,
                        self.account_map_ids[account],
                        self.config_name
                    ), 'w'
                )
                if (output_format == CONST.TO_YAML):
                    fh.write(self.template[account].to_yaml())
                else:
                    fh.write(self.template[account].to_json())
                fh.close()


