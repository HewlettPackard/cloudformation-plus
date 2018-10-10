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

import os
import collections
import itertools
import yaml
import boto3
from botocore.exceptions import ClientError
from .utils import InvalidTemplate, Result
from .lambda_code_tag import delete_unused_lambda_code
from . import (
    utils,
    lambda_code_tag,
    before_creation_tag,
    after_creation_tag,
    bootstrap_actions_tag,
    stack_policy_tag,
    stack_resource,
)

_ARUBA_TAG_EVAL_FUNCS = {
    'Aruba::LambdaCode': lambda_code_tag.evaluate,
    'Aruba::BeforeCreation': before_creation_tag.evaluate,
    'Aruba::AfterCreation': after_creation_tag.evaluate,
    'Aruba::BootstrapActions': bootstrap_actions_tag.evaluate,
    'Aruba::StackPolicy': stack_policy_tag.evaluate,
}

_ARUBA_RESOURCE_EVAL_FUNCS = {
    'Aruba::Stack': stack_resource.evaluate,
}

def process_template(template_str, template_params, aws_region, \
    template_path=None, stack_name=None, template_is_imported=False):
    '''
    Evaluate the "Aruba::" tags in a CloudFormation template.

    Each "Aruba::" tag can produce three outputs:
        1. A transformation of the CloudFormation template
        2. An action that must be done before the stack is made/updated
        3. An action that must be done after the stack is made/updated.

    (These actions are usually S3 operations.)  This function evaluates all
    the "Aruba::" tags in the template and gathers their outputs into one
    object containing:
        1. The net result of all the template transformations
        2. A list of all the actions to be done before creation/update
        3. A list of all the actions to be done after creation/update

    This object is then returned.

    After calling this function, you must put the result in a "with"
    statement, and in the statement's body you must first call the
    do_before_creation method, then make/update the stack using the template
    in the new_template attribute, and finally call the do_after_creation
    method --- for example:

        with process_template(...) as result:
            result.do_before_creation()
            boto3.client('cloudformation').create_stack(
                TemplateBody=result.new_template,
                ...
            )
            result.do_after_creation()

    The purpose of the "with" statement is to support atomicity; if an
    exception is thrown in the do_before_creation call or in any statement
    after this call and before the do_after_creation call, the effects of the
    actions done by the do_before_creation call will be rolled back --- for
    example, objects added to S3 will be removed, objects removed from S3 will
    be restored.  Similarly, if an exception is thrown by the do_after_creation
    call, the effects of any actions done by this call will be rolled back ---
    but the effects of the do_before_creation call will NOT be rolled back.

    The most likely cause of exceptions will be problems with the original
    (non-transformed) template.  CloudFormation supports rollback of failed
    stack changes; with this library, you now can roll back S3 changes as well.

    :param template_str: The CloudFormation template to process (must be in
    YAML).
    :param template_params: A list of dicts of this form:
        {
            "ParameterKey": ...,
            "ParameterValue": ..., (optional)
            "UsePreviousValue": ... (optional)
        }

    If "UsePreviousValue" is True for any of them, then stack_name must be
    given and a stack with that name must exist.
    :param aws_region: The name of the AWS region in which the stack will be
    made.
    :param template_path: (Optional) An absolute filesystem path pointing to
    the template.  This is needed only if the template has tags containing
    paths relative to the template's path.
    :param stack_name: (Optional) The name that the stack will have when it is
    made.  This is needed only if the template uses the "AWS::StackName"
    variable, or if template_params contains an item with "UsePreviousValue"
    set to True, or if "Aruba::StackPolicy" is used.
    :param template_is_imported: Internal use only.

    :return: Cf. description of this function.

    :throw InvalidTemplate: If the template is invalid.
    :throw ValueError: If there is a problem with an argument.
    '''

    # get old stack
    old_stack = None
    if stack_name is not None:
        cfn = boto3.resource('cloudformation', region_name=aws_region)
        old_stack = cfn.Stack(stack_name)
        try:
            old_stack.reload()
        except:
            old_stack = None

    # make template param dict
    param_dict = {}
    for param in template_params:
        key = param['ParameterKey']
        use_prev = param.get('UsePreviousValue', False)
        if use_prev:
            if 'ParameterValue' in param:
                raise ValueError("Param value given but also told to use " \
                    "previous value")
            if old_stack is None:
                raise ValueError("Told to use prev param value but there " \
                    "is no existing stack")
            value = None
            for sp in old_stack.parameters:
                if sp['ParameterKey'] == key:
                    value = sp['ParameterValue']
                    break
            if value is None:
                raise ValueError("Existing stack has no param \"{}\"".\
                    format(key))
        else:
            if 'ParameterValue' not in param:
                raise ValueError("No value for param \"{}\"".format(key))
            value = param['ParameterValue']
        param_dict[key] = value

    ctx = utils.Context(param_dict, aws_region, template_path, \
        stack_name, template_is_imported, _process_template)
    return _process_template(template_str, ctx)

def _process_template(template_str, ctx):
    # We process two kinds of nodes:
    #
    #   1. Tags: nodes like "{'Aruba::Code': {...}}" in which the key starts
    #      with "Aruba::"
    #   2. Resources: objects in the "Resources" section with "Type" fields
    #      beginning with "Aruba::"
    #
    # This is done in two passes.

    template = yaml.load(template_str)

    # pass 1
    result_1 = _processs_tags(template, ctx)

    # pass 2
    result_2 = _processs_resources(result_1.new_template, ctx)

    result_2.before_creation.extend(result_1.before_creation)
    result_2.after_creation.extend(result_1.after_creation)
    result_2.new_template = _yaml_dump(result_2.new_template)
    return result_2

def _processs_tags(template, ctx):
    '''
    :return: Instance of Result.
    '''

    final_result = Result(template)

    def eval_recursive(tag_name, tag_value, parent, curr_ctx):
        if tag_name in _ARUBA_TAG_EVAL_FUNCS:
            # evauluate Aruba tag
            eval_func = _ARUBA_TAG_EVAL_FUNCS[tag_name]
            result = eval_func(tag_value, curr_ctx)

            # replace tag
            if result.new_template is not None:
                new_tag_name, new_tag_value = result.new_template
                parent[new_tag_name] = new_tag_value
            del parent[tag_name]

            final_result.before_creation.extend(result.before_creation)
            final_result.after_creation.extend(result.after_creation)

        elif isinstance(tag_value, collections.Mapping):
            for next_tag_name, next_tag_value in tag_value.items():
                # recurse
                eval_recursive(next_tag_name, next_tag_value, tag_value, \
                    curr_ctx)

    try:
        # process "Metadata" section
        if 'Metadata' in template:
            eval_recursive(None, template['Metadata'], None, ctx)

        # process "Resources" section
        if 'Resources' in template:
            for rsrc_name, rsrc_node in template['Resources'].items():
                new_ctx = ctx.copy()
                new_ctx.resource_name = rsrc_name
                new_ctx.resource_node = rsrc_node
                eval_recursive(None, rsrc_node, None, new_ctx)
    except InvalidTemplate as e:
        template_fn = os.path.basename(ctx.template_path)
        raise InvalidTemplate('{}: {}'.format(template_fn, str(e)))

    return final_result

def _processs_resources(template, ctx):
    '''
    :return: Instance of Result.
    '''

    final_result = Result(template)

    if 'Resources' not in template:
        return final_result

    resources = template['Resources']
    for name, resource in resources.items():
        # evauluate Aruba resource
        typ = resource.get('Type', '')
        try:
            eval_func = _ARUBA_RESOURCE_EVAL_FUNCS[typ]
        except KeyError:
            continue
        result = eval_func(resource, ctx)

        # replace resource
        if result.new_template is None:
            del resources[name]
        else:
            resources[name] = result.new_template

        # save actions
        final_result.before_creation.extend(result.before_creation)
        final_result.after_creation.extend(result.after_creation)

    return final_result

class _YamlDumper(yaml.dumper.SafeDumper):
    def ignore_aliases(self, data): # override
        return True

def _yaml_dump(s):
    # serialize template, and do not preseve YAML anchors (CFN does not
    # support them)
    return yaml.dump(s, Dumper=_YamlDumper)

def delete_stack(stack_name, aws_region):
    '''
    Sometimes CloudFormation cannot delete stacks containing security groups,
    for some reason.  This function doesn't have that problem.
    '''

    cf = boto3.resource('cloudformation', region_name=aws_region)
    ec2 = boto3.resource('ec2', region_name=aws_region)

    # CloudFormation sometimes has trouble deleting security groups.  This can
    # happen when an EMR cluster was deployed into a stack's VPC --- EMR makes
    # security groups for the cluster, but the stack doesn't know about them
    # and so stack deletion fails.

    # look for VPCs, and then get their security groups
    stack = cf.Stack(stack_name)
    vpc_ids = (r.physical_resource_id for r \
        in stack.resource_summaries.all() \
        if r.resource_type == 'AWS::EC2::VPC')
    vpcs = (ec2.Vpc(id) for id in vpc_ids)
    sec_groups = list(itertools.chain.from_iterable(vpc.security_groups.all() \
        for vpc in vpcs))

    # Some groups may reference each other, which
    # prevents them from being deleted.  So we need to first clear
    # out the groups' rules.
    for sg in sec_groups:
        if len(sg.ip_permissions_egress) > 0:
            sg.revoke_egress(IpPermissions=sg.ip_permissions_egress)
        if len(sg.ip_permissions) > 0:
            sg.revoke_ingress(IpPermissions=sg.ip_permissions)

    # try to delete security groups
    for sg in sec_groups:
        try:
            sg.delete()
        except ClientError:
            pass

    # delete stack
    stack.delete()
