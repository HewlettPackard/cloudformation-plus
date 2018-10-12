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
# pylint: disable=too-few-public-methods
# pylint: disable=unused-argument
import json
import re
import collections
import numbers
from . import utils

def eval_expr(node, ctx):
    '''
    Evaluate CloudFormation template nodes like "{Ref: SomeItem}",
    "{'Fn::Sub': AnotherItem.SomeAttr}", and "{'Fn::ImportVaue': AnExportName}"
    that represent scalar values.

    :param node: A node from a parsed CloudFormation template that represents
    a scalar value.
    :param ctx: An instance of utils.Context.  It will be used to resolve
    references in the node.

    :return: The scalar value represented by the given node.
    :throw: utils.InvalidTemplate
    '''

    if isinstance(node, (utils.base_str, numbers.Number)):
        return node

    if not isinstance(node, collections.Mapping) or len(node) != 1:
        node_str = json.dumps(node)
        raise utils.InvalidTemplate("Invalid scalar expression: {}".\
            format(node_str))

    handlers = {
        'Fn::Sub': _eval_cfn_sub,
        'Fn::ImportValue': _eval_cfn_importvalue,
        'Ref': _eval_cfn_ref,
    }

    func_name, func_arg = utils.dict_only_item(node)
    try:
        h = handlers[func_name]
    except KeyError:
        raise utils.InvalidTemplate("Unknown function: {}".format(func_name))
    return h(func_arg, ctx)

def _eval_cfn_ref(node, ctx):
    '''
    :param node: The argument to a 'Ref' expression.
    :param ctx: An instance of utils.Context.

    :return: The referenced scalar value.
    :throw: utils.InvalidTemplate
    '''

    if not isinstance(node, utils.base_str):
        raise utils.InvalidTemplate("Invalid arg for 'Ref': {}".\
            format(json.dumps(node)))

    try:
        return ctx.resolve_var(node)
    except KeyError:
        raise utils.InvalidTemplate("Cannot resolve variable \"{}\"".\
            format(node))

def _eval_cfn_importvalue(node, ctx):
    '''
    :param node: The argument to an 'Fn::ImportValue' expression.
    :param ctx: An instance of utils.Context.

    :return: The imported scalar value.
    :throw: utils.InvalidTemplate
    '''

    var_name = eval_expr(node, ctx)
    return ctx.resolve_cfn_export(var_name)

def _eval_cfn_sub(node, ctx):
    '''
    :param node: The argument to an 'Fn::Sub' expression.
    :param ctx: An instance of utils.Context.

    :return: The computed string.
    :throw: utils.InvalidTemplate
    '''

    # Arg to 'Fn::Sub' can be string or list.  If it's a string, we normalize
    # it to a list.

    if isinstance(node, utils.base_str):
        node = [node, {}]

    ex = utils.InvalidTemplate("Invalid arg for 'Fn::Sub': {}".\
        format(json.dumps(node)))
    if not isinstance(node, collections.Sequence) or len(node) != 2:
        raise ex

    # get components of arg
    format_str = node[0]
    local_symbols = node[1]
    if not isinstance(format_str, utils.base_str) or \
        not isinstance(local_symbols, collections.Mapping):
        raise ex

    # eval local symbols
    new_ctx = ctx.copy()
    for k, v in local_symbols.items():
        new_ctx.set_var(k, eval_expr(v, ctx))

    # make substitutions in format string
    regex = re.compile(r'\$\{([-.:_0-9a-zA-Z]*)\}')
    pos = 0
    result_buff = utils.StringIO()
    while True:
        # look for variable ref
        match = regex.search(format_str, pos=pos)
        if match is None:
            break

        # resolve variable
        var_name = match.group(1)
        try:
            var_value = new_ctx.resolve_var(var_name)
        except KeyError:
            raise utils.InvalidTemplate("Cannot resolve variable \"{}\"".\
                format(var_name))

        # write variable's value to result
        result_buff.write(format_str[pos:match.start()])
        result_buff.write(str(var_value))
        pos = match.end()

    result_buff.write(format_str[pos:])
    return result_buff.getvalue()
