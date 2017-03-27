# iproxy

----
## what is IProxy?
IProxy is a binding proxy, intended bring source ip selection to applications that does not support binding.

You can use any IP you machine has, and even whole ranges thanks to the freebind linux socket option.

----
## usage
- create `config.json` to set port and key
- run `python server.py`
- configure your apps to use the proxy

----
## adding an ip address
It depends on your distribution. This README file just treats debian.
Adjust your `/etc/network/interfaces` :

```
# primary IP address
auto eth0
iface eth0 inet static
        address 88.191.12.37
        netmask 255.255.255.0
        network 88.191.12.0
        broadcast 88.191.12.255
        gateway 88.191.12.1

# secondary
auto eth0:0
iface eth0:0 inet static
        address 88.191.200.44
        netmask 255.255.255.224
        network 88.191.200.32
        broadcast 88.191.200.63

auto eth0:1
iface eth0:1 inet static
...
```

and restart networking services

## adding an ip range
with ipv6 you can easily get an ip bloc. adding each possible ip would suck (slow to do, would slow down the machine and you can't possible add the billions of ips your range has), fortunately linux supports ip ranges, coupled with freebind we can enjoy massive ip count.

create `/etc/dhcp/dhclient6.conf`:
```
interface "eth0" {
    send dhcp6.client-id 13:37:13:37:13:37:13:37:13:37;
}
```

create a system.d service `/etc/systemd/system/dhclient.service`:
```
[Unit]
Description=dhclient for sending DUID IPv6
Wants=network.target
Before=network.target

[Service]
Type=forking
ExecStart=/usr/sbin/dhclient -cf /etc/dhcp/dhclient6.conf -6 -P -v eth0

[Install]
WantedBy=multi-user.target
```

and enable+start the service :
```
systemctl enable dhclient.service
systemctl start dhclient.service
```
