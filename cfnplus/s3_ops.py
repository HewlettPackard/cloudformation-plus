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

import hashlib
import base64
import botocore
from . import utils

def upload_file(f, bucket, key, undoers, committers):
    # If there's no existing object:
    #    Do: upload file
    #    Undo: delete latest version
    #    Commit: nop
    #
    # If existing file is different:
    #    Do: add new version
    #    Undo: delete latest version
    #    Commit: delete previous version
    #
    # If existing file is same:
    #    Do: nop
    #    Undo: nop
    #    Commit: nop

    HASH_METADATA_KEY = '{}_sum'.format(utils.FILE_HASH_ALG)

    # get file's hash
    h = hashlib.new(utils.FILE_HASH_ALG)
    while True:
        buf = f.read(1024)
        if len(buf) == 0:
            break
        h.update(buf)
    hashvalue = str(base64.b64encode(h.digest()))

    # check if file was already uploaded
    previous_version = None
    try:
        prev_obj = bucket.Object(key)
        previous_version = prev_obj.version_id
        existing_hash = prev_obj.metadata.get(HASH_METADATA_KEY)
    except botocore.exceptions.ClientError:
        pass
    else:
        if existing_hash == hashvalue:
            # object already exists
            return

    # upload file
    print("Uploading to s3://{}/{}".format(bucket.name, key))
    f.seek(0)
    obj = bucket.put_object(
        Body=f,
        Key=key,
        Metadata={HASH_METADATA_KEY: hashvalue})
    obj.wait_until_exists()
    if obj.version_id is None:
        obj.delete()
        raise Exception("Bucket must have versioning enabled")
    new_version = obj.version_id

    # add undoer
    def undo():
        obj.delete(VersionId=new_version)
        obj.wait_until_not_exists(VersionId=new_version)
    undoers.append(undo)

    # add committer
    if previous_version is not None:
        def commit():
            obj.delete(VersionId=previous_version)
            obj.wait_until_not_exists(VersionId=previous_version)
        committers.append(commit)

def delete_object(bucket, key, undoers, committers):
    # If object exists:
    #   Do: insert delete marker for object
    #   Undo: delete the delete marker
    #   Commit: delete all versions
    #
    # If object does not exist:
    #   Do: nop
    #   Undo: nop
    #   Commit: nop

    # check if object exists
    obj = bucket.Object(key)
    try:
        obj.reload()
    except botocore.exceptions.ClientError:
        # doesn't exist
        return
    prev_version = obj.version_id
    if prev_version is None:
        raise Exception("Bucket must have versioning enabled")

    # delete object (this inserts a delete marker version)
    print("Deleting s3://{}/{}".format(bucket.name, key))
    resp = obj.delete()
    delete_marker_version = resp['VersionId']
    obj.wait_until_not_exists()

    # add undoer
    def undo():
        # delete the delete marker
        obj.delete(VersionId=delete_marker_version)
        obj.wait_until_not_exists(VersionId=delete_marker_version)
    undoers.append(undo)

    # add committer
    def commit():
        # delete all versions
        obj.delete(VersionId=prev_version)
        obj.wait_until_not_exists(VersionId=prev_version)
        obj.delete(VersionId=delete_marker_version)
        obj.wait_until_not_exists(VersionId=delete_marker_version)
    committers.append(commit)

def make_dir(bucket, key, undoers, committers):
    # If dir does not already exist:
    #   Do: make dir
    #   Undo: delete dir (latest version)
    #   Commit: nop
    #
    # If dir already exists:
    #   Do: nop
    #   Undo: nop
    #   Commit: nop

    # check if dir already exists
    files = bucket.objects.filter(Prefix=key)
    if len(list(files)) > 0:
        # already exists
        return

    # make dir
    print("Making directory at s3://{}/{}".format(bucket.name, key))
    obj = bucket.put_object(Key=key)
    obj.wait_until_exists()
    if obj.version_id is None:
        obj.delete()
        obj.wait_until_not_exists()
        raise Exception("Bucket must have versioning enabled")
    new_version = obj.version_id

    # add undoer
    def undo():
        obj.delete(VersionId=new_version)
        obj.wait_until_not_exists(VersionId=new_version)
    undoers.append(undo)
