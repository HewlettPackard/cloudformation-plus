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
import cStringIO
import unittest
import numbers
from . import utils

def eval_cfn_expr(node, ctx):
    if isinstance(node, utils.base_str) or isinstance(node, numbers.Number): # pylint: disable=consider-merging-isinstance
        return node

    if not isinstance(node, collections.Mapping) or len(node) != 1:
        node_str = json.dumps(node)
        raise utils.InvalidTemplate("e string expression: {}".format(node_str))

    handlers = {
        'Fn::Sub': _eval_cfn_sub,
        'Fn::ImportValue': _eval_cfn_importvalue,
        'Ref': _eval_cfn_ref,
    }

    func_name = node.keys()[0]
    func_arg = node[func_name]
    try:
        h = handlers[func_name]
    except KeyError:
        raise utils.InvalidTemplate("Unknown function: {}".format(func_name))
    return h(func_arg, ctx)

def _eval_cfn_ref(node, ctx):
    '''
    :param node: The argument to a 'Ref' call
    :return: The referenced value
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
    :param node: The argument to an 'Fn::ImportValue' call
    :return: The imported value
    '''

    var_name = eval_cfn_expr(node, ctx)
    return ctx.resolve_cfn_export(var_name)

def _eval_cfn_sub(node, ctx):
    '''
    :param node: The argument to an 'Fn::Sub' call
    :return: The computed string
    '''

    if isinstance(node, utils.base_str):
        return _eval_cfn_sub_str(node, ctx)
    elif isinstance(node, collections.Sequence):
        return _eval_cfn_sub_list(node, ctx)
    else:
        raise utils.InvalidTemplate("Invalid arg for 'Fn::Sub': {}".\
            format(json.dumps(node)))

def _eval_cfn_sub_str(node, ctx):
    '''
    :param node: The string argument to an 'Fn::Sub' call
    :return: The computed string
    '''

    regex = re.compile(r'\$\{([-.:_0-9a-zA-Z]*)\}')
    pos = 0
    result_buff = cStringIO.StringIO()
    while True:
        # look for variable ref
        match = regex.search(node, pos=pos)
        if match is None:
            break

        # resolve variable
        var_name = match.group(1)
        try:
            var_value = ctx.resolve_var(var_name)
        except KeyError:
            raise utils.InvalidTemplate("Cannot resolve variable \"{}\"".\
                format(var_name))

        # write variable's value to result
        result_buff.write(node[pos:match.start()])
        result_buff.write(str(var_value))
        pos = match.end()

    result_buff.write(node[pos:])
    return result_buff.getvalue()

def _eval_cfn_sub_list(node, ctx):
    '''
    :param node: The list argument to an 'Fn::Sub' call
    :return: The computed string
    '''

    ex = utils.InvalidTemplate("Invalid arg for 'Fn::Sub': {}".\
        format(json.dumps(node)))
    if len(node) != 2:
        raise ex

    # eval format string
    format_str = eval_cfn_expr(node[0], ctx)

    # eval local symbols
    new_ctx = ctx.copy()
    local_symbols = node[1]
    if not isinstance(local_symbols, collections.Mapping):
        raise ex
    for k, v in local_symbols.items():
        new_ctx.set_var(k, eval_cfn_expr(v, ctx))

    # do substitution
    return _eval_cfn_sub_str(format_str, new_ctx)

class _Test(unittest.TestCase):
    def testSubWithString(self):
        cases = [
            {
                'exp': {'Fn::Sub': 'my name is Woobie!'},
                'symbols': {},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {'Fn::Sub': 'my name is ${name}!'},
                'symbols': {'name': 'Woobie'},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {'Fn::Sub': 'my ${attr} is ${value}!'},
                'symbols': {'attr': 'name', 'value': 'Woobie'},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {'Fn::Sub': 'I have ${n} cats!'},
                'symbols': {'n': 2},
                'result': 'I have 2 cats!',
            },
        ]

        for case in cases:
            #
            # Set up
            #
            ctx = utils.Context(case['symbols'])

            #
            # Call
            #
            result = eval_cfn_expr(case['exp'], ctx)

            #
            # Test
            #
            self.assertEqual(case['result'], result)

    def testSubWithList(self):
        cases = [
            {
                'exp': {
                    'Fn::Sub': [
                        'my name is Woobie!',
                        {},
                    ],
                },
                'symbols': {},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {
                    'Fn::Sub': [
                        'my name is ${name}!',
                        {'name': 'Woobie'},
                    ],
                },
                'symbols': {},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {
                    'Fn::Sub': [
                        'my ${attr} is ${value}!',
                        {'attr': 'name', 'value': 'Woobie'},
                    ],
                },
                'symbols': {},
                'result': 'my name is Woobie!',
            },
            {
                'exp': {
                    'Fn::Sub': [
                        'my ${attr} is ${value}!',
                        {'value': 'Woobie'},
                    ],
                },
                'symbols': {'attr': 'name'},
                'result': 'my name is Woobie!',
            },
        ]

        for case in cases:
            #
            # Set up
            #
            ctx = utils.Context(case['symbols'])

            #
            # Call
            #
            result = eval_cfn_expr(case['exp'], ctx)

            #
            # Test
            #
            self.assertEqual(case['result'], result)

    def testImportWithSub(self):
        #
        # Set up
        #
        exp = {
            'Fn::ImportValue': {'Fn::Sub': 'Tc-${DeployId}-BucketName'}
        }
        ctx = utils.Context({'DeployId': '1'})
        ctx.resolve_cfn_export = lambda k: 'woobie' if k == 'Tc-1-BucketName' \
            else None

        #
        # Call
        #
        result = eval_cfn_expr(exp, ctx)

        #
        # Test
        #
        self.assertEqual('woobie', result)

    def testRefWithRegVar(self):
        #
        # Set up
        #
        ctx = utils.Context({'Bucket': 'Woobie'})

        #
        # Call
        #
        result = eval_cfn_expr({'Ref': 'Bucket'}, ctx)

        #
        # Test
        #
        self.assertEqual('Woobie', result)

    def testRefWithBuiltInVar(self):
        #
        # Set up
        #
        ctx = utils.Context({}, aws_region='us-west-2')

        #
        # Call
        #
        result = eval_cfn_expr({'Ref': 'AWS::Region'}, ctx)

        #
        # Test
        #
        self.assertEqual('us-west-2', result)

if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(_Test)
    unittest.TextTestRunner(verbosity=2).run(suite)
