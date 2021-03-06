# (C) Copyright 2018 Hewlett Packard Enterprise Development LP.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# and in the "LICENSE.txt" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.

# pylint: disable=superfluous-parens
# pylint: disable=invalid-name
# pylint: disable=missing-docstring
# pylint: disable=global-statement
# pylint: disable=broad-except
# pylint: disable=bare-except
# pylint: disable=too-many-branches
# pylint: disable=too-many-statements
# pylint: disable=too-many-return-statements
# pylint: disable=import-error
# pylint: disable=no-else-return
# pylint: disable=len-as-condition
# pylint: disable=too-many-locals
# pylint: disable=unused-argument

import collections
import json
import boto3
from . import utils

def evaluate(arg_node, ctx):
    '''
    :return: Instance of Result.
    '''

    tag_name = 'Aruba::StackPolicy'
    if not isinstance(arg_node, collections.Mapping):
        raise utils.InvalidTemplate("{}: must contain mapping".\
            format(tag_name))
    if ctx.stack_name is None:
        raise utils.InvalidTemplate("{}: stack name is unknown".\
            format(tag_name))

    def set_policy_action(undoers, committers):
        cfn = boto3.client('cloudformation', region_name=ctx.aws_region)
        print("Setting policy for stack {}".format(ctx.stack_name))
        cfn.set_stack_policy(
            StackName=ctx.stack_name,
            StackPolicyBody=json.dumps(arg_node),
        )
    return utils.Result(after_creation=[set_policy_action])
