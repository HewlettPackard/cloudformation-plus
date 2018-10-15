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
# pylint: disable=too-many-arguments
# pylint: disable=too-many-ancestors
import time
import boto3
import botocore
import cfnplus

_TEMPLATE_PATH = 'template.yml'
_STACK_NAME = 'MyApi'
_AWS_REGION = 'us-west-2'

def clean_up_changesets(cfn):
    try:
        resp = cfn.list_change_sets(StackName=_STACK_NAME)
    except botocore.exceptions.ClientError:
        return
    for cs in resp['Summaries']:
        cfn.delete_change_set(ChangeSetName=cs['ChangeSetId'])

def make_or_update_stack(cfn, template, params):
    # does stack exist?
    try:
        cfn.describe_stacks(StackName=_STACK_NAME)
        stack_exists = True
    except botocore.exceptions.ClientError:
        stack_exists = False

    # make change set
    change_set = cfn.create_change_set(
        StackName=_STACK_NAME,
        TemplateBody=template,
        Parameters=params,
        Capabilities=['CAPABILITY_IAM'],
        ChangeSetName='{}-change-set'.format(_STACK_NAME),
        ChangeSetType='UPDATE' if stack_exists else 'CREATE',
    )

    # wait for change set to get made
    while True:
        resp = cfn.describe_change_set(ChangeSetName=change_set['Id'])
        status = resp['Status']
        if status == 'CREATE_COMPLETE':
            break
        elif status == 'FAILED':
            reason = resp['StatusReason']

            if "The submitted information didn't contain changes." in reason or \
                "No updates are to be performed." in reason:
                print("No changes")
                return

            msg = "Failed to make change set for {}: {}".\
                format(_STACK_NAME, reason)
            raise Exception(msg)

        time.sleep(2)

    # execute change set
    cfn.execute_change_set(ChangeSetName=change_set['Id'])

    # wait for execution to finish
    if stack_exists:
        waiter = cfn.get_waiter('stack_update_complete')
    else:
        waiter = cfn.get_waiter('stack_create_complete')
    waiter.wait(StackName=_STACK_NAME)

def main():
    cfn = boto3.client('cloudformation', region_name=_AWS_REGION)

    # read template
    with open(_TEMPLATE_PATH) as f:
        template = f.read()

    params = [
        {'ParameterKey': 'Bucket', 'ParameterValue': 'niara-tmp'},
        {'ParameterKey': 'BucketArn', 'ParameterValue': 'arn:aws:s3:::niara-tmp'},
    ]

    # process language extensions
    with cfnplus.process_template(
        template,
        params, # template params
        _AWS_REGION,
        _TEMPLATE_PATH,
        _STACK_NAME,
    ) as cfnp_result:

        # do actions that must be done before stack creation/update
        cfnp_result.do_before_creation()

        try:
            make_or_update_stack(cfn, cfnp_result.new_template, params)
        finally:
            clean_up_changesets(cfn)

        # do actions that must be done after stack creation/update
        cfnp_result.do_after_creation()

if __name__ == '__main__':
    main()
