"""
Encoded Application AWS Deployment Helper

- SpotClient was removed in EPIC-ENCD-4716/ENCD-4688-remove-unused-code-from-deploy.

# Creating private AMIs

### Demos
    1. Create demo ami instance to build demo ami image
        $ bin/deploy --name encdbuildami-demo --build-ami
    2. Watch the logs of both machines, wait till deployment finishes. 
    3. Create the demo ami image from the instance using the commands printed in the console.
        Example create ami command
            $ python ./cloud-config/create-ami.py $username demo $encd_instance_id
        Terminate the instance when ami image is built
    4. Add the ami-id to the ami_map['demo'] below, commit and push the code
    5. Then create a test demo
        $ bin/deploy -n test-encdami-demo

### ES wait nodes
    1. Create es wait node and head for ami instance to build ami images
        $ bin/deploy --cluster-name encdbuildami-es-wait --es-wait --build-ami
    2. Watch the logs of both machines, wait till deployment finishes.
    3. Create the es data and head node ami image from the instance using the commands 
        printed in the console.

        Examples:
            $ python ./cloud-config/create-ami.py $username es-wait-node $encd_instance_id
            $ python ./cloud-config/create-ami.py $username es-wait-head $encd_instance_id
        Terminate the instances when ami image is built

    4. Add the ami-id to the ami_map['es-wait-node-cluster'] and
        ami_map['es-wait-head-cluster'] below, commit and push the code.
    5. Then create a test demo
        $ bin/deploy --cluster-name test-encdami-eswait --es-wait


### Frontend
    1. Create frontend ami instance to build fronend ami image
        $ bin/deploy --cluster-name encdbuildami-frontend --build-ami
    2. Watch the logs of both machines, wait till deployment finishes.
    3. Create the frontend ami image from the instance using the command
        printed in the console.

        Example:
        $ python ./cloud-config/create-ami.py $username frontend $encd_instance_id
        Terminate the instance when ami image is built
    
    4. Add the ami-id to the ami_map['fe-cluster'] below, commit and push the code.
    5. Then create a test frontend
        $ bin/deploy --cluster-name test-encdami-eswait --es-ip $es_head_ip



Ex) Build a new ami and deploy a demo
1. Demo: the --build-ami argument sets the aws image to base ubbuntu 18
    $ bin/deploy encd-demo-ami --build-ami -n
    # ssh on and watch cloud-init-output.log for errors.
    # Once completed, and the machine rebooted, contintue to next step.
2. Go to aws console and create an image from the instance
3. Once completed,
    * terminate the ami ec2 instance
    * create tags for the ami image, with started-by your-name, desc like buildtype and date
    * copy the the-image-ami-id to use to build a demo instance
3. Create a demo with the-image-ami-id, ex) ami-03d883df2ca6cbaf9
    $ bin/deploy -n encd-demo-test --use-prebuilt-config 20200129-u18-demo --image-id ami-03d883df2ca6cbaf9
    # QA the demo, as a PR that updates the AMI in the deploy.py

Ex) How to use this script to build a new config files, like the Ubuntu 18/Python 3.7 update
1. Copy a demo prebuilt yaml in encoded/cloud-config/prebuilt-config-yamls
    $ cp 20190923-pg11-demo.yml 20191112-pg11-u18-demo.yml
2. Deploy use the new prebuilt yaml from encoded/
    $ bin/deploy --use-prebuilt-config 20191112-pg11-u18-demo
3. Update the prebuilt yaml by hand with necessary changes.
4. Repeat 2. and 3. until the update is complete.
5. Make a new template in encoded/cloud-config/config-build-files/
    $ cp pg11-demo.yml u18-demo.yml
6. Create a new set of files in encoded/cloud-config/config-build-files/cc-parts
    to be used in u18-demo.yml template.  Examine older templates to see how.
7. Diff the compiled yml with the manual yml.  Fix any differences.
8. Save the compiled yml to prebuilt using today's date
    $ bin/deploy --save-config-name 20200129
9. Remove the manualy prebuilt, we'll keep the compiled version
10. Deploy the new prebuilt as in step two.
11. Make templates in encoded/cloud-config/config-build-files/ for es nodes and frontend.
    Try to reused the demo cc-parts is possible.  Make new ones for es or frontend if needed.


"""
import argparse
import getpass
import io
import re
import subprocess
import sys
import copy
from time import sleep

from difflib import Differ
from os.path import expanduser

import boto3


def _nameify(in_str):
    name = ''.join(
        c if c.isalnum() else '-'
        for c in in_str.lower()
    ).strip('-')
    return re.subn(r'\-+', '-', name)[0]


def _short_name(long_name):
    """
    Returns a short name for the branch name if found
    """
    if not long_name:
        return None
    regexes = [
        '(?:encd|sno)-[0-9]+',  # Demos
        '^v[0-9]+rc[0-9]+',     # RCs
        '^v[0-9]+x[0-9]+',      # Prod, Test
    ]
    result = long_name
    for regex_str in regexes:
        res = re.findall(regex_str, long_name, re.IGNORECASE)
        if res:
            result = res[0]
            break
    return result[:9].lower()


def _tag_ec2_instance(instance, tag_data, elasticsearch, cluster_name):
    tags = [
        {'Key': 'Name', 'Value': tag_data['name']},
        {'Key': 'branch', 'Value': tag_data['branch']},
        {'Key': 'commit', 'Value': tag_data['commit']},
        {'Key': 'started_by', 'Value': tag_data['username']},
    ]
    if elasticsearch:
        tags.append({'Key': 'elasticsearch', 'Value': 'yes'})
        # This if for integration with nagios server.
        # Only used on production.
        tags.append({'Key': 'Role', 'Value': 'data'})
    if cluster_name is not None:
        tags.append({'Key': 'ec_cluster_name', 'Value': cluster_name})
    instance.create_tags(Tags=tags)
    return instance


def _read_file_as_utf8(config_file):
    with io.open(config_file, 'r', encoding='utf8') as file_handler:
        return file_handler.read()


def _write_str_to_file(filepath, str_data):
    with io.open(filepath, 'w') as file_handler:
        return file_handler.write(str_data)


def _read_ssh_key(identity_file):
    ssh_keygen_args = ['ssh-keygen', '-l', '-f', identity_file]
    finger_id = subprocess.check_output(
        ssh_keygen_args
    ).decode('utf-8').strip()
    if finger_id:
        with open(identity_file, 'r') as key_file:
            ssh_pub_key = key_file.readline().strip()
            return ssh_pub_key
    return None


def _get_bdm(main_args):
    return [
        {
            'DeviceName': '/dev/sda1',
            'Ebs': {
                'VolumeSize': int(main_args.volume_size),
                'VolumeType': 'gp2',
                'DeleteOnTermination': True
            }
        },
        {
            'DeviceName': '/dev/sdb',
            'NoDevice': "",
        },
        {
            'DeviceName': '/dev/sdc',
            'NoDevice': "",
        },
    ]


def _get_user_data(config_yaml, data_insert, main_args):
    ssh_pub_key = _read_ssh_key(main_args.identity_file)
    if not ssh_pub_key:
        print(
            "WARNING: User is not authorized with ssh access to "
            "new instance because they have no ssh key"
        )
    data_insert['LOCAL_SSH_KEY'] = ssh_pub_key
    # aws s3 authorized_keys folder
    auth_base = 's3://encoded-conf-prod/ssh-keys'
    auth_type = 'prod'
    if main_args.profile_name != 'production':
        auth_type = 'demo'
    auth_keys_dir = '{auth_base}/{auth_type}-authorized_keys'.format(
        auth_base=auth_base,
        auth_type=auth_type,
    )
    data_insert['S3_AUTH_KEYS'] = auth_keys_dir
    user_data = config_yaml % data_insert
    return user_data


def _get_commit_sha_for_branch(branch_name):
    return subprocess.check_output(
        ['git', 'rev-parse', '--short', branch_name]
    ).decode('utf-8').strip()


def _get_instances_tag_data(main_args):
    instances_tag_data = {
        'branch': main_args.branch,
        'commit': None,
        'short_name': _short_name(main_args.name),
        'name': main_args.name,
        'username': None,
    }
    instances_tag_data['commit'] = _get_commit_sha_for_branch(instances_tag_data['branch'])
    # check if commit is a tag first then branch
    is_tag = False
    tag_output = subprocess.check_output(
        ['git', 'tag', '--contains', instances_tag_data['commit']]
    ).strip().decode()
    if tag_output:
        if tag_output == main_args.branch:
            is_tag = True
    is_branch = False
    git_cmd = ['git', 'branch', '-r', '--contains', instances_tag_data['commit']]
    if subprocess.check_output(git_cmd).strip():
        is_branch = True
    if not is_tag and not is_branch:
        print("Commit %r not in origin. Did you git push?" % instances_tag_data['commit'])
        sys.exit(1)
    instances_tag_data['username'] = getpass.getuser()
    if instances_tag_data['name'] is None:
        instances_tag_data['short_name'] = _short_name(instances_tag_data['branch'])
        instances_tag_data['name'] = _nameify(
            '%s-%s-%s' % (
                instances_tag_data['short_name'],
                instances_tag_data['commit'],
                instances_tag_data['username'],
            )
        )
        if main_args.es_wait or main_args.es_elect:
            instances_tag_data['name'] = 'elasticsearch-' + instances_tag_data['name']
    return instances_tag_data, is_tag


def _get_ec2_client(main_args, instances_tag_data):
    session = boto3.Session(region_name='us-west-2', profile_name=main_args.profile_name)
    ec2 = session.resource('ec2')
    name_to_check = instances_tag_data['name']
    if main_args.node_name:
        if main_args.cluster_size != 1:
            print('--node-name can only be used --cluster-size 1')
            return None
        name_to_check = main_args.node_name
    if any(ec2.instances.filter(
            Filters=[
                {'Name': 'tag:Name', 'Values': [name_to_check]},
                {'Name': 'instance-state-name',
                 'Values': ['pending', 'running', 'stopping', 'stopped']},
            ])):
        print('An instance already exists with name: %s' % name_to_check)
        return None
    return ec2


def _get_run_args(main_args, instances_tag_data, config_yaml, is_tag=False):
    master_user_data = None
    git_remote = 'origin' if not is_tag else 'tags'
    data_insert = {
        'APP_WORKERS': 'notused',
        'BATCHUPGRADE_VARS': 'notused',
        'BUILD_TYPE': 'NONE',
        'COMMIT': instances_tag_data['commit'],
        'CC_DIR': '/home/ubuntu/encoded/cloud-config/deploy-run-scripts',
        'CLUSTER_NAME': 'NONE',
        'ES_IP': main_args.es_ip,
        'ES_PORT': main_args.es_port,
        'ES_OPT_FILENAME': 'notused',
        'FULL_BUILD': main_args.full_build,
        'GIT_BRANCH': main_args.branch,
        'GIT_REMOTE': git_remote,
        'GIT_REPO': main_args.git_repo,
        'HOME': '/srv/encoded',
        'INSTALL_TAG': 'encd-install',
        'JVM_GIGS': 'notused',
        'PG_VERSION': main_args.postgres_version,
        'PY3_PATH': '/usr/bin/python3.6',
        'REDIS_PORT': main_args.redis_port,
        'REGION_INDEX': str(main_args.region_indexer),
        'ROLE': main_args.role,
        'S3_AUTH_KEYS': 'addedlater',
        'WALE_S3_PREFIX': main_args.wale_s3_prefix,
    }
    if main_args.es_wait or main_args.es_elect:
        # Data node clusters
        count = main_args.cluster_size
        security_groups = ['elasticsearch-https']
        iam_role = main_args.iam_role_es
        es_opt = 'es-cluster-wait.yml' if main_args.es_wait else 'es-cluster-elect.yml'
        data_insert.update({
            'BUILD_TYPE': 'encd-es-build',
            'CLUSTER_NAME': main_args.cluster_name,
            'ES_OPT_FILENAME': es_opt,
            'JVM_GIGS': main_args.jvm_gigs,
        })
        user_data = _get_user_data(config_yaml, data_insert, main_args)
        # Additional head node
        if main_args.es_wait and main_args.node_name is None:
            master_data_insert = copy.copy(data_insert)
            master_data_insert.update({
                'ES_OPT_FILENAME': 'es-cluster-head.yml',
            })
            master_user_data = _get_user_data(
                config_yaml,
                master_data_insert,
                main_args,
            )
    else:
        # Single demo or Frontends
        security_groups = ['ssh-http-https']
        iam_role = main_args.iam_role
        count = 1
        data_insert.update({
            'APP_WORKERS': main_args.app_workers,
            'BATCHUPGRADE_VARS': ' '.join(main_args.batchupgrade_vars),
            'REGION_INDEX': str(main_args.region_indexer),
            'ROLE': main_args.role,
        })
        if main_args.cluster_name:
            data_insert.update({
                'BUILD_TYPE': 'encd-frontend-build',
                'CLUSTER_NAME': main_args.cluster_name,
                'REGION_INDEX': 'True',
            })
        else:
            data_insert.update({
                'BUILD_TYPE': 'encd-demo-build',
                'JVM_GIGS': main_args.jvm_gigs,
                'ES_OPT_FILENAME': 'es-demo.yml',
            })
        user_data = _get_user_data(config_yaml, data_insert, main_args)
    run_args = {
        'count': count,
        'iam_role': iam_role,
        'master_user_data': master_user_data,
        'user_data': user_data,
        'security_groups': security_groups,
        'key-pair-name': 'encoded-demos' if main_args.role != 'candidate' else 'encoded-prod'
    }
    if main_args.profile_name == 'production' and main_args.role != 'candidate':
        run_args['key-pair-name'] += '-prod'
    return run_args


def _wait_and_tag_instances(
        main_args,
        run_args,
        instances_tag_data,
        instances,
        cluster_master=False
):
    tmp_name = instances_tag_data['name']
    instances_tag_data['domain'] = 'instance'
    if main_args.profile_name == 'production':
        instances_tag_data['domain'] = 'production'
    ssh_host_name = None
    is_cluster_master = False
    is_cluster = False
    if (main_args.es_wait or main_args.es_elect) and run_args['count'] >= 1:
        if cluster_master and run_args['master_user_data']:
            is_cluster_master = True
        else:
            is_cluster = True
    # Wait for one instance to start running + a little more
    instances[0].wait_until_running()
    sleep(30)
    instances_info = {}
    for i, instance in enumerate(instances):
        info_type = 'unknown'
        # Reload to get new data
        instance.load()
        instances_tag_data['name'] = tmp_name
        instances_tag_data['id'] = instance.id
        instances_tag_data['url'] = 'None'
        if is_cluster_master:
            info_type = 'cluster_master'
            instances_tag_data['name'] = "{}master".format(tmp_name[0:-1])
        elif is_cluster:
            info_type = 'cluster_node_{}'.format(i)
            instances_tag_data['name'] = "{}-data{}".format(tmp_name, i)
        if main_args.node_name:
            # override default node name
            # This is to add a node to a preexisting cluster since there is a name check
            instances_tag_data['name'] = main_args.node_name
        url = None 
        if not is_cluster and not cluster_master:
            # Demos and frontends
            # - build type
            if main_args.cluster_name:
                info_type = 'frontend'
            else:
                info_type = 'demo'
            # - url for prod and demo
            if instances_tag_data['domain'] == 'production':
                url = 'http://%s.%s.encodedcc.org' % (instances_tag_data['name'], 'production')
            else:
                url = 'https://%s.%s.encodedcc.org' % (instances_tag_data['name'], 'demo')
        if url:
            instances_tag_data['url'] = url
        # Set Tags
        _tag_ec2_instance(
            instance, instances_tag_data,
            (main_args.es_wait or main_args.es_elect),
            main_args.cluster_name,
        )
        # Create return info
        instances_info[info_type] = {
            'instance_id_domain': "{}.{}.encodedcc.org".format(
                instance.id,
                instances_tag_data['domain'],
            ),
            'instance_id': instance.id,
            'public_dns': instance.public_dns_name,
            'private_ip': instance.private_ip_address,
            'name': instances_tag_data['name'],
            'url': url,
            'username': instances_tag_data['username'],
        }
    return instances_info


def _get_cloud_config_yaml(main_args):
    """
    This will return a config yaml file built from a template and template parts
    - There will still be run variables in the template.
    """
    # pylint: disable=too-many-locals, too-many-return-statements
    cluster_name = main_args.cluster_name
    conf_dir = main_args.conf_dir
    diff_configs = main_args.diff_configs
    es_elect = main_args.es_elect
    es_wait = main_args.es_wait
    postgres_version = main_args.postgres_version
    save_config_name = main_args.save_config_name
    use_prebuilt_config = main_args.use_prebuilt_config

    def _diff_configs(config_one, config_two):
        results = list(
            Differ().compare(
                config_one.splitlines(keepends=True),
                config_two.splitlines(keepends=True),
            )
        )
        is_clean = True
        for index, result in enumerate(results, 1):
            if not result[0] == ' ':
                print(index, result)
                is_clean = False
                break
        return is_clean

    def _get_prebuild_config_template():
        read_config_path = "{}/{}/{}.yml".format(
            conf_dir,
            'prebuilt-config-yamls',
            use_prebuilt_config
        )
        return _read_file_as_utf8(read_config_path)

    def _build_config_template(build_type):
        template_path = "{}/{}/{}.yml".format(conf_dir, 'config-build-files', build_type)
        built_config_template = _read_file_as_utf8(template_path)
        replace_vars = set(re.findall(r'\%\((.*)\)s', built_config_template))
        # Replace cc parts vars in template.  Run vars are in cc-parts.
        template_parts_dir = "{}/{}/{}".format(conf_dir, 'config-build-files', 'cc-parts')
        cc_parts_insert = {}
        for replace_var_filename in replace_vars:
            replace_var_path = "{}/{}.yml".format(
                template_parts_dir,
                replace_var_filename,
            )
            replace_var_data = _read_file_as_utf8(replace_var_path).strip()
            cc_parts_insert[replace_var_filename] = replace_var_data
        return built_config_template % cc_parts_insert

    # Incompatibile build arguments
    if postgres_version and postgres_version not in ['9.3', '11']:
        print("Error: postgres_version must be '9.3' or '11'")
        return None, None, None
    if (es_elect or es_wait) and not cluster_name:
        print('Error: --cluster-name required for --es-wait and --es-elect')
        return None, None, None
    if diff_configs and not use_prebuilt_config:
        print('Error: --diff-configs must have --use-prebuilt-config config to diff against')
        return None, None, None
    # Determine type of build from arguments
    # - es-nodes builds will overwrite the postgres version
    build_type = 'u18-demo'
    if es_elect or es_wait:
        build_type = 'u18-es-nodes'
    elif cluster_name:
        build_type = 'u18-frontend'
    # elif cluster_name:
    #     build_type = 'pg{}-frontend'.format(postgres_version.replace('.', ''))
    # else:
    #     build_type = 'pg{}-{}'.format(postgres_version.replace('.', ''), build_type)
    # Determine config build method
    if use_prebuilt_config and not diff_configs:
        # Read a prebuilt config file from local dir and use for deployment
        prebuilt_config_template = _get_prebuild_config_template()
        if prebuilt_config_template:
            return prebuilt_config_template, None, build_type
        return None, None, build_type
    # Build config from template using cc-parts
    config_template = _build_config_template(build_type)
    if diff_configs:
        # Read a prebuilt config file from local dir and use for diff
        prebuilt_config_template = _get_prebuild_config_template()
        print('Diffing')
        _diff_configs(config_template, prebuilt_config_template)
        print('Diff Done')
        return config_template, None, build_type
    if save_config_name:
        # Having write_file_path set will not deploy
        # After creating a new config rerun
        #  with use_prebuilt_config=subpath/config_name
        config_name = "{}-{}".format(save_config_name, build_type)
        write_file_path = "{}/{}/{}.yml".format(
            conf_dir,
            'prebuilt-config-yamls',
            config_name,
        )
        return config_template, write_file_path, build_type
    return config_template, None, build_type


def _write_config_to_file(build_config, build_path, build_type):
    print("    * Made       Prebuild: ${}".format(' '.join(sys.argv)))
    print("        # Wrote new config to %s" % build_path)
    deployment_args = []
    # Clean sys args of --save-config-name and parameter
    config_name = ''
    for index, arg in enumerate(sys.argv):
        if arg == '--save-config-name':
            config_name = sys.argv[index + 1]
            deployment_args.extend(sys.argv[index + 2:])
            break
        deployment_args.append(arg)
    deploy_cmd = ' '.join(deployment_args)
    prebuild = "--use-prebuilt-config {}-{}".format(config_name, build_type)
    print("    * Diff Build/Prebuild: ${} {} --diff-configs".format(deploy_cmd, prebuild))
    es_ip_arg = '--es-ip $HEADNODEIP' if build_type == 'frontend' else ''
    if es_ip_arg:
        deploy_cmd += ' ' + es_ip_arg
    print("    * Deploy     Prebuild: ${} {}".format(deploy_cmd, prebuild))
    print("    * Deploy        Build: ${}".format(deploy_cmd))
    _write_str_to_file(build_path, build_config)


def main():
    """Entry point for deployment"""
    main_args = _parse_args()
    build_config, build_path, build_type = _get_cloud_config_yaml(main_args)
    if main_args.diff_configs:
        # instances_tag_data, is_tag = _get_instances_tag_data(main_args)
        # run_args = _get_run_args(main_args, instances_tag_data, build_config)
        # print(run_args['user_data'])
        sys.exit(0)
    if not build_config or not build_type:
        print('# Failure: Could not determine configuration type')
        sys.exit(1)
    if build_path:
        _write_config_to_file(build_config, build_path, build_type)
        sys.exit(0)
    # Deploy Frontend, Demo, es elect cluster, or es wait data nodes
    print('\nDeploying %s' % build_type)
    print("$ {}".format(' '.join(sys.argv)))
    print('Waiting for instance(s) to start running')
    instances_tag_data, is_tag = _get_instances_tag_data(main_args)
    if instances_tag_data is None:
        sys.exit(10)
    ec2_client = _get_ec2_client(main_args, instances_tag_data)
    if ec2_client is None:
        sys.exit(20)
    run_args = _get_run_args(main_args, instances_tag_data, build_config, is_tag=is_tag)
    bdm = _get_bdm(main_args)
    # Create aws demo instance or frontend instance
    # OR instances for es_wait nodes, es_elect nodes depending on count
    instances = ec2_client.create_instances(
        ImageId=main_args.image_id,
        MinCount=run_args['count'],
        MaxCount=run_args['count'],
        InstanceType=main_args.instance_type,
        SecurityGroups=run_args['security_groups'],
        UserData=run_args['user_data'],
        BlockDeviceMappings=bdm,
        InstanceInitiatedShutdownBehavior='terminate',
        IamInstanceProfile={
            "Name": run_args['iam_role'],
        },
        Placement={
            'AvailabilityZone': main_args.availability_zone,
        },
        KeyName=run_args['key-pair-name'],
    )
    instances_info = _wait_and_tag_instances(main_args, run_args, instances_tag_data, instances)
    # Create aws es_wait frontend instance
    if main_args.es_wait and run_args.get('master_user_data'):
        instances = ec2_client.create_instances(
            ImageId=main_args.eshead_image_id,
            MinCount=1,
            MaxCount=1,
            InstanceType=main_args.eshead_instance_type,
            SecurityGroups=['ssh-http-https'],
            UserData=run_args['master_user_data'],
            BlockDeviceMappings=bdm,
            InstanceInitiatedShutdownBehavior='terminate',
            IamInstanceProfile={
                "Name": main_args.iam_role,
            },
            Placement={
                'AvailabilityZone': main_args.availability_zone,
            },
            KeyName=run_args['key-pair-name'],
        )
        instances_info.update(
            _wait_and_tag_instances(
                main_args,
                run_args,
                instances_tag_data,
                instances,
                cluster_master=True,
            )
        )
    # Displays deployment output
    print('')
    tail_cmd = " 'tail -f /var/log/cloud-init-output.log'"
    helper_vars = []
    if 'demo' in instances_info:
        instance_info = instances_info['demo']
        if main_args.build_ami:
            print('AMI Build: Demo deploying:', instance_info['name'])
            print('instance_id:', instance_info['instance_id'])
            print(
                'After it builds, create the ami: '
                "python ./cloud-config/create-ami.py {} demo {} --profile-name {}".format(
                    instances_tag_data['username'],
                    instance_info['instance_id'],
                    main_args.profile_name,
                )
            )
        else:
            print('Deploying Demo:', instance_info['url'])
            print(" ssh ubuntu@{}".format(instance_info['instance_id_domain']))
        print("ssh and tail:\n ssh ubuntu@{}{}".format(instance_info['public_dns'], tail_cmd))
    elif 'cluster_master' in instances_info and main_args.es_wait:
        instance_info = instances_info['cluster_master']
        if main_args.build_ami:
            print('AMI Build: Wait ES cluster deploying:', instance_info['name'])
            print('instance_id:', instance_info['instance_id'])
            arg_name = 'es-wait-head'
            if main_args.es_elect:
                arg_name = 'es-elect'
            print(
                'After it builds, create the ami: '
                "python ./cloud-config/create-ami.py {} {} {} --profile-name {}".format(
                    instances_tag_data['username'],
                    arg_name,
                    instance_info['instance_id'],
                    main_args.profile_name,
                )
            )
        else:
            print('Deploying Head ES Node:', instance_info['name'])
            print(" ssh ubuntu@{}".format(instance_info['instance_id_domain']))
            print(" --es-ip {}".format(instance_info['private_ip']))
        print('\nRun the following command to view es head deployment log.')
        print("ssh ubuntu@{}{}".format(instance_info['public_dns'], tail_cmd))
        print('')
        helper_vars.append("datam='{}'".format(instance_info['instance_id']))
        for index in range(main_args.cluster_size):
            str_index = str(index)
            key_name = 'cluster_node_' + str_index
            node_info = instances_info[key_name]
            helper_vars.append("data{}='{}'  # {}".format(index, node_info['instance_id'], key_name))
            if index == 0:
                if main_args.build_ami and main_args.es_wait:
                    print(
                        'After it builds, create the ami: '
                        "python ./cloud-config/create-ami.py {} es-wait-node {} --profile-name {}".format(
                            instances_tag_data['username'],
                            node_info['instance_id'],
                            main_args.profile_name,
                        )
                    )
                print('Run the following command to view this es node deployment log.')
                print("ssh ubuntu@{}{}".format(node_info['public_dns'], tail_cmd))
            else:
                print("ES node{} ssh:\n ssh ubuntu@{}".format(index, node_info['public_dns']))
    elif 'frontend' in instances_info:
        instance_info = instances_info['frontend']
        if main_args.build_ami:
            print('AMI Build: Frontend deploying:', instance_info['name'])
            print('instance_id:', instance_info['instance_id'])
            print(
                'After it builds, create the ami: '
                "python ./cloud-config/create-ami.py {} frontend {} --profile-name {}".format(
                    instances_tag_data['username'],
                    instance_info['instance_id'],
                    main_args.profile_name,
                )
            )
        else:
            print('Deploying Frontend:', instance_info['url'])
            print(" ssh ubuntu@{}".format(instance_info['instance_id_domain']))
        print('\n\nRun the following command to view the deployment log.')
        print("ssh ubuntu@{}{}".format(instance_info['public_dns'], tail_cmd))
        helper_vars.append("frontend='{}'".format(instance_info['instance_id']))
    else:
        print('Warning: Unknown instance info')
        print(instances_info)
    if main_args.role == 'candidate' or main_args.build_ami:
        print('')
        # helps vars for release and building amis
        for helper_var in helper_vars:
            print(helper_var)


def _parse_args():
    # pylint: disable=too-many-branches, too-many-statements

    def check_volume_size(value):
        allowed_values = ['120', '200', '500']
        if not value.isdigit() or value not in allowed_values:
            raise argparse.ArgumentTypeError(
                "%s' is not in [%s]." % (
                    str(value),
                    ', '.join(allowed_values),
                )
            )
        return value

    def hostname(value):
        if value != _nameify(value):
            raise argparse.ArgumentTypeError(
                "%r is an invalid hostname, only [a-z0-9] and hyphen allowed." % value)
        return value

    parser = argparse.ArgumentParser(
        description="Deploy ENCODE on AWS",
    )
    parser.add_argument('-b', '--branch', default=None, help="Git branch or tag")
    parser.add_argument('-n', '--name', default=None, type=hostname, help="Instance name")
    parser.add_argument('--candidate', action='store_true', help="Prod candidate Flag")
    parser.add_argument('--release-candidate', action='store_true', help="RC Flag")
    parser.add_argument(
        '--test',
        action='store_const',
        default='demo',
        const='test',
        dest='role',
        help="Set role"
    )
    parser.add_argument(
        '--git-repo',
        default='https://github.com/ENCODE-DCC/encoded.git',
        help="Git repo to checkout branches: https://github.com/{user|org}/{repo}.git"
    )

    # User Data Yamls
    parser.add_argument('--app-workers', default='6', help="Apache config app workers")
    parser.add_argument(
        '--conf-dir',
        default='./cloud-config',
        help="Location of cloud build config"
    )
    parser.add_argument(
        '--diff-configs',
        action='store_true',
        help="Diff new build config against prebuilt."
    )
    parser.add_argument(
        '--save-config-name',
        default=None,
        help=(
            "Output cloud config to file. "
            "The type of config will be determined from args. "
            "Ex) 20190920"
        )
    )
    parser.add_argument('--use-prebuilt-config', default=None, help="Use prebuilt config file")
    parser.add_argument(
        '--region-indexer',
        default=None,
        help="Set region indexer to 'yes' or 'no'.  None is 'yes' for everything but demos."
    )
    parser.add_argument(
        '-i',
        '--identity-file',
        default="{}/.ssh/id_rsa.pub".format(expanduser("~")),
        help="ssh identity file path"
    )
    parser.add_argument(
        '--batchupgrade-vars',
        nargs=4,
        default=['1000', '1', '16', '1'],
        help=(
            "Set batchupgrade vars for demo only "
            "Ex) --batchupgrade-vars 1000 1 8 1 "
            "Where the args are batchsize, chunksize, processes, and maxtasksperchild"
        )
    )

    # Cluster
    parser.add_argument(
        '--es-elect',
        action='store_true',
        help="Create es nodes electing head node."
    )
    parser.add_argument('--es-wait', action='store_true', help="Create es nodes and head node.")
    parser.add_argument('--cluster-name', default=None, type=hostname, help="Name of the cluster")
    parser.add_argument('--cluster-size', default=5, type=int, help="Elasticsearch cluster size")
    parser.add_argument('--es-ip', default='localhost', help="ES Master ip address")
    parser.add_argument('--es-port', default='9201', help="ES Master ip port")
    parser.add_argument(
        '--node-name',
        default=None,
        type=hostname,
        help="Name of single node to add to already existing cluster"
    )
    parser.add_argument('--jvm-gigs', default='8', help="JVM Xms and Xmx gigs")

    # Database
    parser.add_argument('--postgres-version', default='11', help="Postegres version. '9.3' or '11'")
    parser.add_argument('--redis-ip', default='localhost', help="Redis IP.")
    parser.add_argument('--redis-port', default=6379, help="Redis Port.")
    parser.add_argument('--wale-s3-prefix', default='s3://encoded-backups-prod/production-pg11')

    # AWS
    parser.add_argument('--profile-name', default='default', help="AWS creds profile")
    parser.add_argument('--iam-role', default='encoded-instance', help="Frontend AWS iam role")
    parser.add_argument('--iam-role-es', default='elasticsearch-instance', help="ES AWS iam role")
    parser.add_argument(
        '--build-ami',
        action='store_true',
        help='Flag to indicate building for ami'
    )
    parser.add_argument(
        '--full-build',
        action='store_true',
        help='Flag to indicate building without an ami'
    )
    parser.add_argument(
        '--image-id',
        help=('Demo, Frontend, and es data node override default image ami')
    )
    parser.add_argument(
        '--eshead-image-id',
        help=('ES head node override default image ami')
    )
    parser.add_argument(
        '--availability-zone',
        default='us-west-2a',
        help="Set EC2 availabilty zone"
    )
    parser.add_argument(
        '--instance-type',
        help=('Demo, Frontend, and es data node override default image ami')
    )
    parser.add_argument(
        '--eshead-instance-type',
        help=('ES head node override default image ami')
    )
    parser.add_argument(
        '--volume-size',
        default=200,
        type=check_volume_size,
        help="Size of disk. Allowed values 120, 200, and 500"
    )
    args = parser.parse_args()
    # Set AMI per build type
    ami_map = {
        # AWS Launch wizard: ubuntu/images/hvm-ssd/ubuntu-bionic-18.04-amd64-server-20200112
        'default': 'ami-0d1cd67c26f5fca19',

        # Private AMIs: Add comments to each build

        # encdami-demo build on 2020-04-02 19:47:53.548416: encdami-demo-2020-04-02_194753
        'demo': 'ami-0483adb94a046470c',
        # encdami-es-wait-head build on 2020-03-31 20:13:17.094941: encdami-es-wait-head-2020-03-31_201317
        'es-wait-head': 'ami-03e019cdd3cc178a0',
        # encdami-es-wait-node build on 2020-03-31 20:08:41.739802: encdami-es-wait-node-2020-03-31_200841
        'es-wait-node': 'ami-077951301740d5be6',
        #  ES elect builds were not bulit since we rarely use them
        'es-elect-head': None,
        'es-elect-node': None,
        # encdami-frontend build on 2020-04-02 19:51:22.186528: encdami-frontend-2020-04-02_195122
        'frontend': 'ami-01e6c9e8a88583551',

        # Production Private AMIs: Add comments to each build

        # encdami-es-wait-head build on 2020-03-31 20:20:04.987640: encdami-es-wait-head-2020-03-31_202004
        'es-wait-head-prod': 'ami-0f2c2547107497579',
        # encdami-es-wait-node build on 2020-03-31 20:21:11.386147: encdami-es-wait-node-2020-03-31_202111
        'es-wait-node-prod': 'ami-09875dbadceee1dad',
        #  ES elect builds were not bulit since we rarely use them
        'es-elect-head-prod': None,
        'es-elect-node-prod': None,
        # encdami-frontend build on 2020-03-31 20:40:37.969622: encdami-frontend-2020-03-31_204037
        'frontend-prod': 'ami-07a066a69e1fd3f4c',
    }
    if not args.image_id:
        # Select ami by build type.  
        if args.build_ami:
            # Building new amis or making full builds from scratch
            # should start from base ubutnu image
            args.image_id = ami_map['default']
            args.eshead_image_id = ami_map['default']
            # We only need one es node to make an ami
            args.cluster_size = 1
        elif args.full_build:
            # Full builds from scratch
            # should start from base ubutnu image
            args.image_id = ami_map['default']
            args.eshead_image_id = ami_map['default']
        elif args.cluster_name:
            # Cluster builds have three prebuilt priviate amis
            if args.es_wait:
                if args.profile_name == 'production':
                    args.eshead_image_id = ami_map['es-wait-head-prod']
                    args.image_id = ami_map['es-wait-node-prod']
                else:
                    args.eshead_image_id = ami_map['es-wait-head']
                    args.image_id = ami_map['es-wait-node']
            elif args.es_elect and args.profile_name != 'production':
                if args.profile_name == 'production':
                    args.eshead_image_id = ami_map['es-elect-head-prod']
                    args.image_id = ami_map['es-elect-node-prod']
                else:
                    args.eshead_image_id = ami_map['es-elect-head']
                    args.image_id = ami_map['es-elect-node']
            else:
                if args.profile_name == 'production':
                    args.image_id = ami_map['frontend-prod']
                else:
                    args.image_id = ami_map['frontend']
        else:
            args.image_id = ami_map['demo']
    else:
        args.image_id = ami_map['default']
    # Aws instance size.  If instance type is not specified, choose based on build type
    if not args.instance_type:
        if args.es_elect or args.es_wait:
            # datanode
            args.instance_type = 'm5.xlarge'
            # Head node
            args.eshead_instance_type = 'm5.xlarge'
        else:
            # frontend
            args.instance_type = 'c5.9xlarge'
    # Check cluster name overrides name
    if args.cluster_name:
        cluster_tag = '-cluster'
        args.name = args.cluster_name.replace(cluster_tag, '')
        args.cluster_name = args.name + cluster_tag
        # adding a single node to a pre existing cluster
        if args.node_name and args.cluster_size != 1:
            raise ValueError(
                'Adding a node to a preexisting cluster. '
                '--cluster-size must be 1.'
            )
        # Elect clusters must have size of 4 or 5 due to
        # hard coded discovery size in es-cluster-elect.yml
        if (
                args.node_name is None and args.es_elect and (
                    args.cluster_size < 4 or args.cluster_size > 5
                )
        ):
            raise ValueError(
                '--es-elect cluster must have a size of 4 or 5 '
                'since election discovery is hard coded to 3 '
                'in es-cluster-elect.yml'
            )
    if args.es_wait and args.es_elect:
        raise ValueError('--es-wait and --es-elect cannot be used in the same command')
    # Set Role
    # - 'demo' role is default for making single or clustered
    # applications for feature building.
    # - '--test' will set role to test
    # - 'rc' role is for Release-Candidate QA testing and
    # is the same as 'demo' except batchupgrade will be skipped during deployment.
    # This better mimics production but require a command be run after deployment.
    # - 'candidate' role is for production release that potentially can
    # connect to produciton data.
    if not args.role == 'test':
        if args.release_candidate:
            args.role = 'rc'
            args.candidate = False
        elif args.candidate:
            args.role = 'candidate'
    # region_indexer is default True for everything but demos
    if args.region_indexer is not None:
        if args.region_indexer[0].lower() == 'y':
            args.region_indexer = True
        else:
            args.region_indexer = False
    elif args.role == 'demo':
        args.region_indexer = False
    else:
        args.region_indexer = True
    # Add branch arg
    if not args.branch:
        args.branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
        ).decode('utf-8').strip()
    return args


if __name__ == '__main__':
    main()
