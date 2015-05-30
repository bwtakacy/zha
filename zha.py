"""
Copyright (c) 2015, @sakamotomsh
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

 * Redistributions of source code must retain the above copyright notice, this
list of conditions and the following disclaimer.

 * Redistributions in binary form must reproduce the above copyright notice,
this list of conditions and the following disclaimer in the documentation
and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""
import threading
import time
import signal
from kazoo.client import KazooClient
from kazoo.client import KazooState
from kazoo.retry import KazooRetry

class ZHA(object):
    class HealthStateUpdateCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_state_update(self, state):
            if state == HealthMonitor.OK:
                self.zha.last_health_ok = time.time()
            print "ZHA: latest Health state is: %d" %(state)
            self.zha.recheck()
    class ElectorStateChangeCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_become_active(self):
            ret = self.zha.trigger_active()
            if ret == 0:
                print "ZHA::ElectorCallback: successfully become active"
                self.zha.election_state = Elector.ACT
                return True
            else:
                print "ZHA::ElectorCallback: activation failed.."
                return False
        def on_become_active_to_standby(self):
            ret = self.zha.trigger_standby()
            self.zha.election_state = Elector.SBY # state changed to SBY anyway.
            if ret == 0:
                print "ZHA::ElectorCallback: successfully become standby"
                return True
            else:
                print "ZHA::ElectorCallback: could not retire cleanly..."
                return False
        def on_fence(self):
            print "ZHA::ElectorCallback: shoot the node"
            self.zha.trigger_fence()
    def __init__(self, config):
        self.config = config
        self.trigger_active = config.trigger_active
        self.trigger_standby = config.trigger_standby
        self.trigger_fence = config.trigger_fence

        self.should_run = True
        self.last_health_ok = None
        self.election_state = Elector.SBY
        self.monitor = HealthMonitor(config, self.HealthStateUpdateCallback(self))
        self.elector = Elector(config, self.ElectorStateChangeCallback(self))
        self.monitor.start()
        self.elector.start()
        signal.signal(signal.SIGINT, self.on_sigint)
    def recheck(self):
        if self.last_health_ok is None:
            self.elector.leave()
            return
        if time.time() - self.last_health_ok < self.config.get("health_dms_timeout",10):
            self.elector.enter()
            return
        else: #dms timeout
            self.elector.leave()
            return
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
    def __init__(self, config, callback):
        threading.Thread.__init__(self)
        self.config = config
        self.callback = callback
        self.check_health = self.config.check_health
        self.state = HealthMonitor.INIT
        self.should_run = True
    def monitor(self):
        result = self.check_health()
        self.callback.on_state_update(result)
    def run(self):
        while self.should_run:
            self.monitor()
            time.sleep(self.config.get("healthcheck_interval",5))
        print "monitor thread stopped."

class Elector(threading.Thread):
    ACT, SBY = 1,2
    def __init__(self, config, callback):
        threading.Thread.__init__(self)
        self.config = config
        self.callback = callback
        self.should_run = True
        self.in_entry = False
        self.state = Elector.SBY
        self.zk = KazooClient(hosts=self.config.get("connection_string","127.0.0.1:2181"))
        self.zk.add_listener(self.zk_listener)
        self.zk.start()
        self.id = self.config.get("id")
        self.lock = self.zk.Lock(self.config.get("lock_znode","/zha-lock"), self.id)
        self.abcpath = self.config.get("abc_znode","/zha-abc")
    def enter(self):
        self.in_entry = True
    def leave(self):
        self.in_entry = False
    def zk_listener(self,zkstate):
        if zkstate == KazooState.LOST:
            print "(connection to zookeeper is lost/closed)"
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
            self.callback.on_fence()
            self.zk.set(self.abcpath, self.id)
    def zk_delete_my_abc(self):
        assert self.zk.exists(self.abcpath)
        data, stat = self.zk.get(self.abcpath)
        assert data.strip() == self.id
        self.zk.delete(self.abcpath)
    def zk_safe_release(self):
        if self.state == Elector.ACT:
            if self.callback.on_become_active_to_standby():
                self.zk_delete_my_abc()
            else:
                pass #,that is, become standby leaving abc behind.
        self.state = Elector.SBY
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
        lock_result = self.lock.acquire() #blocks.... and lock acquired.
        if lock_result is False:
            return
        if self.in_entry == False:
            self.zk_safe_release()
            return
        self.handle_abc() # including fencing.
        activate_result = self.callback.on_become_active()
        if activate_result is False:
            self.zk_delete_my_abc()
            self.zk_safe_release()
            time.sleep(self.config.get("elector_interval",3)) #wait a sec for another zha can lock..
            return
        # if reached here, all done with lock
        self.state = Elector.ACT
    def run(self):
        while self.should_run:
            self.in_elector_loop()
        self.zk_safe_release()
        self.zk.stop()
        print "elector thread stopped."
