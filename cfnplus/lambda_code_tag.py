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

import os
import hashlib
import zipfile
import collections
import json
import tempfile
import struct
import yaml
import boto3
from . import template_funcs, utils, s3_ops

class _LambdaPkgMaker(object):
    '''
    This class makes AWS Lambda function packages --- i.e., zipfiles of code.
    It also computes a hash of such packages based (only) on their contents.
    '''

    # IMPLEMENTATION NOTE: We cannot just take the hash of the zipfile b/c
    # zipfiles contain crap like timestamps that we do not want to influence
    # the hash.
    #
    # Instead, we take the hash of a bytestring that represents the zipfile's
    # contents.  The bytestring consists of a series of records of this form:
    #
    #       <path_in_zipfile_len><path_in_zipfile><file_contents_len><file_contents>
    #
    # with one record for each file in the zipfile.

    def __init__(self):
        self._entries = {} # package path -> abs path

    def add(self, local_path, pkg_path):
        self._entries[pkg_path] = local_path

    @property
    def hash(self):
        h = hashlib.new(utils.FILE_HASH_ALG)
        for pkg_path, local_path in self._entries.items():
            h.update(struct.pack('>Q', len(pkg_path))) # path_in_zipfile_len
            h.update(pkg_path) # path_in_zipfile
            stat = os.stat(local_path)
            h.update(struct.pack('>Q', stat.st_size)) # file_contents_len
            with open(local_path) as f: # file_contents
                while True:
                    data = f.read(1024)
                    if len(data) == 0:
                        break
                    h.update(data)

        return h.hexdigest()

    def open(self):
        f = tempfile.TemporaryFile() # will be deleted when closed
        try:
            with zipfile.ZipFile(f, 'w') as z:
                for pkg_path, local_path in self._entries.items():
                    z.write(local_path, arcname=pkg_path)

            f.seek(0)
            return f
        except:
            f.close()
            raise

def evaluate(arg_node, ctx):
    '''
    :return: Instance of Result.
    '''

    ex = utils.InvalidTemplate("Invalid argument for Aruba::LambdaCode: {}".\
        format(json.dumps(arg_node)))
    if not isinstance(arg_node, collections.Mapping):
        raise ex
    try:
        local_path_node = arg_node['LocalPath']
        s3_dest_node = arg_node['S3Dest']
    except KeyError:
        raise ex

    # eval nodes in arg
    local_path = template_funcs.eval_cfn_expr(local_path_node, ctx)
    s3_dest = template_funcs.eval_cfn_expr(s3_dest_node, ctx)
    bucket_name, dir_key = utils.parse_s3_uri(s3_dest)

    # make abs path to local dir
    abs_local_path = ctx.abspath(local_path)
    if not os.path.isdir(abs_local_path):
        raise utils.InvalidTemplate("{} is not a directory".\
            format(abs_local_path))

    # make package
    pkg_maker = _LambdaPkgMaker()
    for parent, _, filenames in os.walk(abs_local_path):
        for fn in filenames:
            local_path = os.path.join(parent, fn)
            pkg_path = os.path.relpath(local_path, start=abs_local_path)
            pkg_maker.add(local_path, pkg_path)

    # compute S3 key
    s3_key = '{}/{}'.format(dir_key, pkg_maker.hash)

    def action(undoers, committers):
        # check if bucket exists
        if not utils.bucket_exists(bucket_name, ctx.aws_region):
            raise utils.InvalidTemplate("No such S3 bucket: {}".\
                format(bucket_name))
        bucket = boto3.resource('s3', region_name=ctx.aws_region).\
            Bucket(bucket_name)

        with pkg_maker.open() as f:
            s3_ops.upload_file(f, bucket, s3_key, undoers, committers)

    # make new tag
    new_tag_value = {
        'S3Bucket': bucket_name,
        'S3Key': s3_key,
    }

    return utils.Result(new_template=('Code', new_tag_value), \
        before_creation=[action])

def delete_unused_lambda_code(stack_names, bucket_name, s3_code_prefix, \
    aws_region):
    # In order to support rollbacks, we need to keep Lambda functions' source
    # in S3 (even though it isn't actually used when the functions run).
    # Eventually function code gets replaced with new verions, so we need to
    # delete old code that's no longer referenced by a stack.

    cf = boto3.client('cloudformation', region_name=aws_region)

    if not s3_code_prefix.endswith('/'):
        s3_code_prefix += '/'

    # make list of code files referenced by any stack
    refed_code = set([])
    for stack_name in stack_names:
        resp = cf.get_template(StackName=stack_name, TemplateStage='Original')
        template = yaml.load(resp['TemplateBody'])
        for _, rsrc in template['Resources'].items():
            if rsrc['Type'] != 'AWS::Lambda::Function':
                continue
            code_node = rsrc['Properties']['Code']
            curr_bucket = code_node['S3Bucket']
            curr_key = code_node['S3Key']
            if curr_bucket != bucket_name or \
                not curr_key.startswith(s3_code_prefix):
                continue
            refed_code.add(curr_key)

    # delete unreferenced code files from S3
    bucket = boto3.resource('s3', region_name=aws_region).Bucket(bucket_name)
    for obj in bucket.objects.filter(Prefix=s3_code_prefix):
        if obj.key in refed_code:
            continue
        print("Deleting unused Lambda code s3://{}/{}".\
            format(bucket_name, obj.key))
        obj.delete()
