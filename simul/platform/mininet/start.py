#!/usr/bin/python

"""
This will run a number of hosts on the server and do all
the routing to being able to connect to the other mininets.

You have to give it a list of server/net/nbr for each server
that has mininet installed and what subnet should be run
on it.

It will create nbr+1 entries for each net, where the ".1" is the
router for the net, and ".2"..".nbr+1" will be the nodes.
"""

import sys, time, threading, os, datetime

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.cli import CLI
from mininet.log import lg, setLogLevel
from mininet.node import Node, Host
from mininet.util import netParse, ipAdd, irange
from mininet.nodelib import NAT
from subprocess import Popen, PIPE, call

# The port used for socat
socatPort = 5000
# If this is true, only a dummy-function will be started on each mininet-node
cothorityDummy = True
# What debugging-level to use
debugging = 3
# Logging-file
logfile = "/tmp/stdout.gw"

class BaseRouter(Node):
    """"A Node with IP forwarding enabled."""
    def config( self, rootLog=None, **params ):
        super(BaseRouter, self).config(**params)
        print "Starting router at", self.IP(), rootLog
        self.cmd( 'sysctl net.ipv4.ip_forward=1' )
        socat = "socat %s udp4-listen:%d,reuseaddr,fork" % (logfile, socatPort)
        print "Running socat on gw:", socat
        self.cmd( '%s &' % socat )
        # self.cmd('ping -c 2 10.2.0.1 >> /tmp/ping')
        # self.cmd('ip a >> /tmp/ping')
        if rootLog:
            self.cmd('tail -f /tmp/stdout.gw | socat - udp-sendto:%s:%d &' % (rootLog, socatPort))

    def terminate( self ):
        print "Stopping router"
        self.cmd( 'sysctl net.ipv4.ip_forward=0' )
        self.cmd( 'killall socat' )
        super(BaseRouter, self).terminate()


class Cothority(Host):
    """A cothority running in a host"""
    def config(self, gw=None, simul="", **params):
        super(Cothority, self).config(**params)
        print "Starting cothority-node on", self.IP()
        # TODO: this will fail on other nodes than the root.
        self.cmd('cd ~/mininet_run')
        socat="socat -v - udp-sendto:%s:%d 2> /tmp/socat" % (gw, socatPort)
        print "Socat is", socat, "on", self.IP()
        # self.cmd('sleep 10')
        # socat="socat -v >> /tmp/socat"
        if cothorityDummy:
            print "Starting dummy"
            # self.cmd('while (ip a | grep "inet 10" ); do sleep 1; done | %s &' % socat)
            # self.cmd('ping -c 2 10.2.0.1 | %s &' % socat)
            self.cmd('ping -c 2 10.1.0.1 >> /tmp/socat')
            # self.cmd('ip a | %s &' % socat)
        else:
            print "Starting cothority on node", self.IP(), socat
            self.cmd('( pwd; ./cothority -debug %s -address %s:2000 -simul %s ) | %s &' %
		        ( debugging, self.IP(), simul, socat ))

    def terminate(self):
        print "Stopping cothority"
        if cothorityDummy:
            self.cmd('killall while')

        self.cmd('killall socat')
        super(Cothority, self).terminate()


class InternetTopo(Topo):
        """Create one switch with all hosts connected to it and host
        .1 as router - all in subnet 10.x.0.0/16"""
        def __init__(self, myNet=None, rootLog=None, **opts):
            Topo.__init__(self, **opts)
            server, mn, n = myNet[0]
            switch = self.addSwitch('s0')
            baseIp, prefix = netParse(mn)
            gw = ipAdd(1, prefix, baseIp)
            print "Gw", gw, "baseIp", baseIp, prefix
            hostgw = self.addNode('h0', cls=BaseRouter,
                                  ip='%s/%d' % (gw, prefix),
                                  inNamespace=False,
                                  rootLog=rootLog)
            # hostgw = self.addNode('h0', ip='%s/%d' % (gw, prefix))
            self.addLink(switch, hostgw)

            for i in range(1, int(n) + 1):
                ipStr = ipAdd(i + 1, prefix, baseIp)
                host = self.addHost('h%d' % i, cls=Cothority,
                                    ip = '%s/%d' % (ipStr, prefix),
                                    defaultRoute='via %s' % gw,
			                	    simul="CoSimul", gw=gw)
                # host = self.addHost('h%d' % i, ip = '%s/%d' % (ipStr, prefix))
                print "Adding link", host, switch
                self.addLink(host, switch)

def RunNet():
    """RunNet will start the mininet and add the routes to the other
    mininet-services"""
    rootLog = None
    if myNet[1] > 0:
        i, p = netParse(otherNets[0][1])
        rootLog = ipAdd(1, p, i)
    print "Creating network", myNet
    topo = InternetTopo(myNet=myNet, rootLog=rootLog)
    print "Starting on", myNet
    net = Mininet(topo=topo)
    net.start()
    for (gw, n, i) in otherNets:
        print "Adding route for", n, gw
        net['h0'].cmd( 'route add -net %s gw %s' % (n, gw) )
    CLI(net)
    time.sleep(5)
    for (gw, n, i) in otherNets:
        net['h0'].cmd( 'route del -net %s gw %s' % (n, gw) )

    print "Stopping on", myNet
    net.stop()

class InternetTopoEx(Topo):
    "Single switch connected to n hosts."
    def __init__(self, n=2, **opts):
        Topo.__init__(self, **opts)

        # set up inet switch
        inetSwitch = self.addSwitch('s0')
        # add inet host
        inetHost = self.addHost('h0')
        self.addLink(inetSwitch, inetHost)

        # add local nets
        for i in irange(1, n):
            inetIntf = 'nat%d-eth0' % i
            localIntf = 'nat%d-eth1' % i
            localIP = '192.168.%d.1' % i
            localSubnet = '192.168.%d.0/24' % i
            natParams = { 'ip' : '%s/24' % localIP }
            # add NAT to topology
            nat = self.addNode('nat%d' % i, cls=NAT, subnet=localSubnet,
                               inetIntf=inetIntf, localIntf=localIntf)
            switch = self.addSwitch('s%d' % i)
            # connect NAT to inet and local switches
            self.addLink(nat, inetSwitch, intfName1=inetIntf)
            self.addLink(nat, switch, intfName1=localIntf, params1=natParams)
            # add host and connect to local switch
            host = self.addHost('h%d' % i,
                                ip='192.168.%d.100/24' % i,
                                defaultRoute='via %s' % localIP)
            self.addLink(host, switch)

def RunNetEx():
    "Create network and run the CLI"
    topo = InternetTopo()
    net = Mininet(topo=topo)
    net.start()
    CLI(net)
    net.stop()

def GetNetworks(filename):
    """GetServer will read the file and search if the current server
    is in it and return those. It will also return whether we're in the
    first line and thus the 'root'-server for logging."""

    process = Popen(["ip", "a"], stdout=PIPE)
    (ips, err) = process.communicate()
    process.wait()

    with open(filename) as f:
        content = f.readlines()
    list = []
    for line in content:
        list.append(line.rstrip().split(' '))

    otherNets = []
    myNet = None
    pos = 0
    for (server, net, count) in list:
        t = [server, net, count]
        if ips.find('inet %s/' % server) >= 0:
            myNet = [t, pos]
        else:
            otherNets.append(t)
        pos += 1

    return myNet, otherNets

# The only argument given to the script is the server-list. Everything
# else will be read from that and searched in the computer-configuration.
if __name__ == '__main__':
    setLogLevel('info')
    # lg.setLogLevel( 'critical')
    if len(sys.argv) < 2:
        print "please give list-name"
        sys.exit(-1)

    list_file = sys.argv[1]
    myNet, otherNets = GetNetworks(list_file)

    if myNet:
        print "Starting mininet for", myNet
        t1 = threading.Thread(target=RunNet)
        t1.start()

    if len(sys.argv) > 2:
        os.remove(logfile)
        with open(logfile, mode='a') as lfile:
            lfile.write('Starting log at %s.\n' %
                            datetime.datetime.now())
        for (server, mn, nbr) in otherNets:
            print "Going to copy things %s to %s and run %s hosts in net %s" % \
                  (list_file, server, nbr, mn)
            call("scp -q cothority start.py %s %s:" % (list_file, server), shell=True)
            # print("going to clean mininet")
            # call("ssh %s /usr/local/bin/mn -c" % server, shell=True)
            print "Launching script on %s" % server
            call("ssh -q %s sudo python -u start.py %s &" % (server, list_file), shell=True)
            time.sleep(0.1)

    if myNet:
        t1.join()
        time.sleep(1)
