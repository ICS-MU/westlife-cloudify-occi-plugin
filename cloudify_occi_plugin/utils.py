from cloudify import context
from cloudify_occi_plugin.provider.cli import Client
from functools import wraps


RUNTIME_PROPERTIES = [
    'ip', 'networks', 'device',
    'user', 'port', 'password', 'key',
    'occi_resource_id', 'occi_resource_url', 'occi_resource_title',
    'occi_storage_link_url', 'occi_network_link_url',
    'occi_cleanup_urls'
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


def get_instance_state(ctx, client):
    url = ctx.instance.runtime_properties['occi_resource_url']
    response = client.describe(url)[0]  # TODO: check structure
    return get_state(response)


def get_state(data):
    kind = data['kind']
    if kind.endswith('#compute'):
        return data['attributes']['occi']['compute']['state']
    elif kind.endswith('#storage'):
        return data['attributes']['occi']['storage']['state']
    elif kind.endswith('#storagelink'):
        return data['attributes']['occi']['storagelink']['state']
    else:
        raise Exception('Unknown kind '+kind)


def delete_runtime_properties(ctx):
    for key in RUNTIME_PROPERTIES:
        if key in ctx.instance.runtime_properties:
            del ctx.instance.runtime_properties[key]
