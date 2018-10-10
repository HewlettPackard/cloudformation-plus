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
import hashlib
import json
import cStringIO
import boto3
from . import utils, template_funcs, s3_ops

def evaluate(resource, ctx):
    '''
    :return: Instance of Result.
    '''

    # 1. Compute local vars for imported template
    # 2. Evaluate Aruba tags in imported template
    # 3. Upload imported template to S3
    # 4. Make 'AWS::CloudFormation::Stack' resource

    if ctx.template_is_imported:
        raise utils.InvalidTemplate("Cannot have imported template in " + \
            "imported template")

    # check resource contents
    ex = utils.InvalidTemplate("Invalid argument for Aruba::Stack: {}".\
        format(json.dumps(resource)))
    if not isinstance(resource, collections.Mapping):
        raise ex
    try:
        props = resource['Properties']
    except KeyError:
        raise ex
    if not isinstance(props, collections.Mapping):
        raise ex
    try:
        template_node = props['Template']
    except KeyError:
        raise ex
    if not isinstance(template_node, collections.Mapping):
        raise ex
    try:
        local_path_node = template_node['LocalPath']
        s3_dest_node = template_node['S3Dest']
    except KeyError:
        raise ex
    params_node = props.get('Parameters')

    # eval nodes
    local_path = template_funcs.eval_cfn_expr(local_path_node, ctx)
    s3_dest = template_funcs.eval_cfn_expr(s3_dest_node, ctx)
    s3_bucket, s3_dir_key = utils.parse_s3_uri(s3_dest)

    # compute local vars
    new_ctx = ctx.copy()
    if params_node is not None:
        for param_name, param_node in params_node.items():
            try:
                param_value = template_funcs.eval_cfn_expr(param_node, ctx)
            except utils.InvalidTemplate:
                # it's okay; not everything needs to be resolvable at this point
                continue
            new_ctx.set_var(param_name, param_value)

    # eval Aruba tags in imported template
    template_abs_path = ctx.abspath(local_path)
    with open(template_abs_path) as f:
        imported_template_str = f.read()
    new_ctx.template_is_imported = True
    new_ctx.template_path = template_abs_path
    new_ctx.stack_name = None
    new_template_str = ctx.proc_result_cache_get(imported_template_str, new_ctx)
    if new_template_str is None:
        print("Evaluating Aruba tags in {}".format(template_abs_path))
        result = ctx.process_template_func(imported_template_str, new_ctx)

        # add to cache
        ctx.proc_result_cache_put(imported_template_str, new_ctx, \
            result.new_template)
    else:
        result = utils.Result(new_template=new_template_str)

    # make S3 key
    h = hashlib.new(utils.FILE_HASH_ALG)
    h.update(result.new_template)
    s3_key = '{}/{}'.format(s3_dir_key, h.hexdigest())

    def upload_action(undoers, committers):
        buf = cStringIO.StringIO()
        buf.write(result.new_template)
        buf.seek(0)
        bucket = boto3.resource('s3', region_name=ctx.aws_region).\
            Bucket(s3_bucket)
        s3_ops.upload_file(buf, bucket, s3_key, undoers, committers)

    # make 'AWS::CloudFormation::Stack' resource
    s3_dest_uri = 'https://s3-{region}.amazonaws.com/{bucket}/{key}'\
        .format(region=ctx.aws_region, bucket=s3_bucket, key=s3_key)
    cfn_resource = {
        'Type': 'AWS::CloudFormation::Stack',
        'Properties': {
            'TemplateURL': s3_dest_uri,
        },
    }
    if params_node is not None:
        cfn_resource['Properties']['Parameters'] = params_node

    final_result = utils.Result(
        new_template=cfn_resource,
        before_creation=[upload_action] + result.before_creation,
        after_creation=result.after_creation,
    )
    return final_result
