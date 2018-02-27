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

from troposphere import Output, GetAtt, Sub, Export
from troposphere.cloudtrail import Trail
import logging

_LOGGER = logging.getLogger(__name__)


def load_trails(c):
    # Cloud Trail
    if "cloudtrail" in c.config:
        for trail_name in c.config["cloudtrail"]:
            context = ["all"]
            if "in_accounts" in c.config["cloudtrail"][trail_name]:
                context = c.config["cloudtrail"][trail_name]["in_accounts"]

            for account in c.search_accounts(context):
                c.current_account = account
                add_cloudtrail(
                    c,
                    trail_name,
                    c.config["cloudtrail"][trail_name],
                    c.config["global"]["names"]["cloudtrail"]
                )


def add_cloudtrail(c, TrailName, model, named=False):
    cfn_name = c.scrub_name(TrailName + "Trail")
    kw_args = {
        "IncludeGlobalServiceEvents": True
    }

    if named:
        kw_args["TrailName"] = TrailName

    if "logging" in model:
        kw_args["IsLogging"] = model["logging"]

    if "bucket" in model:
        kw_args["DependsOn"] = c.scrub_name(model["bucket"] + "Bucket")
        kw_args["S3BucketName"] = model["bucket"]

    if "multiregion" in model:
        kw_args["IsMultiRegionTrail"] = model["multiregion"]

    if "GlobalEvents" in model:
        kw_args["IncludeGlobalServiceEvents"] = model["GlobalEvents"]

    _LOGGER.debug("Adding Trail to :{}".format(c.current_account))
    c.template[c.current_account].add_resource(Trail(
        cfn_name,
        **kw_args
    ))

    if c.config['global']['template_outputs'] == "enabled":
        c.template[c.current_account].add_output([
            Output(
                cfn_name + "Arn",
                Description="Bucket " + TrailName + " ARN",
                Value=GetAtt(cfn_name, "Arn"),
                Export=Export(Sub("${AWS::StackName}-" + cfn_name + "Arn"))
            )
        ])
