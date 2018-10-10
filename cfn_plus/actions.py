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

import json
import collections
import os
import boto3
from . import utils, template_funcs, s3_ops

def _do_mkdir(arg_node, ctx):
    # eval URI
    uri = template_funcs.eval_cfn_expr(arg_node, ctx)
    bucket_name, key = utils.parse_s3_uri(uri)
    if not key.endswith('/'):
        key += '/'

    def action(undoers, committers):
        # check if bucket exists
        if not utils.bucket_exists(bucket_name, ctx.aws_region):
            raise utils.InvalidTemplate("S3Mkdir: No such S3 bucket: {}".\
                format(bucket_name))
        bucket = boto3.resource('s3', region_name=ctx.aws_region).\
            Bucket(bucket_name)

        s3_ops.make_dir(bucket, key, undoers, committers)

    return action

def _do_sync(arg_node, ctx):
    # get args
    ex = utils.InvalidTemplate("Invalid argument for S3Sync: {}".\
        format(json.dumps(arg_node)))
    if not isinstance(arg_node, collections.Mapping) or len(arg_node) != 2:
        raise ex
    try:
        local_dir_node = arg_node['LocalDir']
        s3_dest_node = arg_node['S3Dest']
    except KeyError:
        raise ex

    # eval nodes
    local_dir = template_funcs.eval_cfn_expr(local_dir_node, ctx)
    s3_dest = template_funcs.eval_cfn_expr(s3_dest_node, ctx)
    bucket_name, dir_key = utils.parse_s3_uri(s3_dest)
    if not dir_key.endswith('/'):
        dir_key += '/'

    def action(undoers, committers):
        # check if bucket exists
        if not utils.bucket_exists(bucket_name, ctx.aws_region):
            raise utils.InvalidTemplate("S3Sync: No such S3 bucket: {}".\
                format(bucket_name))

        # make abs path to local dir
        abs_local_path = ctx.abspath(local_dir)
        if not os.path.isdir(abs_local_path):
            raise utils.InvalidTemplate("S3Sync: {} is not a directory".\
                format(abs_local_path))

        print("Syncing {} with s3://{}/{}".\
            format(abs_local_path, bucket_name, dir_key))

        # list existing files in S3
        bucket = boto3.resource('s3', region_name=ctx.aws_region).\
            Bucket(bucket_name)
        s3_files = [os.path.relpath(obj.key, start=dir_key) for \
            obj in bucket.objects.filter(Prefix=dir_key)]

        # list local files
        local_files = set([])
        for dirpath, _, filenames in os.walk(abs_local_path):
            for fn in filenames:
                local_path = os.path.join(dirpath, fn)
                relpath = os.path.relpath(local_path, start=abs_local_path)
                local_files.add(relpath)

        # delete unneeded S3 files
        files_to_delete = [f for f in s3_files if f not in local_files]
        for f in files_to_delete:
            key = dir_key + f
            s3_ops.delete_object(bucket, key, undoers, committers)

        # upload local files
        for fn in local_files:
            local_path = os.path.join(abs_local_path, fn)
            key = dir_key + fn
            with open(local_path) as f:
                s3_ops.upload_file(f, bucket, key, undoers, committers)

    return action

def _do_upload(arg_node, ctx):
    # get args
    ex = utils.InvalidTemplate("Invalid argument for S3Upload: {}".\
        format(json.dumps(arg_node)))
    if not isinstance(arg_node, collections.Mapping) or len(arg_node) != 2:
        raise ex
    try:
        local_file_node = arg_node['LocalFile']
        s3_dest_node = arg_node['S3Dest']
    except KeyError:
        raise ex

    # eval nodes
    local_file = template_funcs.eval_cfn_expr(local_file_node, ctx)
    s3_dest = template_funcs.eval_cfn_expr(s3_dest_node, ctx)
    bucket_name, key = utils.parse_s3_uri(s3_dest)
    if key.endswith('/'):
        raise utils.InvalidTemplate("S3Upload: Key must not end with '/'")

    def action(undoers, committers):
        # check if bucket exists
        if not utils.bucket_exists(bucket_name, ctx.aws_region):
            raise utils.InvalidTemplate("S3Upload: No such S3 bucket: {}".\
                format(bucket_name))
        bucket = boto3.resource('s3', region_name=ctx.aws_region).\
            Bucket(bucket_name)

        # make abs path to local file
        with open(ctx.abspath(local_file)) as f:
            s3_ops.upload_file(f, bucket, key, undoers, committers)

    return action

_ACTION_HANDLERS = {
    'S3Mkdir': _do_mkdir,
    'S3Sync': _do_sync,
    'S3Upload': _do_upload,
}

def eval_beforecreation_or_aftercreation(tag_name, arg_node, ctx):
    '''
    :return: list of functions
    '''

    if ctx.template_is_imported:
        raise utils.InvalidTemplate("Actions are not allowed in this template, " + \
            "but found {}".format(tag_name))

    ex = utils.InvalidTemplate("Invalid value for {}: {}".\
        format(tag_name, json.dumps(arg_node)))
    if not isinstance(arg_node, collections.Sequence):
        raise ex

    actions = []
    for action_node in arg_node:
        if not isinstance(action_node, collections.Mapping) or \
            len(action_node) != 1:
            raise ex

        action_name, action_arg = action_node.items()[0]
        try:
            action_handler = _ACTION_HANDLERS[action_name]
        except KeyError:
            raise utils.InvalidTemplate("Invalid action: {}".\
                format(action_name))
        actions.append(action_handler(action_arg, ctx))

    return actions
