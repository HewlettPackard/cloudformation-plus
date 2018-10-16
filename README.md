# CloudFormation Plus

## Contents

- [Intro](#intro)
  - [Example](#example)
- [Installation](#installation)
- [Usage](#usage)
  - [Signature of `process_template`](#signature-of-process_template)
- [Note: Intrinsic functions](#note-intrinsic-functions)
- [Features](#features)
  - [Atomicity](#atomicity)
  - [S3 operations](#s3-operations)
    - [Making a directory](#making-a-directory)
    - [Uploading a file](#uploading-a-file)
    - [Syncing a directory](#syncing-a-directory)
  - [Making and updating Lambda functions](#making-and-updating-lambda-functions)
  - [Bootstrapping EC2 instances](#bootstrapping-ec2-instances)
  - [Including nested stacks](#including-nested-stacks)
  - [Using YAML anchors in templates](#using-yaml-anchors-in-templates)
  - [Setting a stack policy](#setting-a-stack-policy)

## Intro

This is a Python library that adds features to AWS CloudFormation that reduce the amount of code you must write in order to automate the deployment of non-trivial cloud-based systems.  Specifically, this library adds elements to the CloudFormation template language that perform tasks that otherwise would need to be done in your deploy script.

### Example

Suppose we want to use CloudFormation to make a database node and a Lambda function that implements an API endpoint.  We write a shell script that configures the database node (i.e., downloads and installs the database software) and a program that implements the Lambda function's logic.  We put both files in this directory structure:

```
|- my-api/
  |- bootstrap/
    |- db.sh
  |- lambda/
    |- api/
      |- api.py
```

Using CloudFormation Plus's extensions to the template language, we can make the template like this:

```
AWSTemplateFormatVersion: 2010-09-09

Metadata:
  Aruba::BeforeCreation:
    - S3Upload:
        LocalFile: bootstrap/db.sh
        S3Dest: s3://my-bucket/bootstrap/db.sh

Resources:
  Database:
    Type: 'AWS::EC2::Instance'
    Properties:
      AvailabilityZone: us-west-2a
      ImageId: ami-e251209a
      InstanceType: m5.large
      Aruba::BootstrapActions:
        Actions:
          - Path: s3://my-bucket/bootstrap/db.sh
        LogUri: s3://my-bucket/logs
        Timeout: PT5M
      IamInstanceProfile: {Ref: InstProf}

  ApiLambda:
    Type: 'AWS::Lambda::Function'
    Properties:
      Aruba::LambdaCode:
        LocalPath: lambda/api
        S3Dest: s3://my-bucket/lambda
      Environment:
        Variables:
          DB_HOST: {'Fn::Sub': 'Database.PublicDnsName'}
      Handler: api.handle
      Runtime: python2.7

  DatabaseRole:
    Type: 'AWS::IAM::Role'
    Properties:
      AssumeRolePolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Principal:
              Service:
                - ec2.amazonaws.com
            Action:
              - 'sts:AssumeRole'
      Policies:
        - PolicyName: DatabasePolicy
          PolicyDocument:
            Version: 2012-10-17
            Statement:
              - Effect: Allow
                Action: 's3:HeadBucket'
                Resource: '*'
              - Effect: Allow
                Action: 's3:ListBucket'
                Resource: 'arn:aws:s3:::my-bucket'
              - Effect: Allow
                Action:
                  - 's3:GetObject'
                  - 's3:PutObject'
                Resource: 'arn:aws:s3:::my-bucket/*'

  InstProf:
    Type: 'AWS::IAM::InstanceProfile'
    Properties:
      Roles:
        - Ref: DatabaseRole
```

This template would be saved at `my-api/template.yml`.

CloudFormation Plus helps in the following ways:

- In the `Metadata` section near the top, the `Aruba::BeforeCreation` element uploads `bootstrap/db.sh` to the S3 bucket `my-bucket` at key `bootstrap/db.sh`.
- In the `Database` resource, the `Aruba::BootstrapActions` property causes `db.sh` to be executed after the database node is made.  If `db.sh` fails, the whole stack deployment will fail.  `db.sh`'s output will be written to the S3 bucket `my-bucket`.
- In the `ApiLambda` resource, the `Aruba::LambdaCode` property bundles the local `lambda/api` directory into a Lambda deployment package, and then uploads it to the S3 bucket `my-bucket`.  It also sets the function to use that deployment package as its code (and when this template is used to update an existing stack, it ensures that the function uses the latest package).


## Installation

CloudFormation Plus works with Python 2 and 3.

1. Download the source package for one of <a href="https://github.com/HewlettPackard/cloudformation-plus/releases" target="_blank">the releases</a>.
1. Example the source package, and `cd` into the resulting directory.
1. Run `pip install .`

You can now use CloudFormation Plus in your scripts by importing `cfnplus`.

## Usage

The rest of this document describes the extensions to the template language.  This section describes how to process templates that use these extensions.

CloudFormation Plus is a Python library, and it is intended to be used with stacks that are made/updated by Python programs.  In other words, it is best if the creation/update of your stacks is automated with Python programs.

Let's use an example consisting of a single template named "my_website.yml".  We can write a Python program that uses boto3 to deploy and update this stack:

```
import time
import boto3
import botocore

_TEMPLATE_PATH = 'my_website.yml'
_STACK_NAME = 'MyWebsite'
_AWS_REGION = 'us-west-2'

def make_or_update_stack(cfn, template):
  ...

def main():
    # read template
    with open(_TEMPLATE_PATH) as f:
        template = f.read()

    # make/update stack
    make_or_update_stack(cfn, template)

if __name__ == '__main__':
  main()
```

(I omit the body of `make_or_update_stack` because it's quite verbose and not important for the current purpose.  If you'd like to see how it could be written, confer <a href="https://github.com/HewlettPackard/cloudformation-plus/blob/master/example/deploy.py#L47" target="_blank">this</a>.)

If we want to use CloudFormation Plus template language extensions in `my_website.yml`, we need to change this script thus:

```
import time
import boto3
import botocore
import cfnplus

_TEMPLATE_PATH = 'my_website.yml'
_STACK_NAME = 'MyWebsite'
_AWS_REGION = 'us-west-2'

def make_or_update_stack(cfn, template):
  ...

def main():
    # read template
    with open(_TEMPLATE_PATH) as f:
        template = f.read()

    # process language extensions
    with cfnplus.process_template(
        template,
        [],  # template params
        _AWS_REGION,
        _TEMPLATE_PATH,
        _STACK_NAME,
    ) as cfnp_result:

        # do actions that must be done before stack creation/update
        cfnp_result.do_before_creation()

        # make/update stack
        make_or_update_stack(cfn, template)

        # do actions that must be done after stack creation/update
        cfnp_result.do_after_creation()

if __name__ == '__main__':
  main()
```

Let's go over these changes.  All CloudFormation Plus features used in `my_website.yml` are processed by the call to `cfnplus.process_template`.  (The parameters for this function are described below.)  As you will learn when you read the sections below, some features generate template code, some features generate S3 actions that are to be done before stack creation/update, and some features generate S3 actions that are to be done after stack creation/update.  The return value of `cfnplus.process_template` contains the accumulated results of each feature in `my_website.yml`.  It is important to note that `cfnplus.process_template` itself does not perform any S3 actions &mdash; in fact, it has no side-effets.

We do the rest of the work in the body of the `with` statement.  The purpose of the `with` statement is to support atomicity; if an exception is thrown in the `do_before_creation` call or in any statement after this call and before the `do_after_creation` call, the effects of the actions done by the `do_before_creation` call will be rolled back &mdash; for example, objects added to S3 will be removed, objects removed from S3 will be restored.  Similarly, if an exception is thrown by the `do_after_creation` call, the effects of any actions done by this call will be rolled back &mdash; but the effects of the `do_before_creation` call will NOT be rolled back.

The most likely cause of exceptions will be problems with the original (non-transformed) template.  CloudFormation supports rollback of failed stack changes; with CloudFormation Plus, you now can roll back S3 changes as well.

### Signature of `process_template`

```
def process_template(template, template_params, aws_region, template_path=None, stack_name=None)
```

<table>
<thead>
<tr><th>Param</th><th>Type</th><th>Description</th></tr>
</thead>
<tfoot></tfoot>
<tbody>
<tr>
<td>template</td>
<td>str</td>
<td>The CloudFormation template to process (must be in
  YAML)</td>
</tr>
<tr>
<td>template_params</td>
<td>dict</td>
<td>A list of dicts of this form:
<pre><code>
{
    "ParameterKey": ...,
    "ParameterValue": ..., (optional)
    "UsePreviousValue": ... (optional)
}</code></pre>

If `UsePreviousValue` is `True` for any of them, then the `stack_name` parameter must be
  given and a stack with that name must exist.
</td>
</tr>

<tr>
<td>aws_region</td>
<td>str</td>
<td>The name of the AWS region in which the stack will be
  made</td>
</tr>

<tr>
<td>template_path</td>
<td>str</td>
<td>An absolute filesystem path pointing to
  the template.  This is needed only if the template has tags containing
  paths relative to the template's path.</td>
</tr>

<tr>
<td>stack_name</td>
<td>str</td>
<td>The name that the stack will have when it is
  made.  This is needed only if the template uses the <code>AWS::StackName</code>
  variable, or if <code>template_params</code> contains an item with <code>UsePreviousValue</code>
  set to <code>True</code>, or if <code>Aruba::StackPolicy</code> is used.</td>
</tr>

</tbody>
</table>


## Note: Intrinsic functions

Certain CloudFormation <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/intrinsic-function-reference.html" target="_blank">intrinsic functions</a> can be used with the features provided by this library. However, they can only be used to reference template parameters and values exported from other stacks.  In particular, they cannot be used to reference resources (or properties thereof) defined in the same template.

The following intrinsic functions are supported:
- `fn::ImportValue`
- `fn::Sub`
- `Ref`

## Features

### Atomicity

A great aspect of CloudFormation is that it is (usually) able to roll back resource changes when an error occurs.  This is also true of S3 operations performed by CloudFormation Plus.  Confer [above](#usage) to see how to use the CloudFormation Plus library to enable this.

### S3 operations

You can specify S3 operations to be done before or after a stack is made from your template.  For the former, add a list to your template's `Metadata` section with the label `Aruba::BeforeCreation`, and add your actions to that list.  For the latter, the list should have the label `Aruba::AfterCreation`.

For example:

```
AWSTemplateFormatVersion: 2010-09-09
Parameters:
  ...
Metadata:
  Aruba::BeforeCreation:
    - ...
    - ...
  Aruba::AfterCreation:
    - ...
    - ...
Resources:
  ...
```

The following subsections describe how to define actions.

*NOTE:* Versioning must be enabled on the bucket.  This is needed because it is used to undo S3 operations when an error occurs.

#### Making a directory

```
S3Mkdir: S3_DEST
```

This action makes a directory in an S3 bucket.

If a directory already exists at the destination, this action does nothing.

NOTE: This is done by adding a 0-byte object with the specified key (plus a '/' at the end if it doesn't end with one already).

##### Parameters

<dl>
<dt><code>S3_DEST</code></dt>
<dd>An "s3://BUCKET/KEY" URI at which a directory should be made</dd>
</dt>

#### Uploading a file

```
S3Upload:
  LocalFile: LOCAL_FILE
  S3Dest: S3_DEST
```

This action uploads a local file to an S3 bucket.

If a file already exists at the destination, this action overwrites it.

##### Parameters

<dl>
<dt><code>LOCAL_FILE</code></dt>
<dd>A local path to the file that should be uploaded.  If the path is relative,
it must be relative to the template file.</dd>

<dt><code>S3_DEST</code></dt>
<dd>An "s3://BUCKET/KEY" URI to which the file should be uploaded</dd>
</dl>

#### Syncing a directory

```
S3Sync:
  LocalDir: LOCAL_DIR
  S3Dest: S3_DEST
```

This action updates a directory in S3 with the contents of a local directory.  Files and directories in the local directory are uploaded to the S3 directory, and any files and directories in the S3 directory that are not in the local directory are deleted.

If nothing yet exists at the destination, a directory is created there.

##### Parameters

<dl>
<dt><code>LOCAL_DIR</code></dt>
<dd>A local path to the directory that should be synced.  If the path is relative,
it must be relative to the template file.</dd>

<dt><code>S3_DEST</code></dt>
<dd>The "s3://BUCKET/KEY" URI of the directory that should be synced.  At the end,
this directory will contain (directory or indirectly) all the files in the local
directory, and nothing else.</dd>
</dl>

### Making and updating Lambda functions

CloudFormation Plus can help you keep your Lambda functions up-to-date.  Use the following property in your <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-resource-lambda-function.html" target="_blank">`AWS::Lambda::Function`</a> resources:

```
Aruba::LambdaCode:
  LocalPath: LOCAL_PATH
  S3Dest: S3_DEST
```

*IMPORTANT:* This property should be used instead of the `Code` property.

This property does the following:
- Builds a Lambda deployment package containing the files in the directory at `LOCAL_PATH`, and uploads it to S3
- If the Lambda function already exists and any code in the directory at `LOCAL_PATH` has changed, updates the Lambda function to use the new code

#### Parameters

<dl>
<dt><code>LOCAL_PATH</code></dt>
<dd>A path to a directory containing code (and dependencies) for a Lambda function.  
If the path is relative, it must be relative to the template file.</dd>

<dt><code>S3_DEST</code></dt>
<dd>The "s3://BUCKET/KEY" URI of the directory to which the Lambda deployment
package should be uploaded</dd>
</dl>

#### Example

```
MyFunction:
  Type: 'AWS::Lambda::Function'
  Properties:
    Aruba::LambdaCode:
      LocalPath: lambda-funcs/my-func
      S3Dest: s3://my-bucket/lambda-code
    Handler: my_func.go
    Runtime: python2.7
    Timeout: 30
```

### Bootstrapping EC2 instances

CloudFormation does lets you <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/deploying.applications.html" target="_blank">bootstrap EC2 instances</a>, but it's a bit complicated and is missing some useful features.

Instead, use the following property in your <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-ec2-instance.html" target="_blank">EC2 instance definitions</a>:

```
Aruba::BootstrapActions:
  Actions:
    - Path: ACTION_PATH
      Args: ARG_LIST
    - ...
    - ...
  LogUri: LOG_URI
  Timeout: TIMEOUT
```

The property does the following:
- Runs each program specified in the `Actions` list on the instance
- Captures each action's output and uploads it to the S3 location given in `LogUri`
- Makes the stack wait for all the actions to finish running
- Makes the stack's status conditional on the status of all the actions

*IMPORTANT:* The action programs must be in S3, and this property does not put them there.  You can use the [S3 operations elements](#s3-operations) defined in this library to upload the action programs to S3.

*IMPORTANT:* The EC2 instance must be given an instance profile with a role that has permission to read the action programs in S3, and, if `LogUri` is used, it must also have permissions to write to the specified S3 location.

#### Parameters

<dl>
<dt><code>ACTION_PATH</code></dt>
<dd>An S3 path (starting with "s3://") pointing to the program that bootstraps the instance</dd>

<dt><code>ARG_LIST</code></dt>
<dd>A list of strings to pass as arguments to the bootstrap program</dd>

<dt><code>LOG_URI</code></dt>
<dd>(Optional) The "s3://BUCKET/KEY" URI of the directory in which to put the output of the
bootstrap program</dd>

<dt><code>TIMEOUT</code></dt>
<dd>The length of time that we should wait for the bootstrap program to run.
Must be in ISO8601 duration format.</dd>
</dl>

#### Example

```
Database:
  Type: 'AWS::EC2::Instance'
  Properties:
    AvailabilityZone: us-west-2a
    ImageId: ami-e251209a
    InstanceType: m5.large
    IamInstanceProfile: {Ref: InstProf}
    Aruba::BootstrapActions:
      Actions:
        - Path: s3://my-bucket/bootstrap/db.sh
      Timeout: PT5M

DatabaseRole:
  Type: 'AWS::IAM::Role'
  Properties:
    AssumeRolePolicyDocument:
      Version: 2012-10-17
      Statement:
        - Effect: Allow
          Principal:
            Service:
              - ec2.amazonaws.com
          Action:
            - 'sts:AssumeRole'
    Policies:
      - PolicyName: DatabasePolicy
        PolicyDocument:
          Version: 2012-10-17
          Statement:
            - Effect: Allow
              Action: 's3:HeadBucket'
              Resource: '*'
            - Effect: Allow
              Action: 's3:ListBucket'
              Resource: 'arn:aws:s3:::my-bucket'
            - Effect: Allow
              Action:
                - 's3:GetObject'
              Resource: 'arn:aws:s3:::my-bucket/*'

InstProf:
  Type: 'AWS::IAM::InstanceProfile'
  Properties:
    Roles:
      - Ref: DatabaseRole
```

### Including nested stacks

```
Type: Aruba::Stack
Properties:
  Template:
    LocalPath: LOCAL_PATH
    S3Dest: S3_DEST
  Parameters: PARAMETERS
```

This resource type will upload the template file to S3.  If the template file uses any of the features from this library, it will be processed accordingly.

#### Parameters

<dl>
<dt><code>LOCAL_PATH</code></dt>
<dd>A path to the nested stack's template file.  If the path is relative, it must be relative to the template file.</dd>

<dt><code>S3_DEST</code></dt>
<dd>The "s3://BUCKET/KEY" URI of the directory to which the file should be uploaded</dd>

<dt><code>PARAMETERS</code></dt>
<dd>Parameters to pass to the nested stack (cf. <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-stack-parameters.html" target="_blank">AWS CloudFormation Stack Parameters</a>)</dd>
</dl>

### Using YAML anchors in templates

In a YAML document, you can include the same node in multiple places using <a href="http://yaml.org/spec/1.2/spec.html#id2785586" target="_blank">anchors</a>.  This can be quite useful when you want to reduce the size of a YAML file.

Unfortunately, CloudFormation does not support YAML anchors.  However, when you process a template with this library, all the anchor references will be expanded in the modified template that you send to CloudFormation.  This applies to templates that you pass directly to this library as well as templates that are referenced in an `Aruba::Stack` resource.

### Setting a stack policy

You can set a stack's policy by adding the following to the template's `Metadata` section:

```
Aruba::StackPolicy: POLICY
```

#### Parameters

<dl>
<dt><code>POLICY</code></dt>
<dd>A stack policy &mdash; cf. <a href="https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/protect-stack-resources.html" target="_blank">the AWS documentation</a> for details on how to define a policy.
</dl>
