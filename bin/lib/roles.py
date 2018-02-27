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

from troposphere import Output, GetAtt, Sub, Export, Ref
from troposphere.iam import Role, InstanceProfile
from lib import policy
import logging
import re

_LOGGER = logging.getLogger(__name__)


def load_roles(c):
    # Roles
    if "roles" in c.config:
        for role_name in c.config["roles"]:
            context = ["all"]
            if "in_accounts" in c.config["roles"][role_name]:
                context = c.config["roles"][role_name]["in_accounts"]

            for account in c.search_accounts(context):
                c.current_account = account
                add_role(
                    c,
                    role_name,
                    c.config["roles"][role_name],
                    c.config["global"]["names"]["roles"]
                )

                # See if we need to add an instance profile too with an ec2 trust.       # noqa
                if "ec2.amazonaws.com" in c.config["roles"][role_name]["trusts"]:     # noqa
                    create_instance_profile(
                        c,
                        role_name,
                        c.config["roles"][role_name],
                        c.config["global"]["names"]["roles"]
                    )


def build_role_trust(c, trusts):
    policy = {
        "Version": "2012-10-17",
        "Statement": [],
    }

    sts_principals = []
    saml_principals = []
    for trust in trusts:
        # See if we match an account:
        # First see if we match an account friendly name.
        trust_account = c.search_accounts([trust])
        if trust_account:
            sts_principals.append({
                "AWS": "arn:aws:iam::" +
                       str(c.account_map_ids[trust_account[0]]) +
                       ":root"
            })
        # Next see if we match our SAML trust.
        elif trust == c.saml_provider:
            saml_principals.append({
                "Federated": "arn:aws:iam::" +
                             c.parent_account_id +
                             ":saml-provider/" +
                             c.saml_provider
            })
        # See if we have a 'dot' in our name denoting a service.
        elif re.match("^.*\..*?$", trust):
            sts_principals.append({"Service": trust})
        # otherwise this is likely an account friendly name that isn't correct.
        else:
            error = "Uanble to find trust name '{}' in the config.yaml. "
            + " Assure it exists in the account section.".format(
                trust
            )
            _LOGGER.error(error)
            raise ValueError(error)

    for sts_principal in sts_principals:
        policy["Statement"].append({
            "Effect": "Allow",
            "Principal": sts_principal,
            "Action": "sts:AssumeRole"
        })

    for saml_principal in saml_principals:
        policy["Statement"].append({
            "Effect": "Allow",
            "Principal": saml_principal,
            "Action": "sts:AssumeRoleWithSAML",
            "Condition": {
                "StringEquals": {
                    "SAML:aud": "https://signin.aws.amazon.com/saml"
                }
            }
        })

    return(policy)


def build_sts_statement(account, role):
    statement = {
        "Effect": "Allow",
        "Action": "sts:AssumeRole",
        "Resource": "arn:aws:iam::" + account + ":role/" + role,
    }
    return(statement)


def add_role(c, RoleName, model, named=False, Policy=None):
    cfn_name = c.scrub_name(RoleName + "Role")
    kw_args = {
        "Path": "/",
        "AssumeRolePolicyDocument": build_role_trust(c, model['trusts']),
        "ManagedPolicyArns": [],
        "Policies": []
    }

    if named:
        kw_args["RoleName"] = RoleName

    if "managed_policies" in model:
        kw_args["ManagedPolicyArns"] = policy.parse_managed_policies(
            c, model["managed_policies"], RoleName)

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    c.template[c.current_account].add_resource(Role(
        cfn_name,
        **kw_args
    ))
    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="Role " + RoleName + " ARN",
                Value=GetAtt(cfn_name, "Arn"),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])


def create_instance_profile(c, RoleName, model, named=False):
    cfn_name = c.scrub_name(RoleName + "InstanceProfile")

    kw_args = {
        "Path": "/",
        "Roles": [Ref(c.scrub_name(RoleName + "Role"))]
    }

    if named:
        kw_args["InstanceProfileName"] = RoleName

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    c.template[c.current_account].add_resource(InstanceProfile(
        cfn_name,
        **kw_args
    ))

    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="Instance profile for Role " + RoleName + " ARN",
                Value=Ref(cfn_name),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])
