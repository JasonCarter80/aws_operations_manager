# Copyright 2016 Amazon.com, Inc. or its affiliates.
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

from troposphere import Output, GetAtt, Sub, Export
from troposphere.iam import Group
from lib import policy
import logging

_LOGGER = logging.getLogger(__name__)


def load_groups(c):
    # Groups
    if "groups" in c.config:
        for group_name in c.config["groups"]:

            context = ["all"]
            if "in_accounts" in c.config["groups"][group_name]:
                context = c.config["groups"][group_name]["in_accounts"]

            for account in c.search_accounts(context):
                c.current_account = account

                # Handle Inline Polices on our Groups
                if "inline_policies" in c.config["groups"][group_name]:
                    for account in c.search_accounts(["children"]):
                        # Don't add Inline Policies on the Master
                        if c.is_parent(account):
                            continue
                        for pol in c.config["groups"][group_name]["inline_policies"]:   # noqa
                            add_group(
                                c,
                                "{}-{}".format(c.map_account(account), pol),
                                c.config["groups"][group_name],
                                c.config["global"]["names"]["groups"],
                                policy.build_inline_assume_role_policy_document(
                                    c,
                                    c.map_account(account),
                                    pol)
                            )
                else:
                    # Handle Regular Groups
                    add_group(
                        c,
                        group_name,
                        c.config["groups"][group_name],
                        c.config["global"]["names"]["groups"]
                    )


def add_group(c, GroupName, model, named=False, PolicyDocument=None):
    cfn_name = c.scrub_name(GroupName + "Group")
    kw_args = {
        "Path": "/",
        "ManagedPolicyArns": []
    }

    if named:
        kw_args["GroupName"] = GroupName

    if "managed_policies" in model:
        kw_args["ManagedPolicyArns"] = policy.parse_managed_policies(
            c,
            model["managed_policies"], GroupName
        )

    if "inline_policies" in model:
        kw_args["Policies"] = policy.add_inline_policy(c,
            GroupName,
            PolicyDocument,
        )

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    c.template[c.current_account].add_resource(Group(
        c.scrub_name(cfn_name),
        **kw_args
    ))
    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="Group " + GroupName + " ARN",
                Value=GetAtt(cfn_name, "Arn"),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])
