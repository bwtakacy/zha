import threading
import time
import signal

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
        assert config.get("id")
        assert "check_health" in dir(config)
        assert "trigger_active" in dir(config)
        assert "trigger_standby" in dir(config)
        assert "trigger_fence" in dir(config)
        self.trigger_active = config.trigger_active
        self.trigger_standby = config.trigger_standby
        self.trigger_fence = config.trigger_fence
        self.config = config
        self.should_run = True
        self.health_state   = HealthMonitor.INIT
        self.election_state = Elector.SBY
        self.monitor = HealthMonitor(config, callbacks=[self.HealthStateChangeCallback(self)])
        self.elector = Elector(config, callbacks=[self.ElectorStateChangeCallback(self),])
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
            time.sleep(self.config.get("recheck_interval",5))
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
    def __init__(self, config, callbacks):
        threading.Thread.__init__(self)
        self.config = config
        self.callbacks = callbacks
        self.check_health = self.config.check_health
        self.state = HealthMonitor.INIT
        self.should_run = True
    def monitor(self):
        try:
            result = self.check_health()
        except:
            result = HealthMonitor.NG
        if self.state != result:
            self.state = result
            for cb in self.callbacks:
                cb.on_state_change(result)
    def run(self):
        while self.should_run:
            self.monitor()
            time.sleep(self.config.get("healthcheck_interval",5))
        print "monitor thread stopped."

from kazoo.client import KazooClient
from kazoo.client import KazooState
from kazoo.retry import KazooRetry
class Elector(threading.Thread):
    ACT, SBY = 1,2
    def __init__(self, config, callbacks):
        threading.Thread.__init__(self)
        self.config = config
        self.callbacks = callbacks
        self.should_run = True
        self.in_entry = False
        self.state = Elector.SBY
        self.zk = KazooClient(hosts=self.config.get("connection_string","127.0.0.1:2181"))
        self.zk.add_listener(self.zk_listener)
        self.zk.start()
        self.id = self.config.get("id")
        self.lock = self.zk.Lock(self.config.get("lock_znode","/zha-lock"), id)
        self.abcpath = self.config.get("abc_znode","/zha-abc")
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
        if not self.zk.exists(self.abcpath):
            self.zk.create(self.abcpath, self.id)
            return
        data, stat = self.zk.get(self.abcpath)
        if data.strip()==self.id:
            return
        else:
            for cb in self.callbacks:
                cb.on_fence()
            self.zk.set(self.abcpath, self.id)
    def zk_delete_my_abc(self):
        assert self.zk.exists(self.abcpath)
        data, stat = self.zk.get(self.abcpath)
        assert data.strip() == self.id
        self.zk.delete(self.abcpath)
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
            time.sleep(self.config.get("elector_interval",3))
            return
        if self.state == Elector.ACT:
            time.sleep(self.config.get("elector_interval",3))
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

