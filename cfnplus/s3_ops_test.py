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

import cStringIO
import unittest
import boto3
import botocore
import s3_ops

AWS_REGION = 'us-west-2'

class S3OpsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._bucket = boto3.resource('s3', region_name=AWS_REGION).\
            Bucket('niara-s3ops-test')
        cls._bucket.create(
            CreateBucketConfiguration={'LocationConstraint': AWS_REGION}
        )
        cls._bucket.wait_until_exists()
        cls._bucket.Versioning().enable()

    @classmethod
    def tearDownClass(cls):
        cls._bucket.delete()
        cls._bucket.wait_until_not_exists()

    def tearDown(self):
        for obj in self._bucket.objects.all():
            self._delete_object(obj.key)

    def _delete_object(self, key):
        while True:
            try:
                obj = self._bucket.Object(key)
                if obj.version_id is None:
                    obj.delete()
                    obj.wait_until_not_exists()
                else:
                    obj.delete(VersionId=obj.version_id)
                    obj.wait_until_not_exists(VersionId=obj.version_id)
            except:
                return

    def assertObjectExists(self, key, contents):
        try:
            resp = self._bucket.Object(key).get()
        except:
            self.fail("No object with key \"{}\"".format(key))
            return
        actual_contents = resp['Body'].read()
        self.assertEqual(contents, actual_contents)

    def assertObjectDoesNotExist(self, key):
        obj = self._bucket.Object(key)
        self.assertRaises(botocore.exceptions.ClientError, obj.get)

    def assertDirObjectExists(self, key):
        files = self._bucket.objects.filter(Prefix=key)
        self.assertGreater(len(list(files)), 0)

    def assertDirObjectDoesNotExist(self, key):
        files = self._bucket.objects.filter(Prefix=key)
        self.assertEqual(0, len(list(files)))

    def testUploadFile_noExisting_success(self):
        #
        # Set up
        #

        # make local file
        file_contents = "Hello world"
        buf = cStringIO.StringIO()
        buf.write(file_contents)

        # make S3 key
        key = 'my_file'

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.upload_file(buf, self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in committers:
            f()

        #
        # Test
        #

        # check that object exists
        self.assertObjectExists(key, file_contents)

    def testUploadFile_noExisting_failure(self):
        #
        # Set up
        #

        # make local file
        file_contents = "Hello world"
        buf = cStringIO.StringIO()
        buf.write(file_contents)

        # make S3 key
        key = 'my_file'

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.upload_file(buf, self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in undoers:
            f()

        #
        # Test
        #

        # check that object doesn't exist
        self.assertObjectDoesNotExist(key)

    def testUploadFile_existing_success(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_file'

        # make existing S3 file
        s3_contents_old = "Hello world"
        obj = self._bucket.put_object(Body=s3_contents_old, Key=key)
        obj.wait_until_exists()

        # make local file
        file_contents_new = s3_contents_old + " again"
        buf = cStringIO.StringIO()
        buf.write(file_contents_new)

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.upload_file(buf, self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in committers:
            f()

        #
        # Test
        #

        # check that object exists
        self.assertObjectExists(key, file_contents_new)

    def testUploadFile_existing_failure(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_file'

        # make existing S3 file
        s3_contents_old = "Hello world"
        obj = self._bucket.put_object(Body=s3_contents_old, Key=key)
        obj.wait_until_exists()

        # make local file
        file_contents_new = s3_contents_old + " again"
        buf = cStringIO.StringIO()
        buf.write(file_contents_new)

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.upload_file(buf, self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in undoers:
            f()

        #
        # Test
        #

        # check that object exists
        self.assertObjectExists(key, s3_contents_old)

    def testDeleteObject_success(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_file'

        # make S3 object
        s3_contents = 'haaaiii!'
        obj = self._bucket.put_object(Key=key, Body=s3_contents)
        obj.wait_until_exists()
        self.assertObjectExists(key, s3_contents)

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.delete_object(self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in committers:
            f()

        #
        # Test
        #

        # check that object doesn't exist
        self.assertObjectDoesNotExist(key)

    def testDeleteObject_failure(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_file'

        # make S3 object
        s3_contents = 'haaaiii!'
        obj = self._bucket.put_object(Key=key, Body=s3_contents)
        obj.wait_until_exists()
        self.assertObjectExists(key, s3_contents)

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.delete_object(self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in undoers:
            f()

        #
        # Test
        #

        # check that object exists
        self.assertObjectExists(key, s3_contents)

    def testMakeDir_success(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_dir'

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.make_dir(self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in committers:
            f()

        #
        # Test
        #

        # check that dir exists
        self.assertDirObjectExists(key)

    def testMakeDir_failure(self):
        #
        # Set up
        #

        # make S3 key
        key = 'my_dir'

        #
        # Call
        #
        committers = []
        undoers = []
        s3_ops.make_dir(self._bucket, key, committers=committers, \
            undoers=undoers)
        for f in undoers:
            f()

        #
        # Test
        #

        # check that dir exists
        self.assertDirObjectDoesNotExist(key)

def main():
    print("WARNING: This test performs real AWS S3 operations.")
    while True:
        resp = raw_input("Continue? [y/N] ").lower()
        if resp == 'y':
            break
        elif resp == 'n':
            return

    suite = unittest.TestLoader().loadTestsFromTestCase(S3OpsTest)
    unittest.TextTestRunner(verbosity=2).run(suite)

if __name__ == '__main__':
    main()
