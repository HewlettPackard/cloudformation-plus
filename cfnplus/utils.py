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
# pylint: disable=too-many-instance-attributes

import os
import json
import urlparse
import boto3
import botocore

base_str = (str, unicode)

FILE_HASH_ALG = 'sha1'

class InvalidTemplate(Exception):
    pass

def bucket_exists(bucket_name, aws_region):
    s3 = boto3.client('s3', region_name=aws_region)
    try:
        s3.head_bucket(Bucket=bucket_name)
    except botocore.exceptions.ClientError as e:
        # If a client error is thrown, then check that it was a 404 error.
        # If it was a 404 error, then the bucket does not exist.
        error_code = int(e.response['Error']['Code'])
        if error_code == 404:
            return False
        else:
            raise e
    return True

def parse_s3_uri(uri):
    '''
    :return: A pair (bucket, key)
    '''

    uri = urlparse.urlparse(uri)
    if uri.scheme != 's3':
        raise InvalidTemplate("Invalid URI: '{}'".format(uri))
    bucket = uri.netloc
    key = uri.path
    if key.startswith('/'):
        key = key[1:]
    return (bucket, key)

class Context(object):
    def __init__(self, symbols, aws_region=None, \
        template_path=None, stack_name=None, template_is_imported=False, \
        process_template_func=None, resource_name=None, resource_node=None):
        self._symbols = dict(**symbols)
        self.aws_region = aws_region
        self.template_path = template_path
        self.stack_name = stack_name
        self.template_is_imported = template_is_imported
        self.process_template_func = process_template_func
        self.resource_name = resource_name
        self.resource_node = resource_node
        self._proc_result_cache = {}

    def copy(self):
        ctx = Context(
            self._symbols,
            aws_region=self.aws_region,
            template_path=self.template_path,
            stack_name=self.stack_name,
            template_is_imported=self.template_is_imported,
            process_template_func=self.process_template_func,
            resource_name=self.resource_name,
            resource_node=self.resource_node)
        ctx._proc_result_cache = self._proc_result_cache # pylint: disable=protected-access
        return ctx

    @property
    def _built_in_vars(self):
        var_map = {}
        if self.aws_region is not None:
            var_map['AWS::Region'] = self.aws_region
        if self.stack_name is not None:
            var_map['AWS::StackName'] = self.stack_name
        return var_map

    def resolve_var(self, symbol):
        try:
            return self._symbols[symbol]
        except KeyError:
            return self._built_in_vars[symbol]

    def set_var(self, symbol, value):
        self._symbols[symbol] = value

    def resolve_cfn_export(self, var_name):
        cf = boto3.client('cloudformation', region_name=self.aws_region)
        args = {}
        while True:
            result = cf.list_exports(**args)
            for export in result['Exports']:
                if export['Name'] == var_name:
                    return export['Value']

            try:
                args['NextToken'] = result['NextToken']
            except KeyError:
                raise InvalidTemplate("No such CloudFormation export: {}".\
                    format(var_name))

    def abspath(self, rel_path):
        template_dir = os.path.dirname(self.template_path)
        return os.path.abspath(os.path.join(template_dir, rel_path))

    @staticmethod
    def _proc_result_cache_make_key(template_str, ctx):
        attrs = ['_symbols', 'aws_region', 'template_path', 'stack_name', \
            'template_is_imported']
        d = {'template_str': template_str}
        for attr in attrs:
            d[attr] = getattr(ctx, attr)
        return json.dumps(d)

    def proc_result_cache_get(self, template_str, ctx):
        '''
        It is possible that a template is processed multiple times, so we'd like
        to keep a cache of results.  Since template processing is a function
        of both templates and contexts, we need to include the context in
        the cache key along with the template.  So we need a way to serialize
        or hash the context (or at least the parts of the context that are
        relevant to template processing).

        :return: The processed template as a string, or None.
        '''


        key = self._proc_result_cache_make_key(template_str, ctx)
        try:
            return self._proc_result_cache[key]
        except KeyError:
            return None

    def proc_result_cache_put(self, template_str, ctx, new_template_str):
        key = self._proc_result_cache_make_key(template_str, ctx)
        self._proc_result_cache[key] = new_template_str

class Result(object):
    '''
    An instance of this class represents the result of processing a template.
    Such a result consists of
        - the new template
        - actions that should be done before the stack is created or updated
        - actions that should be done after the stack is created or updated
    '''

    def __init__(self, new_template=None, before_creation=None, \
        after_creation=None):
        self.new_template = new_template
        self.before_creation = [] if before_creation is None else before_creation
        self.after_creation = [] if after_creation is None else after_creation
        self._undoers = []
        self._committers = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is None:
                for action in self._committers:
                    action()
                self._committers = []
            else:
                print("Undoing CloudFormation Plus actions")
                while len(self._undoers) > 0:
                    action = self._undoers.pop()
                    action()
        except:
            pass

    def do_before_creation(self):
        '''
        Perform actions that should be done before the stack is created or
        updated.
        '''

        # do before-creation actions
        for action in self.before_creation:
            action(self._undoers, self._committers)

    def do_after_creation(self):
        '''
        Perform actions that should be done after the stack is created or
        updated.
        '''

        # commit the before-creation actions
        for action in self._committers:
            action()
        self._committers = []
        self._undoers = []

        # do after-creation actions
        for action in self.after_creation:
            action(self._undoers, self._committers)
