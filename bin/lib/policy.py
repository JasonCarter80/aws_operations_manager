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
from troposphere.iam import ManagedPolicy, Policy
from jinja2 import Template as jinja_template
from lib import roles
import re
import json
import logging

_LOGGER = logging.getLogger(__name__)


def load_policies(c):
    # Policies
    if "policies" in c.config:
        for policy_name in c.config["policies"]:
            if "inline" in c.config["policies"][policy_name]:
                continue
            context = ["all"]
            if "in_accounts" in c.config["policies"][policy_name]:
                context = c.config["policies"][policy_name]["in_accounts"] # noqa

            # Skip Inline Polices, Handled in Groups
            if "inline" in c.config["policies"][policy_name]:
                continue

            for account in c.search_accounts(context):
                c.current_account = account
                # If our managed policy is jinja based we'll have a policy_file # noqa
                policy_document = ""
                if "policy_file" in c.config["policies"][policy_name]:
                    policy_document = policy_document_from_jinja(
                        c,
                        policy_name,
                        c.config["policies"][policy_name]
                    )
                # If our managed policy is generated as an assume trust
                # we'll have assume
                if "assume" in c.config["policies"][policy_name]:
                    policy_document = build_assume_role_policy_document(
                        c,
                        c.search_accounts(
                            c.config["policies"][policy_name]["assume"]["accounts"]  # noqa
                        ),
                        c.config["policies"][policy_name]["assume"]["roles"]  # noqa
                    )

                add_managed_policy(
                    c,
                    policy_name,
                    policy_document,
                    c.config["policies"][policy_name],
                    c.config["global"]["names"]["policies"]
                )

# Creates a policy document from a jinja template
def policy_document_from_jinja(c, policy_name, model):
    # Try and read the policy file file into a jinja template object
    try:
        policy_file = c.BASEPATH + "/policy/" + model["policy_file"]
        _LOGGER.debug("Opening Policy File from Jinja: {}".format(policy_file))

        template = jinja_template(open(policy_file).read())
    except Exception as e:
        error = "Failed to read template file {}/policy/{}\n\n{}".format(
                c.BASEPATH,
                model["policy_file"],
                e
        )
        _LOGGER.error(error)
        raise ValueError(error)

    # Perform our jinja substitutions on the file contents.
    template_vars = ""
    if "template_vars" in model:
        template_vars = model["template_vars"]

    _LOGGER.debug(c.config)
    try:
        template_jinja = template.render(
            config=c.config,
            account=c.map_account(c.current_account),
            parent_account=c.parent_account_id,
            template_vars=template_vars
        )
    except Exception as e:
        error = "Jinja render failure on file {}/policy/{}\n\n{}".format(
            c.BASEPATH,
            model["policy_file"],
            e
        )
        _LOGGER.error(error)
        raise ValueError(error)

    # Now encode the jinja parsed template as JSON
    try:
        template_json = json.loads(template_jinja)
    except Exception as e:
        error = "JSON encoding failure on file {}/policy/{}\n\n{}".format(
            c.BASEPATH,
            model["policy_file"],
            e
        )
        _LOGGER.error(error)
        raise ValueError(error)

    return(template_json)


def build_inline_assume_role_policy_document(c, account, role):
    policy_statement = {
        "Version": "2012-10-17",
        "Statement": []
    }

    policy_statement["Statement"].append(
        roles.build_sts_statement(account, role)
    )

    return(policy_statement)


def build_assume_role_policy_document(c, accounts, roles):
    policy_statement = {
        "Version": "2012-10-17",
        "Statement": []
    }
    for role in roles:
        for account in accounts:
            policy_statement["Statement"].append(
                build_sts_statement(c.map_account(account), role)
            )

    return(policy_statement)


# Managed policies are unique in that they must be an ARN.
# So either we have an ARN, or a Ref() within our current environment
# or an import: statement from another cloudformation template.
def parse_managed_policies(c, managed_policies, working_on):
    managed_policy_list = []
    for managed_policy in managed_policies:
        # If we have an ARN then we're explicit
        _LOGGER.debug("Managed Policy: {}".format(managed_policy))
        if re.match("arn:aws", managed_policy):
            managed_policy_list.append(managed_policy)
        # If we have an import: then we're importing from another template.
        elif re.match("^import:", managed_policy):
            m = re.match("^import:(.*)", managed_policy)
            managed_policy_list.append(ImportValue(m.group(1)))
        # Alternately we're dealing with a managed policy locally that
        # we need to 'Ref' to get an ARN.
        else:
            # Confirm this is a local policy, otherwise we'll error out.
            if c.is_local_managed_policy(managed_policy):
                # Policy name exists in the template,
                # lets make sure it will exist in this account.
                if c.is_managed_policy_in_account(
                        managed_policy,
                        c.map_account(c.current_account)
                ):
                    # If this is a ref we'll need to assure it's scrubbed
                    managed_policy_list.append(Ref(c.scrub_name(managed_policy)))
                else:
                    error = "Working on: '{}' - Managed Policy: '{}' "
                    + "is not configured to go into account: '{}'".format(
                        working_on,
                        managed_policy,
                        c.current_account
                    )
                    _LOGGER.debug(error)
                    raise ValueError(error)
            else:
                _LOGGER.error(working_on)
                error = "Working on: '{}' - Managed Policy: '{}' " \
                 "does not exist in the configuration file".format(
                    working_on,
                    managed_policy
                )
                _LOGGER.error(error)
                raise ValueError(error)

    return(managed_policy_list)


def add_managed_policy(c, ManagedPolicyName, PolicyDocument,
                       model, named=False):

    cfn_name = c.scrub_name(ManagedPolicyName)
    kw_args = {
        "Description": "Managed Policy " + ManagedPolicyName,
        "PolicyDocument": PolicyDocument,
        "Groups": [],
        "Roles": [],
        "Users": []
    }

    if named:
        kw_args["ManagedPolicyName"] = ManagedPolicyName
    if "description" in model:
        kw_args["Description"] = model["description"]
    if "groups" in model:
        kw_args["Groups"] = parse_imports(c, model["groups"])
    if "users" in model:
        kw_args["Users"] = parse_imports(c, model["users"])
    if "roles" in model:
        kw_args["Roles"] = parse_imports(c, model["roles"])

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    c.template[c.current_account].add_resource(ManagedPolicy(
        cfn_name,
        **kw_args
    ))

    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "PolicyArn",
                Description=kw_args["Description"] + " Policy Document ARN",
                Value=Ref(cfn_name),
                Export=Export(Sub(
                    "${AWS::StackName}-" + cfn_name + "PolicyArn"
                ))
            )
        ])


def add_inline_policy(c, InlinePolicyName, PolicyDocument):

    cfn_name = c.scrub_name(InlinePolicyName)
    kw_args = {
        "PolicyName": InlinePolicyName,
        "PolicyDocument": PolicyDocument
    }

    return [Policy(
        cfn_name,
        **kw_args
    )]
