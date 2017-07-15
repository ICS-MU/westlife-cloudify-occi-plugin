# Cloudify OCCI plugin

[![Build Status](https://travis-ci.org/ICS-MU/westlife-cloudify-occi-plugin.svg?branch=master)](https://travis-ci.org/ICS-MU/westlife-cloudify-occi-plugin)

## OCCI CLI

Plugin requires the `occi` CLI to be installed on a host managing the deployment.

### RHEL/CentOS 7.x

```
yum install -y ruby-devel openssl-devel gcc gcc-c++ ruby rubygems
gem install occi-cli
```

### Debian/Ubuntu family

```
apt-get install -y ruby rubygems ruby-dev
gem install occi-cli
```

***

CERIT Scientific Cloud, <support@cerit-sc.cz>
