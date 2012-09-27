import dxpy
import json
import os
import shutil
import stat
import subprocess
import tempfile

def ssh_id_filename():
    # TODO: ensure .ssh exists (currently this is done below)
    return os.path.join(os.path.expanduser("~/.ssh"), "incubator_ssh_id")

def save_credentials(credentials):
    """
    Saves credentials file to disk in a place where git/SSH will be able to
    find it.
    """
    # TODO: ignore keys that are not among those we explicitly recognize.
    dot_ssh = os.path.expanduser("~/.ssh")

    try:
        os.mkdir(dot_ssh)
    except:
        pass

    # TODO: preload known_hosts entry for github.com and maybe others
    with open(os.path.join(dot_ssh, "config"), "w") as outfile:
        outfile.write("StrictHostKeyChecking no")

    id_filename = ssh_id_filename()
    print "Saving credentials to %s" % (id_filename)
    dxpy.download_dxfile(credentials, id_filename)
    # Change mode to 0600, as is befitting for credentials.
    os.chmod(id_filename, stat.S_IRUSR | stat.S_IWUSR)


def main():
    repo_url = job['input']['repo_url']
    ref = 'master'
    if 'ref' in job['input']:
        ref = job['input']['ref']
    credentials = None
    if 'credentials' in job['input']:
        credentials = job['input']['credentials']
    target_apiserver_host = None
    if 'target_apiserver_host' in job['input']:
        target_apiserver_host = job['input']['target_apiserver_host']
    target_apiserver_port = None
    if 'target_apiserver_port' in job['input']:
        target_apiserver_port = job['input']['target_apiserver_port']

    print "Repo URL: %s" % (repo_url,)
    print "Ref name: %s" % (ref,)
    if target_apiserver_host:
        print "Overriding API server host: %s" % (target_apiserver_host,)
    if target_apiserver_port:
        print "Overriding API server port: %d" % (target_apiserver_port,)

    if credentials:
        save_credentials(credentials)

    # Clone the repo and run dx-build-app on it.

    tempdir = tempfile.mkdtemp()
    print "Working in " + tempdir

    # Make an SSH wrapper that will make SSH use the provided key (and no
    # other).
    ssh_wrapper_filename = os.path.join(tempdir, 'ssh_wrapper')
    with open(ssh_wrapper_filename, 'w') as ssh_wrapper_outfile:
        ssh_wrapper_outfile.write("#!/bin/sh\nssh -i" + ssh_id_filename() + " -oIdentitiesonly=yes \"$@\"\n")
    os.chmod(ssh_wrapper_filename, stat.S_IRUSR | stat.S_IXUSR)

    checkout_dir = os.path.join(tempdir, "clonedest")
    os.mkdir(checkout_dir)
    os.chdir(checkout_dir)
    override_env = dict(os.environ)
    override_env['GIT_SSH'] = ssh_wrapper_filename
    subprocess.check_call(['git', 'clone', repo_url, 'userapp'], env=override_env)

    os.chdir('userapp')
    subprocess.check_call(['git', 'checkout', '-q', ref])

    subprocess.check_call(['git', 'submodule', 'update', '--init'])

    # Load any build deps requested by the app.
    with open('dxapp.json') as manifest:
        parsed_manifest = json.load(manifest)
        # TODO: check that manifest.buildDepends is an array of hashes
        if 'buildDepends' in parsed_manifest:
            depends = [dep['name'] for dep in parsed_manifest['buildDepends']]
            print 'Installing the following packages specified in buildDepends: ' + ', '.join(depends)
            cmd = ['sudo', 'apt-get', 'install', '--yes'] + depends
            subprocess.check_call(cmd)

    # Override the API server host and port if requested.
    env = dict(os.environ)
    if target_apiserver_host:
        env['DX_APISERVER_HOST'] = target_apiserver_host
    if target_apiserver_port:
        env['DX_APISERVER_PORT'] = target_apiserver_port

    os.chdir(checkout_dir)
    cmd = ['dx-build-app', 'userapp']
    subprocess.check_call(cmd, env=env)

    shutil.rmtree(tempdir)