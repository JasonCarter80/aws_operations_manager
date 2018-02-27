# Copyright 2018 by Jason Carter
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

from lib.policy import *
import logging

_LOGGER = logging.getLogger(__name__)


def load_buckets(c):
    # Buckets
    if "buckets" in c.config:
        for bucket_name in c.config["buckets"]:
            context = ["parent"]
            if "in_accounts" in c.config["buckets"][bucket_name]:
                context = c.config["buckets"][bucket_name]["in_accounts"]

            for account in c.search_accounts(context):
                c.current_account = account
                add_bucket(
                    c,
                    bucket_name,
                    c.config["buckets"][bucket_name],
                    c.config["global"]["names"]["buckets"]
                )


def add_bucket(c, BucketName, model, named=False):
    cfn_name = c.scrub_name(BucketName + "Bucket")
    kw_args = {}

    if named:
        kw_args["BucketName"] = BucketName

    if "bucket_policy" in model:
        policy = c.config["buckets"][BucketName]['bucket_policy']
        policy_document = ""

        cfn_name_policy = c.scrub_name(BucketName + "BucketPolicy")
        _LOGGER.debug(policy)
        if "policy_file" in policy:
            _LOGGER.debug("Has Policy File")
            policy_document = policy_document_from_jinja(
                c,
                cfn_name_policy,
                c.config["buckets"][BucketName]['bucket_policy']
            )

            _LOGGER.debug(policy_document)
            c.template[c.current_account].add_resource(BucketPolicy(
                cfn_name_policy,
                Bucket=BucketName,
                PolicyDocument=policy_document
            ))

    if "retain_on_delete" in model:
        if model["retain_on_delete"] is True:
            kw_args["DeletionPolicy"] = "Retain"

    c.template[c.current_account].add_resource(Bucket(
        cfn_name,
        **kw_args
    ))

    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="Bucket " + BucketName + " ARN",
                Value=GetAtt(cfn_name, "Arn"),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])
