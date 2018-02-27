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
from troposphere.iam import User, LoginProfile
from lib.policy import *
import logging
import string
import secrets
import hashlib

_LOGGER = logging.getLogger(__name__)


def load_users(c):
    # Users
    if "users" in c.config:
        for user_name in c.config["users"]:

            context = ["parent"]
            if "in_accounts" in c.config["users"][user_name]:
                context = c.config["users"][user_name]["in_accounts"]

            for account in c.search_accounts(context):
                c.current_account = account
                add_user(
                    c,
                    user_name,
                    c.config["users"][user_name],
                    c.config["global"]["names"]["users"]
                )


def generate_password(length=16):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for i in range(length))


def add_user(c, UserName, model, named=False):
    cfn_name = c.scrub_name(UserName + "User")
    kw_args = {
        "Path": "/",
        "Groups": [],
        "ManagedPolicyArns": [],
        "Policies": [],
    }

    if named:
        kw_args["UserName"] = UserName

    if "groups" in model:
        kw_args["Groups"] = c.parse_imports(model["groups"])

    if "managed_policies" in model:
        kw_args["ManagedPolicyArns"] = parse_managed_policies(
            c,
            model["managed_policies"],
            UserName
        )

    if "password" in model:
        kw_args["LoginProfile"] = LoginProfile(
            Password=model["password"],
            PasswordResetRequired=True
        )

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    fixed_pw = hashlib.md5(UserName.encode('utf-8')).hexdigest()
    _LOGGER.debug("UserName: {}".format(UserName))
    _LOGGER.debug("FixedPW: {}".format(fixed_pw))

    c.template[c.current_account].add_resource(User(
        cfn_name,
        LoginProfile=LoginProfile(
            PasswordResetRequired="true",
            Password=fixed_pw
        ),
        **kw_args
    ))

    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="User " + UserName + " ARN",
                Value=GetAtt(cfn_name, "Arn"),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])
