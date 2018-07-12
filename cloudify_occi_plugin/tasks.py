# import cloudify
import random
import string

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
    availability_zone = resource_config.get('availability_zone')
    network = resource_config.get('network')
    network_pool = resource_config.get('network_pool')
    cloud_config = ctx.node.properties.get('cloud_config', dict())
    # TODO: cpu, memory

    # cloud-init configuration
    cc = client.gen_cloud_init_data(
        user=cloud_config.get('username'),
        public_keys=[cloud_config.get('public_key')],
        data=cloud_config.get('data'))

    try:
        url = client.create(name, os_tpl, resource_tpl, availability_zone, cc)
        ctx.instance.runtime_properties['occi_resource_url'] = url
        ctx.instance.runtime_properties['occi_resource_title'] = name
    except Exception:
        raise

    # link network
    try:
        if network:
            if network_pool:
                mixins = [network_pool]
            else:
                mixins = []

            net_url = client.link(network, url, mixins)
            ctx.instance.runtime_properties['occi_network_link_url'] = net_url
    except Exception:
        client.delete(url)
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
        if link['rel'].endswith('#ipreservation'):
            ip = link['attributes']['occi']['networkinterface']['address']
            ips.append(ip)

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

# VH: on savba.sk deletes whole VM, not just the assigned network
#    net_url = ctx.instance.runtime_properties.get('occi_network_link_url')
#    if net_url:
#        client.delete(net_url)

    # stop active instance
    state = get_instance_state(ctx, client)
    if (state == 'active'):
        client.trigger(url, 'stop')
        state = get_instance_state(ctx, client)

    # check again for suspended instance or retry
    if ((state not in ['suspended', 'inactive']) and
            kwargs.get('wait_finish', True)):
        return ctx.operation.retry(
            message='Waiting for server to stop (state: %s)' % (state,),
            retry_after=kwargs['stop_retry_interval'])


@operation
@with_client
def delete(client, **kwargs):
    ctx.logger.info('Deleting')

    cln = ctx.instance.runtime_properties.get('occi_cleanup_urls')
    url = ctx.instance.runtime_properties.get('occi_resource_url')

    if url:
        # store linked resources for post-delete cleanup
        if cln is None:
            cln = []

            try:
                desc = client.describe(url)
                for link in desc[0]['links']:
                    if (link['rel'].endswith('#storage') and
                            not link['id'].endswith('_disk_0')):
                        cln.append(link['target'])
            except Exception:
                pass
            finally:
                ctx.instance.runtime_properties['occi_cleanup_urls'] = cln

        try:
            client.delete(url)
        except Exception:
            pass

        # check the resource is deleted
        try:
            client.describe(url)

            if kwargs.get('wait_finish', True):
                return ctx.operation.retry(
                    message='Waiting for resource to delete',
                    retry_after=kwargs['delete_retry_interval'])
            else:
                raise Exception
        except Exception:
            if cln:
                del ctx.instance.runtime_properties['occi_resource_url']

                return ctx.operation.retry(
                    message='Waiting for linked resources to delete',
                    retry_after=kwargs['delete_retry_interval'])

    # cleanup linked resources
    elif cln:
        for link in cln:
            try:
                client.delete(link)
            except Exception:
                pass

    delete_runtime_properties(ctx)


@operation
@with_client
def create_volume(client, **kwargs):
    ctx.logger.info('Creating volume')
    size = ctx.node.properties.get('size', dict())
    name = ctx.node.properties.get('name')
    if not name:
        rand = ''.join(random.sample((string.letters+string.digits)*6, 6))
        name = 'cfy-disk-%s-%s' % (ctx.instance.id, rand)
    availability_zone = ctx.node.properties.get('availability_zone')

    url = client.create_volume(name, size, availability_zone)
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
def attach_volume(client, attach_retry_interval, **kwargs):
    ctx.logger.info('Attaching volume')

    url = ctx.source.instance.runtime_properties.get('occi_storage_link_url')
    if not url:
        srv_url = ctx.target.instance.runtime_properties['occi_resource_url']
        vol_url = ctx.source.instance.runtime_properties['occi_resource_url']
        url = client.link(vol_url, srv_url)
        ctx.source.instance.runtime_properties['occi_storage_link_url'] = url

    desc = client.describe(url)
    state = desc[0]['attributes']['occi']['storagelink']['state']

    if state == 'active':
        ctx.source.instance.runtime_properties['device'] = \
                desc[0]['attributes']['occi']['storagelink']['deviceid']
    else:
        return ctx.operation.retry(
                message='Waiting for volume to attach (state: %s)' % (state,),
                retry_after=attach_retry_interval)


@operation
@with_client
def detach_volume(client, detach_retry_interval, **kwargs):
    if kwargs.get('skip_action'):
        ctx.logger.info('Volume detach skipped by configuration')
        del ctx.source.instance.runtime_properties['occi_storage_link_url']
        del ctx.source.instance.runtime_properties['device']
        return

    ctx.logger.info('Detaching volume')
    url = ctx.source.instance.runtime_properties['occi_storage_link_url']

    try:
        desc = client.describe(url)
        state = desc[0]['attributes']['occi']['storagelink']['state']
        if state == 'active':
            client.delete(url)

        if kwargs.get('wait_finish', True):
            return ctx.operation.retry(
                message='Waiting for volume to detach (state: %s)' % (state,),
                retry_after=detach_retry_interval)
        else:
            raise Exception
    except Exception:
        if 'occi_storage_link_url' in ctx.source.instance.runtime_properties:
            del ctx.source.instance.runtime_properties['occi_storage_link_url']
        if 'device' in ctx.source.instance.runtime_properties:
            del ctx.source.instance.runtime_properties['device']
