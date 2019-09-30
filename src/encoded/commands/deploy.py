"""
Encoded Application AWS Deployment Helper

- SpotClient was removed in EPIC-ENCD-4716/ENCD-4688-remove-unused-code-from-deploy.
"""
import argparse
import datetime
import getpass
import io
import re
import subprocess
import sys
import time

from base64 import b64encode
from difflib import Differ
from os.path import expanduser

import boto3


def nameify(in_str):
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


def tag_ec2_instance(instance, tag_data, elasticsearch, cluster_name):
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


def read_ssh_key(identity_file):
    ssh_keygen_args = ['ssh-keygen', '-l', '-f', identity_file]
    fingerprint = subprocess.check_output(
        ssh_keygen_args
    ).decode('utf-8').strip()
    if fingerprint:
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


def get_user_data(commit, config_yaml, data_insert, main_args):
    ssh_pub_key = read_ssh_key(main_args.identity_file)
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
    data_insert['REDIS_PORT'] = main_args.redis_port
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
    if not subprocess.check_output(
            ['git', 'branch', '-r', '--contains', instances_tag_data['commit']]
        ).strip():
        print("Commit %r not in origin. Did you git push?" % instances_tag_data['commit'])
        sys.exit(1)
    instances_tag_data['username'] = getpass.getuser()
    if instances_tag_data['name'] is None:
        instances_tag_data['short_name'] = _short_name(instances_tag_data['branch'])
        instances_tag_data['name'] = nameify(
            '%s-%s-%s' % (
                instances_tag_data['short_name'],
                instances_tag_data['commit'],
                instances_tag_data['username'],
            )
        )
        if main_args.elasticsearch:
            instances_tag_data['name'] = 'elasticsearch-' + instances_tag_data['name']
    return instances_tag_data


def _get_ec2_client(main_args, instances_tag_data):
    session = boto3.Session(region_name='us-west-2', profile_name=main_args.profile_name)
    ec2 = session.resource('ec2')
    if any(ec2.instances.filter(
            Filters=[
                {'Name': 'tag:Name', 'Values': [instances_tag_data['name']]},
                {'Name': 'instance-state-name',
                 'Values': ['pending', 'running', 'stopping', 'stopped']},
            ])):
        print('An instance already exists with name: %s' % instances_tag_data['name'])
        return None
    return ec2


def _get_run_args(main_args, instances_tag_data, config_yaml):
    master_user_data = None
    cc_dir='/home/ubuntu/encoded/cloud-config/deploy-run-scripts'
    if not main_args.elasticsearch:
        security_groups = ['ssh-http-https']
        iam_role = main_args.iam_role
        count = 1
        data_insert = {
            'BATCHUPGRADE_VARS': ' '.join(main_args.batchupgrade_vars),
            'CC_DIR': cc_dir,
            'COMMIT': instances_tag_data['commit'],
            'CLUSTER_NAME': 'NONE',
            'ES_IP': main_args.es_ip,
            'ES_PORT': main_args.es_port,
            'GIT_BRANCH': main_args.branch,
            'GIT_REPO': main_args.git_repo,
            'REDIS_IP': main_args.redis_ip,
            'REDIS_PORT': main_args.redis_port,
            'REGION_INDEX': 'False',
            'ROLE': main_args.role,
            'WALE_S3_PREFIX': main_args.wale_s3_prefix,
        }
        if main_args.cluster_name:
            data_insert.update({
                'CLUSTER_NAME': main_args.cluster_name,
                'REGION_INDEX': 'True',
            })
        else:
            data_insert.update({
                'JVM_GIGS': main_args.jvm_gigs,
            })
        if main_args.set_region_index_to:
            data_insert.update({
                'REGION_INDEX': main_args.set_region_index_to,
            })
        user_data = get_user_data(instances_tag_data['commit'], config_yaml, data_insert, main_args)
    else:
        if not main_args.cluster_name:
            print("Cluster must have a name")
            sys.exit(1)
        count = int(main_args.cluster_size)
        security_groups = ['elasticsearch-https']
        iam_role = main_args.iam_role_es
        data_insert = {
            'CC_DIR': cc_dir,
            'CLUSTER_NAME': main_args.cluster_name,
            'ES_OPT_FILENAME': 'es-cluster-elect.yml',
            'GIT_BRANCH': main_args.branch,
            'GIT_REPO': main_args.git_repo,
            'JVM_GIGS': main_args.jvm_gigs,
        }
        if main_args.single_data_master:
            data_insert.update({
                'ES_OPT_FILENAME': 'es-cluster-wait.yml',
            })
        user_data = get_user_data(instances_tag_data['commit'], config_yaml, data_insert, main_args)
        if main_args.single_data_master:
            master_data_insert = {
                'BATCHUPGRADE_VARS': ' '.join(main_args.batchupgrade_vars),
                'CC_DIR': cc_dir,
                'CLUSTER_NAME': main_args.cluster_name,
                'ES_OPT_FILENAME': 'es-cluster-head.yml',
                'GIT_BRANCH': main_args.branch,
                'GIT_REPO': main_args.git_repo,
                'JVM_GIGS': main_args.jvm_gigs,
            }
            master_user_data = get_user_data(
                instances_tag_data['commit'],
                config_yaml,
                master_data_insert,
                main_args,
            )
    run_args = {
        'count': count,
        'iam_role': iam_role,
        'user_data': user_data,
        'security_groups': security_groups,
    }
    if master_user_data:
        run_args['master_user_data'] = master_user_data
    return run_args


def _get_instance_output(
        instances_tag_data,
        attach_dm=False,
        given_name=None,
        is_production=False,
):
    hostname = '{}.{}.encodedcc.org'.format(
        instances_tag_data['id'],
        instances_tag_data['domain'],
    )
    name_to_use = given_name if given_name else instances_tag_data['short_name']
    suffix = '-dm' if attach_dm else ''
    skip_https_ssh = False
    if suffix == '-dm':
        name_to_use = name_to_use.replace('-data', 'd')
        skip_https_ssh = True
    else:
        name_to_use = name_to_use.replace('-master', 'm')
    domain = 'demo'
    if instances_tag_data['domain'] == 'production':
        domain = 'production'
    output_list = [
        'Host %s.*' % name_to_use,
        '  Hostname %s' % hostname,
    ]
    if not skip_https_ssh:
        output_list.append('  # https://%s.%s.encodedcc.org' % (instances_tag_data['name'], domain))
        output_list.append('  # ssh ubuntu@%s' % hostname)
    return output_list


def _wait_and_tag_instances(main_args, run_args, instances_tag_data, instances, cluster_master=False):
    tmp_name = instances_tag_data['name']
    instances_tag_data['domain'] = 'production' if main_args.profile_name == 'production' else 'instance'
    output_list = []
    is_cluster_master = False
    is_cluster = False
    if main_args.elasticsearch and run_args['count'] > 1:
        if cluster_master and run_args['master_user_data']:
            is_cluster_master = True
        else:
            is_cluster = True
    created_cluster_master = False
    for i, instance in enumerate(instances):
        instances_tag_data['name'] = tmp_name
        instances_tag_data['id'] = instance.id
        if is_cluster_master:
            # Hack: current tmp_name was the last data cluster, so remove '4'
            instances_tag_data['name'] = "{}{}".format(tmp_name[0:-1], 'master')
        elif is_cluster:
            instances_tag_data['name'] = "{}{}".format(tmp_name, i)
        if is_cluster_master or (is_cluster and not created_cluster_master):
            created_cluster_master = True
            output_list.extend(_get_instance_output(
                instances_tag_data,
                attach_dm=True,
                given_name=main_args.name,
            ))
        if is_cluster:
            output_list.append('  # Data Node %d: %s' % (i, instance.id))
        elif not is_cluster:
            output_list.extend(
                _get_instance_output(
                    instances_tag_data,
                    given_name=main_args.name,
                )
            )
        instance.wait_until_exists()
        tag_ec2_instance(instance, instances_tag_data, main_args.elasticsearch, main_args.cluster_name)
    return output_list


def _get_cloud_config_yaml(
        branch=None,
        conf_dir=None,
        cluster_name=None,
        elasticsearch=False,
        no_es=False,
        postgres_version=None,
        save_config_name=None,
        single_data_master=False,
        use_prebuilt_config=None,
    ):
    """
    This will return a config yaml file built from a template and template parts
    - There will still be run variables in the template.
    """
    # Incompatibile build argsuments
    if postgres_version and postgres_version not in ['9.3']:
        print("Error: postgres_version must be '9.3'")
        return None, None, None
    if (elasticsearch or single_data_master) and no_es:
        print('Error: --elasticsearch or --single-data-master cannot also be --no-es frontend')
        return None, None, None
    if (elasticsearch or no_es or single_data_master) and not cluster_name:
        print('Error: --cluster-name required for --elasticsearch or --single-data-master or --no-es')
        return None, None, None
    if cluster_name and not (elasticsearch or no_es or single_data_master):
        print('Error: --cluster-name is only used with --elasticsearch or --single-data-master or --no-es')
        return None, None, None
    # Determine type of build from arguments
    # - Elasticsearch builds will overwrite the postgres version
    build_type = 'demo'
    if single_data_master or elasticsearch:
        build_type = 'es-nodes'
    elif no_es:
        build_type = 'frontend'
    # Determine config build method
    if use_prebuilt_config:
        # Read a prebuilt config file from local dir and use for deployment
        read_config_path = "{}/{}/{}.yml".format(
            conf_dir,
            'prebuilt-config-yamls',
            use_prebuilt_config
        )
        prebuilt_config =  _read_file_as_utf8(read_config_path)
        if prebuilt_config:
            return prebuilt_config, None, build_type
        return None, None, built_type
    else:
        # Build config from template using parts
        template_path = "{}/{}/{}.yml".format(conf_dir, 'config-build-files', build_type)
        pre_config_template = _read_file_as_utf8(template_path)
        replace_vars = set(re.findall('\%\((.*)\)s', pre_config_template))
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
        config_template = pre_config_template % cc_parts_insert
        write_file_path = None
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



def main():
    # Gather Info
    main_args = parse_args()

    # Create config file
    cloud_config_args = {
        'branch': main_args.branch,
        'cluster_name': main_args.cluster_name,
        'conf_dir': main_args.conf_dir,
        'elasticsearch': main_args.elasticsearch,
        'no_es': main_args.no_es,
        'postgres_version': main_args.postgres_version,
        'save_config_name': main_args.save_config_name,
        'single_data_master': main_args.single_data_master,
        'use_prebuilt_config': main_args.use_prebuilt_config,
    }
    build_config, build_path, build_type = _get_cloud_config_yaml(**cloud_config_args)
    if not build_config:
        print('Failure: Could not determine configuration type')
        sys.exit(1)
    if build_path:
        # Data Node Cluster with self elected head node
        # Build: bin/deploy -n tstcnf-data --cluster-name tstcnf-cluster --elasticsearch --save-config-name 20190930
        # Deploy: bin/deploy -n tstcnf-data --cluster-name tstcnf-cluster --elasticsearch --use-prebuilt-config 20190930-es-nodes 


        print("Wrote new config to %s" % build_path)
        _write_str_to_file(build_path, build_config)
        sys.exit(0)
    elif main_args.dry_run_cc:
        print(build_config)
        print('^^ config that would be used')
        sys.exit(0)
    print('# Deploying %s' % build_type)
    print("# {}".format(' '.join(sys.argv)))
    instances_tag_data = _get_instances_tag_data(main_args)
    if instances_tag_data is None:
        sys.exit(10)
    ec2_client = _get_ec2_client(main_args, instances_tag_data)
    if ec2_client is None:
        sys.exit(20)
    run_args = _get_run_args(main_args, instances_tag_data, build_config)
    if main_args.dry_run_aws:
        print('Dry Run AWS')
        print('main_args', main_args)
        print('run_args', run_args.keys())
        print('Dry Run AWS')
        sys.exit(30)
    # Deploy Frontend, Demo, es elect cluster, or es wait data nodes
    bdm = _get_bdm(main_args)
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
    )
    output_list = _wait_and_tag_instances(main_args, run_args, instances_tag_data, instances)
    for output in output_list:
        print(output)
    # Deploy ES master after es wait data nodes
    if 'master_user_data' in run_args and main_args.single_data_master:
        if run_args['master_user_data'] and run_args['count'] > 1 and main_args.elasticsearch:
            instances = ec2_client.create_instances(
                ImageId='ami-2133bc59',
                MinCount=1,
                MaxCount=1,
                InstanceType='c5.9xlarge',
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
            )
            output_list = _wait_and_tag_instances(
                main_args, 
                run_args, 
                instances_tag_data, 
                instances, 
                cluster_master=True,
            )
            for output in output_list:
                print(output)


def parse_args():

    def check_region_index(value):
        lower_value = value.lower()
        allowed_values = [
            'true', 't',
            'false', 'f'
        ]
        if value.lower() not in allowed_values:
            raise argparse.ArgumentTypeError(
                "Noncase sensitive argument '%s' is not in [%s]." % (
                    str(value),
                    ', '.join(allowed_values),
                )
            )
        if lower_value[0] == 't':
            return 'True'
        return 'False'

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
        if value != nameify(value):
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
    parser.add_argument('--conf-dir', default='./cloud-config', help="Location of cloud build config")
    parser.add_argument('--dry-run-aws', action='store_true', help="Abort before ec2 requests.")
    parser.add_argument('--dry-run-cc', action='store_true', help="Abort after building cloud config.")
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
        '--set-region-index-to', 
        type=check_region_index,
        help="Override region index in yaml to 'True' or 'False'"
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
    parser.add_argument('--single-data-master', action='store_true',
            help="Create a single data master node.")
    parser.add_argument('--cluster-name', default=None, help="Name of the cluster")
    parser.add_argument('--cluster-size', default=5, help="Elasticsearch cluster size")
    parser.add_argument('--elasticsearch', action='store_true', help="Launch an Elasticsearch cluster")
    parser.add_argument('--es-ip', default='localhost', help="ES Master ip address")
    parser.add_argument('--es-port', default='9201', help="ES Master ip port")
    parser.add_argument('--no-es', action='store_true', help="Use non ES cloud condfig")
    parser.add_argument('--jvm-gigs', default='8', help="JVM Xms and Xmx gigs")
  
    # Database
    parser.add_argument('--postgres-version', default='9.3', help="Postegres version. '9.3' or '11'")
    parser.add_argument('--redis-ip', default='localhost', help="Redis IP.")
    parser.add_argument('--redis-port', default=6379, help="Redis Port.")
    parser.add_argument('--wale-s3-prefix', default='s3://encoded-backups-prod/production')
    
    # AWS 
    parser.add_argument('--profile-name', default=None, help="AWS creds profile")
    parser.add_argument('--iam-role', default='encoded-instance', help="Frontend AWS iam role")
    parser.add_argument('--iam-role-es', default='elasticsearch-instance', help="ES AWS iam role")
    parser.add_argument(
        '--image-id', 
        default='ami-2133bc59',
        help=(
            "https://us-west-2.console.aws.amazon.com/ec2/home"
            "?region=us-west-2#LaunchInstanceWizard:ami=ami-2133bc59"
        )
    )
    parser.add_argument(
        '--availability-zone', 
        default='us-west-2a',
        help="Set EC2 availabilty zone"
    )
    parser.add_argument(
        '--instance-type', 
        default=None,
        help=(
            "Leave empty for default. "
            "Frontend default: c5.9xlarge. "
            "Datanode default: m5.xlarge. "
            "DataHead default: c5.9xlarge. "
        )
    )
    parser.add_argument(
        '--volume-size', 
        default=200, 
        type=check_volume_size,
        help="Size of disk. Allowed values 120, 200, and 500"
    )
    args = parser.parse_args()
    # Default frontend, datanode, and datahead instance types
    if not args.instance_type:
        if args.elasticsearch:
            args.instance_type = 'm5.xlarge'
            if args.single_data_master:
                args.instance_type = 'c5.9xlarge'
        else:
            args.instance_type = 'c5.9xlarge'
    # Set Role
    # - 'demo' role is default for making single or clustered
    # applications for feature building
    # - '--test' will set role to test
    # - 'rc' role is for Release-Candidate QA testing and
    # is the same as 'demo' except batchupgrade will be skipped during deployment.
    # This better mimics production but require a command be run after deployment.
    # - 'candidate' role is for production release that potential can
    # connect to produciton data.
    if not args.role == 'test':
        if args.release_candidate:
            args.role = 'rc'
            args.candidate = False
        elif args.candidate:
            args.role = 'candidate'
    # Add branch arg
    if not args.branch:
        args.branch = subprocess.check_output(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
        ).decode('utf-8').strip()
    return args


if __name__ == '__main__':
    main()
