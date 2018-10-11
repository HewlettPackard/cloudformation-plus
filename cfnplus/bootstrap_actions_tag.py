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
from . import utils

USER_DATA_SCRIPT_TEMPLATE = '''
#!/bin/bash -x

mkdir /var/log/aruba-bootstrap
exec >/var/log/aruba-bootstrap/main 2>&1

function go() {{
    {go_body}
}}

# run steps
go
EXIT_CODE=$?

if [ {should_copy_log} == True ]; then
    # copy log to S3
    aws s3 cp --content-type text/plain /var/log/aruba-bootstrap/main \
        "${{log_uri}}/main"
fi

# notify CloudFormation of result
yum install -y aws-cfn-bootstrap
/opt/aws/bin/cfn-signal -e "${{!EXIT_CODE}}" --stack "${{AWS::StackName}}" \
    --resource "{rsrc_name}" --region "${{AWS::Region}}"
'''

RUN_BS_SCRIPT_TEMPLATE = '''
    LOG_LOCAL_PATH="/var/log/aruba-bootstrap/{action_nbr}"
    SCRIPT_LOCAL_PATH="/tmp/aruba-bootstrap/{action_nbr}"

    # run script
    mkdir -p "$(dirname ${{!SCRIPT_LOCAL_PATH}})"
    aws s3 cp "${{s3_uri_{action_nbr}}}" "${{!SCRIPT_LOCAL_PATH}}"
    chmod +x "${{!SCRIPT_LOCAL_PATH}}"
    sudo -u ec2-user "${{!SCRIPT_LOCAL_PATH}}" {args} > \
        "${{!LOG_LOCAL_PATH}}" 2>&1
    EXIT_CODE=$?

    if [ {should_copy_log} == True ]; then
        # copy log to S3
        aws s3 cp --content-type text/plain "${{!LOG_LOCAL_PATH}}" \
            "${{log_uri}}/{action_nbr}"
    fi

    if [ "${{!EXIT_CODE}}" -ne 0 ]; then
        return 1
    fi

'''

def evaluate(arg_node, ctx):
    '''
    :return: Instance of Result.
    '''

    # This evaluation is purely text-manipulation: no variables are
    # dereferenced, and there are no side-effects.

    tag_name = 'Aruba::BootstrapActions'
    if not isinstance(arg_node, collections.Mapping):
        raise utils.InvalidTemplate("{}: must contain mapping".format(tag_name))
    try:
        actions_node = arg_node['Actions']
        log_uri_node = arg_node.get('LogUri')
        timeout_node = arg_node['Timeout']
    except KeyError as e:
        raise utils.InvalidTemplate("{}: missing '{}'".\
            format(tag_name, e.args[0]))

    # check 'Actions' argument
    if not isinstance(actions_node, collections.Sequence):
        raise utils.InvalidTemplate("{}: 'Actions' must contain a sequence".\
            format(tag_name))

    # make UserData script
    cfn_subs = {
        'log_uri': log_uri_node if log_uri_node is not None else 'unset',
    }
    go_body = ''
    for i, action_node in enumerate(actions_node):
        # get child nodes
        try:
            path_node = action_node['Path']
        except KeyError:
            raise utils.InvalidTemplate("{}: an action is missing '{}'".\
                format(tag_name, e.args[0]))

        cfn_subs['s3_uri_{}'.format(i)] = path_node

        args_node = action_node.get('Args', [])
        args = []
        for j, n in enumerate(args_node):
            placeholder = 'arg_{}_{}'.format(i, j)
            cfn_subs[placeholder] = n
            args.append('"${' + placeholder + '}"')

        go_body += RUN_BS_SCRIPT_TEMPLATE.format(
            action_nbr=i,
            args=' '.join(args),
            should_copy_log=log_uri_node is not None,
        )

    user_data_script = USER_DATA_SCRIPT_TEMPLATE.format(
        go_body=go_body,
        rsrc_name=ctx.resource_name,
        should_copy_log=log_uri_node is not None,
    )
    user_data_node = {
        'Fn::Base64': {
            'Fn::Sub': [
                user_data_script,
                cfn_subs
            ],
        }
    }

    # add creation policy
    ctx.resource_node['CreationPolicy'] = {
        'ResourceSignal': {'Timeout': timeout_node},
    }

    return utils.Result(new_template=('UserData', user_data_node))
