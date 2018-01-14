import json
import math
import os
import subprocess

from cloudify import ctx
from yaml import dump
from tempfile import NamedTemporaryFile


class Client(object):
    def __init__(self, config):
        self._cmd = '/usr/local/bin/occi'  # TODO
        self._config = config
#        self.runcli([u'--version'])

    def create(self, name, os_tpl, resource_tpl, az=None, cc={}):
        m = ['os_tpl#%s' % os_tpl, 'resource_tpl#%s' % resource_tpl]
        if az:
            m += ['availability_zone#%s' % az]
        a = ['occi.core.title=%s' % name]
        f = self.cloud_init(cc, intofile=True)

        try:
            url = self.runcli([
                    '--action', 'create',
                    '--resource', 'compute',
                    '--context', "user_data=file://%s" % f
                ], mixins=m, attrs=a)
        finally:
            if os.path.isfile(f):
                os.unlink(f)

        return url

    def describe(self, resource):
        return self.runcli(['--action', 'describe', '--resource', resource])

    def delete(self, resource):
        return self.runcli(['--action', 'delete', '--resource', resource])

    def trigger(self, resource, action):
        return self.runcli(['--action', 'trigger',
                            '--trigger-action', action,
                            '--resource', resource])

    def link(self, source, target, mixins=[]):
        return self.runcli([
                '--action', 'link',
                '--resource', target,
                '--link', source
            ], mixins=mixins)

    def unlink(self, source, target, mixins=[]):
        return self.runcli([
                '--action', 'unlink',
                '--resource', target,
                '--link', source
            ], mixins=mixins)

    def create_volume(self, title, size, az=None):
        a = ['occi.core.title=%s' % title]
        a += ['occi.storage.size=%i' % math.ceil(size)]
        m = []
        if az:
            m += ['availability_zone#%s' % az]
        url = self.runcli([
                '--action', 'create',
                '--resource', 'storage'
            ], mixins=m, attrs=a)
        return url

    def runcli(self, args=[], mixins=[], attrs=[]):
        c = [self._cmd, '--output-format', 'json']

        # authentication params
        if 'endpoint' in self._config:
            c += ['--endpoint', self._config['endpoint']]
        if self._config.get('auth', ''):
            c += ['--auth', self._config['auth']]
        if self._config.get('username', ''):
            c += ['--username', self._config['username']]
        if self._config.get('password', ''):
            c += ['--password', self._config['password']]
        if self._config.get('user_cred', ''):
            c += ['--user-cred', self._config['user_cred']]
        if self._config.get('ca_path', ''):
            c += ['--ca-path', self._config['ca_path']]
        if self._config.get('voms', False):
            c += ['--voms']

        # mixins, attributes and other arguments
        for mixin in mixins:
            c += ['--mixin', mixin]
        for attr in attrs:
            c += ['--attribute', attr]
        if args:
            c += args

        ctx.logger.info('Executing %s' % (c,))
        p = subprocess.Popen(c, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        (out, err) = p.communicate()
        status = p.wait()
        ctx.logger.info('Exited with code=%i' % status)

        if (status == 0):
            try:
                data = json.loads(out)
            except ValueError:
                data = out.strip()
        else:
            raise Exception('Failed to run occi: %s' % err)

        return data

    def cloud_init(self, data, intofile=True):
        """
        Generate cloud-init configuration and output as string
        or dump into temporary file.
        """
        s = "#cloud-config\n"+dump(data, default_flow_style=False)
        if intofile:
            f = NamedTemporaryFile(delete=False)
            f.write(s)
            f.close()
            return f.name
        else:
            return s

    def gen_cloud_init_data(self, user='cloudadm', lock_passwd=True,
                            public_keys=[], data={}):
        d = dict(users=[{
            'name': user,
            'sudo': 'ALL=(ALL) NOPASSWD:ALL',
            'lock-passwd': lock_passwd,
            'ssh-authorized-keys': public_keys
        }])

        if (user == 'root'):
            d['disable_root'] = False
            ctx.logger.warning('SSH on root is disabled in EGI images!')

        d.update(data)
        return d
