# zha

`zha` is a small python library that delivers high availability to an arbitary
program.  `zha` leverages Apache ZooKeeper and its python bindings kazoo, and is
inspired from Apache Hadoop (ZKFC).

This project is WIP, no stable release yet.

## Concepts

- Small and Handy
- Well documented

## Install

`zha` is a single file `zha.py`. So all you need is install dependencies, that is, kazoo

```
sudo pip install kazoo
```

## Usage

Modify `skelton.py` for your need, type `python skelton.py` to start, and press
`Ctrl+C` or send SIGINT to stop.  See `skelton.py` for details. This is a
standalone program to use zha.

## LICENCE

BSD, as embedded in `zha.py`

## Releases

- 2015/06/05: ver 0.1.0. This is a beta release.

## What zha supports

High availability cluster consists of one active process (ACT) and multiple
standby processes (SBYs). When ACT faults, one of SBYs is selected as a new ACT
candidate and performs failover, that is, takes over floating IP(VIP) and
broadcast gracious arp in purpose of informing another servers that new ACT
takes over VIP. Some software need additional treatment during failover.

`zha` helps this failover sequence, that is, a) Lockholder selection , b) Health
Monitoring c) Triggering failover.

### Lockholder selection
In `zha` semantics, one zha instance that holds a lock on ZooKeeper emsemble is
eligible to be ACT. All other zha instances waiting to acquire the lock are
SBYs. ACT zha instance releases lock only when the monitoring resource become
unhealthy or loses session to a ZooKeeper emsemble. The next lockholder becomes
eligible to be ACT, and performs failover procedure.

`zha` supports this lock acquitision race. When users provide how to perform
failover, `zha` call it back on lock acquitition.

### Health monitoring
ACT should retire when its resource becomes unhealthy. SBY should stop trying
to lock. `zha` supports this. 

### Triggering failover
Failover sequecnce has two phases. One is for ACT and the other is for a new
ACT candidate. When ACT ceases its role, some clenup jobs should be done. It
includes detaching VIP, performing some operations such as stopping its
resource, releasing the lock. New ACT candicate needs to check that ACT retires
cleanly and if not, performs STONITH (shoot the other node in the head) for
avoinding nightmare situation, split-brain. After that, new ACT candicate
takes over the role, which includes attaching VIP and broadcast garp.

## zha API summary
Zha helps lockholder selection, health monitoring, and triggering failover.
Users have to inform zha how to do that. This section shows howto. 

Typical usage of zha is as follows: a) define config class, b) create `zha.ZHA` instance,
c) call `mainloop()`.

```
import zha
z = zha.ZHA(Config())
z.mainloop() # Ctrl+C to stops
```

Users inform zha of system information via defining `Config` class.
So `zha` defines `Config` class interface. It is well documented in the
`skelton.py`. Below is an extraction:

```
get(keyname, defaultvalue): 
    returns a specified value if keyname exists, otherwise defaultvalue.
    keyname="id" is REQUIRED to specify zha identity, which MUST be unique among cluster.
    Another keys and default values zha uses are listed in skelton.py.
check_health(): 
    returns integer and throws no exception. Returning value is constructed as below:
        retvalue = is_healthy_to_be_sby | 2*is_healthy_to_be_act
    That is, 0 for NG as SBY candicate and also ACT candicate,
    1 for OK as SBY candicate and NG as ACT candicate,
    2 for NG as SBY candicate and OK as ACT candicate,
    3 for OK as both SBY and ACT candicates.
    This method is adviced not to block for a long time so that health monitor thread
    can check multiple times within "health_dms_timeout", which can rescure the situation of
    ocasional failure of cheak_health(). 
become_active() : 
    returns 0 for OK, another integer for NG, and throws no exception.
    This method is invoked when this zha is eligible to become active.
    When this method returns 0, zha considers failover has completed and sets its
    status active, otherwise keeps its status standby. For NG, all cleanup codes for 
    another zha invoking become_active is REQUIRED to be implemented.
    This method SHOULD be reentrant, because some resources becomes already  active
    before zha starts up.
become_clustered():
    returns 0 for OK, another integer for NG.
    CLUSTERED is a ACT state with at least one SBYs. Some middleware, such as PostgreSQL
    requires clustered/declustered configuration.
become_declustered():
    returns 0 for OK, another integer for NG.
    DECLUSTERED is a ACT state with at no SBYs. Some middleware, such as PostgreSQL
    requires clustered/declustered configuration.
become_standby_from_active():
    returns 0 for OK, another integer for NG, and throws no exception.
    This method is invoked when this process has ceased to be active, such as
    health monitor failure or zookeeper connection problem.
    When this method returns NG, zha considers cleanup should be need for another zha becoming active
    , which will result in being fenced by another zha.
    Note that zha on startup, this method is not inovoked.
trigger_fence(): 
    returns 0 for OK, another integer for NG, and throws no exception.
    This methods will be invoked only when this zha is eligible to become active 
    AND the previous active zha is not did not cleanly retire 
    AND the previous active zha is not this zha.
    This SHOULD always succeed, otherwise this zha stops failover.
```


