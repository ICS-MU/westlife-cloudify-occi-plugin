RUNTIME_PROPERTIES = [
    'ip', 'networks', 'device',
    'user', 'port', 'password', 'key',
    'occi_resource_id', 'occi_resource_url', 'occi_resource_title',
]

def get_instance_state(ctx, client):
    url = ctx.instance.runtime_properties['occi_resource_url']
    response = client.describe(url)[0] #TODO: check structure
    return get_state(response)

def get_state(data):
    if data['kind'].endswith('#compute'):
        return data['attributes']['occi']['compute']['state']
    elif data['kind'].endswith('#storage'):
        return data['attributes']['occi']['storage']['state']
    else:
        raise Exception('Unknown kind '+resp[0]['kind'])

def delete_runtime_properties(ctx):
    for key in RUNTIME_PROPERTIES:
        if key in ctx.instance.runtime_properties:
            del ctx.instance.runtime_properties[key]
