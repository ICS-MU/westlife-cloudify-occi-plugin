import cloudify

from cloudify import ctx, context
from cloudify.exceptions import NonRecoverableError, RecoverableError
from cloudify.decorators import operation
from cloudify_occi_plugin.provider.cli import Client
from functools import wraps
from time import sleep

RUNTIME_PROPERTIES = [
    'ip', 'networks',
    'user', 'port', 'password', 'key',
    'occi_resource_id', 'occi_resource_url', 'occi_resource_title',
]

def with_client(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        ctx = kwargs['ctx']
        if ctx.type == context.NODE_INSTANCE:
            config = ctx.node.properties.get('occi_config')
        elif ctx.type == context.RELATIONSHIP_INSTANCE:
            config = ctx.source.node.properties.get('occi_config')
            if not config:
                config = ctx.target.node.properties.get('occi_config')
        else:
            config = None

        if 'occi_config' in kwargs:
            if config:
                config = config.copy()
                config.update(kwargs['occi_config'])
            else:
                config = kwargs['occi_config']

        kwargs['client'] = Client(config)
        return f(*args, **kwargs)
    return wrapper
        
@operation
@with_client
def create(client, **kwargs):
    ctx.logger.info('Creating node')

    # instance parameters
    name = ctx.node.properties.get('name')
    if not name:
        name = 'cfy-node-%s' % ctx.instance.id

    resource_config = ctx.node.properties['resource_config']
    os_tpl = resource_config['os_tpl']
    resource_tpl = resource_config['resource_tpl']
    cloud_config = ctx.node.properties.get('cloud_config', dict())
    # TODO: cpu, memory

    # cloud-init configuration
    cc = client.gen_cloud_init_data(
        user = cloud_config.get('username'),
        public_keys = [cloud_config.get('public_key')],
        data = cloud_config.get('data'))

    try:
        url = client.create(name, os_tpl, resource_tpl, cc)
        ctx.instance.runtime_properties['occi_resource_url'] = url
        ctx.instance.runtime_properties['occi_resource_title'] = name 
    except:
        raise

@operation
@with_client
def start(client, start_retry_interval, **kwargs):
    ctx.logger.info('Starting node')
    url = ctx.instance.runtime_properties['occi_resource_url']
    resp = client.describe(url)
    state = resp[0]['attributes']['occi']['compute']['state']
    if (state != 'active'):
        return ctx.operation.retry(
            message='Waiting for server to start (state: %s)' % (state,),
            retry_after=start_retry_interval)

    # get instance IP addresses
    ips = []
    for link in resp[0]['links']:
        if link['rel'] == 'http://schemas.ogf.org/occi/infrastructure#network':
            ips.append(link['attributes']['occi']['networkinterface']['address'])

    # properties
    ctx.instance.runtime_properties['ip'] = ips[0]
    ctx.instance.runtime_properties['networks'] = ips

@operation
@with_client
def stop(client, **kwargs):
    ctx.logger.info('Stopping')
    url = ctx.instance.runtime_properties.get('occi_resource_url')
    if not url:
        raise Exception('OCCI_URL expected')

    # stop active instance
    desc = client.describe(url)
    state = desc[0]['attributes']['occi']['compute']['state']
    if (state == 'active'):
        client.trigger(url, 'stop')
        desc = client.describe(url)
        state = desc[0]['attributes']['occi']['compute']['state']

    # check again for suspended instance or retry
    if (state != 'suspended'):
        return ctx.operation.retry(
            message='Waiting for server to stop (state: %s)' % (state,))

@operation
@with_client
def delete(client, **kwargs):
    ctx.logger.info('Deleting')
    url = ctx.instance.runtime_properties.get('occi_resource_url')
    if url:
        try:
            desc = client.describe(url)
            client.delete(url)
        finally:
            delete_runtime_properties(ctx)

@operation
@with_client
def create_volume(client, **kwargs):
    ctx.logger.info('Creating volume')
    size = ctx.node.properties.get('size', dict())
    name = ctx.node.properties.get('name')
    if not name:
        name = 'cfy-disk-%s' % ctx.instance.id

    url = client.create_volume(name, size)
    ctx.instance.runtime_properties['occi_resource_url'] = url
    ctx.instance.runtime_properties['occi_resource_title'] = name 

@operation
@with_client
def start_volume(client, start_retry_interval, **kwargs):
    url = ctx.instance.runtime_properties['occi_resource_url']
    desc = client.describe(url)
    state = desc[0]['attributes']['occi']['storage']['state']
    if (state != 'online'):
        return ctx.operation.retry(
            message='Waiting for volume to start (state: %s)' % (state,),
            retry_after=start_retry_interval)

@operation
@with_client
def attach_volume(client, **kwargs):
    ctx.logger.info('Attaching volume')
    server_url = ctx.target.instance.runtime_properties['occi_resource_url']
    volume_url = ctx.source.instance.runtime_properties['occi_resource_url']
    print client.link(volume_url, server_url)
    # TODO: pockat na attach, zaktualizovat device

@operation
@with_client
def detach_volume(client, **kwargs):
    ctx.logger.info('Detaching volume')
    server_url = ctx.target.instance.runtime_properties['occi_resource_url']
    volume_url = ctx.source.instance.runtime_properties['occi_resource_url']
    raise Exception('Not supported')
#    desc = client.describe(url)
#    state = desc[0]['attributes']['occi']['storage']['state']
#    if (state != 'online'):
#        return ctx.operation.retry(
#            message='Waiting for volume to detach (state: %s)' % (state,),
#            retry_after=start_retry_interval)

def delete_runtime_properties(ctx):
    for key in RUNTIME_PROPERTIES:
        if key in ctx.instance.runtime_properties:
            del ctx.instance.runtime_properties[key]
