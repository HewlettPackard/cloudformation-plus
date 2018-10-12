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
import unittest
from cfnplus.eval_cfn_expr import eval_expr
from cfnplus.utils import Context

class EvalCfnExprTest(unittest.TestCase):
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
            ctx = Context(case['symbols'])

            #
            # Call
            #
            result = eval_expr(case['exp'], ctx)

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
            ctx = Context(case['symbols'])

            #
            # Call
            #
            result = eval_expr(case['exp'], ctx)

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
        ctx = Context({'DeployId': '1'})
        ctx.resolve_cfn_export = lambda k: 'woobie' if k == 'Tc-1-BucketName' \
            else None

        #
        # Call
        #
        result = eval_expr(exp, ctx)

        #
        # Test
        #
        self.assertEqual('woobie', result)

    def testRefWithRegVar(self):
        #
        # Set up
        #
        ctx = Context({'Bucket': 'Woobie'})

        #
        # Call
        #
        result = eval_expr({'Ref': 'Bucket'}, ctx)

        #
        # Test
        #
        self.assertEqual('Woobie', result)

    def testRefWithBuiltInVar(self):
        #
        # Set up
        #
        ctx = Context({}, aws_region='us-west-2')

        #
        # Call
        #
        result = eval_expr({'Ref': 'AWS::Region'}, ctx)

        #
        # Test
        #
        self.assertEqual('us-west-2', result)
