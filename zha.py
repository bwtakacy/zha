import threading
import time
import signal

HEALTHCHECK_INTERVAL_SEC = 5
RECHECK_INTERVAL_SEC = HEALTHCHECK_INTERVAL_SEC
LOCK_TIMEOUT = 5
ZNODE_LOCK = "/zha_lock"
ZNODE_ABC  = "/zha_abc"

class ZHA(object):
    class HealthStateChangeCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_state_change(self, state):
            print "ZHA: Health state changed. %d->%d" %(self.zha.health_state, state)
            self.zha.health_state = state
            self.zha.recheck()
    class ElectorStateChangeCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_become_active(self):
            print "ZHA::ElectorCallback: successfully become active"
            self.zha.election_state = Elector.ACT
            self.zha.trigger_active()
        def on_become_active_to_standby(self):
            print "ZHA::ElectorCallback: successfully become standby"
            self.zha.election_state = Elector.SBY
            self.zha.trigger_standby()
        def on_fence(self):
            print "ZHA::ElectorCallback: shoot the node"
            self.zha.trigger_fence()
    def __init__(self, config):
        assert "get_id" in dir(config)
        assert "check_health" in dir(config)
        assert "trigger_active" in dir(config)
        assert "trigger_standby" in dir(config)
        assert "trigger_fence" in dir(config)
        self.trigger_active = config.trigger_active
        self.trigger_standby = config.trigger_standby
        self.trigger_fence = config.trigger_fence
        self.should_run = True
        self.health_state   = HealthMonitor.INIT
        self.election_state = Elector.SBY
        self.monitor = HealthMonitor(config.check_health, callbacks=[self.HealthStateChangeCallback(self)])
        self.elector = Elector(config.get_id(), callbacks=[self.ElectorStateChangeCallback(self),])
        self.monitor.start()
        self.elector.start()
        signal.signal(signal.SIGINT, self.on_sigint)
    def recheck(self):
        if self.health_state == HealthMonitor.OK:
            self.elector.enter()
        else:
            self.elector.leave()
    def mainloop(self):
        while self.should_run:
            self.recheck()
            time.sleep(RECHECK_INTERVAL_SEC)
        self.monitor.should_run = False
        self.elector.should_run = False
        self.monitor.join()
        self.elector.join()
        print "ZHA: main thread stopped."
    def on_sigint(self,sig,frm):
        self.should_run = False
        self.monitor.should_run = False

class HealthMonitor(threading.Thread):
    OK,NG,INIT = 0,1,2
    def __init__(self, monitor_impl, callbacks):
        threading.Thread.__init__(self)
        self.monitor_impl = monitor_impl
        self.callbacks = callbacks
        self.state = HealthMonitor.INIT
        self.should_run = True
    def monitor(self):
        try:
            result = self.monitor_impl()
        except:
            result = HealthMonitor.NG
        if self.state != result:
            self.state = result
            for cb in self.callbacks:
                cb.on_state_change(result)
    def run(self):
        while self.should_run:
            self.monitor()
            time.sleep(HEALTHCHECK_INTERVAL_SEC)
        print "monitor thread stopped."

from kazoo.client import KazooClient
from kazoo.client import KazooState
from kazoo.retry import KazooRetry
class Elector(threading.Thread):
    ACT, SBY = 1,2
    def __init__(self, id, callbacks):
        threading.Thread.__init__(self)
        self.callbacks = callbacks
        self.should_run = True
        self.in_entry = False
        self.state = Elector.SBY
        self.zk = KazooClient()
        self.zk.add_listener(self.zk_listener)
        self.zk.start()
        self.id = id
        self.lock = self.zk.Lock(ZNODE_LOCK, id)
    def enter(self):
        self.in_entry = True
    def leave(self):
        self.in_entry = False
    def zk_listener(self,zkstate):
        if zkstate == KazooState.LOST:
            print "(connection lost)"
            self.zk_safe_release()
        elif zkstate == KazooState.SUSPENDED:
            pass
        else:
            pass
    def handle_abc(self):
        if not self.zk.exists(ZNODE_ABC):
            self.zk.create(ZNODE_ABC, self.id)
            return
        data, stat = self.zk.get(ZNODE_ABC)
        if data.strip()==self.id:
            return
        else:
            for cb in self.callbacks:
                cb.on_fence()
            self.zk.set(ZNODE_ABC, self.id)
    def zk_delete_my_abc(self):
        assert self.zk.exists(ZNODE_ABC)
        data, stat = self.zk.get(ZNODE_ABC)
        assert data.strip() == self.id
        self.zk.delete(ZNODE_ABC)
    def zk_safe_release(self):
        if self.state == Elector.ACT:
            self.state = Elector.SBY
            for cb in self.callbacks:
                cb.on_become_active_to_standby()
            self.zk_delete_my_abc()
            self.lock.release()
    def in_elector_loop(self):
        if self.in_entry is False:
            self.zk_safe_release()
            time.sleep(LOCK_TIMEOUT)
            return
        if self.state == Elector.ACT:
            time.sleep(LOCK_TIMEOUT)
            return
        assert self.in_entry is True and self.state == Elector.SBY
        result = self.lock.acquire() #blocks....
        if result is False:
            return
        if self.in_entry == False:
            self.lock.release()
            return
        self.state = Elector.ACT
        self.handle_abc()
        for cb in self.callbacks:
            cb.on_become_active()
    def run(self):
        while self.should_run:
            self.in_elector_loop()
        self.zk_safe_release()
        self.zk.stop()
        print "elector thread stopped."

