# import cloudify

from cloudify import ctx
# from cloudify.exceptions import NonRecoverableError, RecoverableError
from cloudify.decorators import operation
from cloudify_occi_plugin.utils import (
    with_client,
    get_instance_state,
    get_state,
    delete_runtime_properties)


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
        user=cloud_config.get('username'),
        public_keys=[cloud_config.get('public_key')],
        data=cloud_config.get('data'))

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
    res = client.describe(url)[0]  # TODO: check structure
    state = get_state(res)
    if (state != 'active'):
        return ctx.operation.retry(
            message='Waiting for server to start (state: %s)' % (state,),
            retry_after=start_retry_interval)

    # get instance IP addresses
    ips = []
    for link in res['links']:
        if link['rel'].endswith('#network'):
            ip = link['attributes']['occi']['networkinterface']['address']
            ips.append(ip)

    if ips:
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
    state = get_instance_state(ctx, client)
    if (state == 'active'):
        client.trigger(url, 'stop')
        state = get_instance_state(ctx, client)

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
    state = get_instance_state(ctx, client)
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
    url = client.link(volume_url, server_url)
    ctx.source.instance.runtime_properties['occi_link_url'] = url

    desc = client.describe(url)
    ctx.source.instance.runtime_properties['device'] = \
        desc[0]['attributes']['occi']['storagelink']['deviceid']


@operation
@with_client
def detach_volume(client, **kwargs):
    ctx.logger.info('Detaching volume')
    url = ctx.source.instance.runtime_properties['occi_link_url']
    client.delete(url)
    try:
        del ctx.source.instance.runtime_properties['occi_link_url']
        del ctx.source.instance.runtime_properties['device']
    except:
        pass
