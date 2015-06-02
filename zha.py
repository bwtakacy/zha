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

import logging
FORMAT = '%(asctime)-15s %(message)s'
logging.basicConfig(format=FORMAT, level=logging.INFO)
logger = logging.getLogger('zha')

from kazoo.client import KazooClient
from kazoo.client import KazooState
from kazoo.exceptions import LockTimeout

class ZHA(object):
    class HealthStateUpdateCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_state_update(self, state):
            if state == HealthMonitor.OK:
                self.zha.last_health_ok = time.time()
            logger.info("ZHA: latest Health state is: %d" %(state))
            self.zha.recheck()
    class ElectorStateChangeCallback(object):
        def __init__(self, zha):
            self.zha = zha
        def on_become_active(self):
            if self.zha.trigger_active() == 0:
                logger.info("ZHA::ElectorCallback: successfully become active")
                self.zha.election_state = Elector.ACT
                return True
            else:
                logger.info("ZHA::ElectorCallback: activation failed..")
                return False
        def on_become_active_to_standby(self):
            self.zha.election_state = Elector.SBY # state changed to SBY anyway.
            if self.zha.trigger_standby() == 0:
                logger.info("ZHA::ElectorCallback: successfully become standby")
                return True
            else:
                logger.info("ZHA::ElectorCallback: could not retire cleanly...")
                return False
        def on_fence(self):
            if self.zha.trigger_fence() == 0:
                logger.info("ZHA::ElectorCallback: shooted the node")
                return True
            else:
                logger.info("ZHA::ElectorCallback: could not retire cleanly...")
                return False

    def __init__(self, config):
        self.config = config
        self.trigger_active  = self._deco_returns_minusone_on_Exception(config.trigger_active)
        self.trigger_standby = self._deco_returns_minusone_on_Exception(config.trigger_standby)
        self.trigger_fence   = self._deco_returns_minusone_on_Exception(config.trigger_fence)
        self.check_health    = self._deco_returns_minusone_on_Exception(config.check_health)
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
        logger.info("ZHA: main thread stopped.")
    def on_sigint(self,sig,frm):
        self.should_run = False
    def _deco_returns_minusone_on_Exception(self, orig_func):
        def func(*a,**k):
            try:    ret = orig_func(*a,**k)
            except: ret = -1
            return ret
        return func

class HealthMonitor(threading.Thread):
    OK,NG,INIT = 0,1,2
    def __init__(self, config, callback):
        threading.Thread.__init__(self)
        self.config = config
        self.callback = callback
        self.check_health = self.callback.zha.check_health
        self.state = HealthMonitor.INIT
        self.should_run = True
    def monitor(self):
        result = self.check_health(self.callback.zha.election_state)
        self.callback.on_state_update(result)
    def run(self):
        while self.should_run:
            self.monitor()
            time.sleep(self.config.get("healthcheck_interval",5))
        logger.info("monitor thread stopped.")

class Elector(threading.Thread):
    ACT, SBY = 1,2
    def __init__(self, config, callback):
        threading.Thread.__init__(self)
        self.config = config
        self.callback = callback
        self.should_run = True
        self.in_entry = False
        self.state = Elector.SBY
        self.zk = KazooClient(hosts=self.config.get("connection_string","127.0.0.1:2181"), logger=logger)
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
        logger.info("zookeeper connection state changed %s"%(zkstate,) )
        if zkstate == KazooState.LOST:
            logger.info("(connection to zookeeper is lost/closed)")
            if self.state != Elector.ACT:
                return
            logger.info("become standby due to zk connection problem.")
            self.callback.on_become_active_to_standby()
            self.state = Elector.SBY
        elif zkstate == KazooState.SUSPENDED:
            return
        else:
            return
    def handle_abc(self):
        if not self.zk.retry(self.zk.exists,self.abcpath):
            self.zk.retry(self.zk.create, self.abcpath, self.id)
            return True
        data, stat = self.zk.retry(self.zk.get, self.abcpath)
        if data.strip()==self.id:
            return True
        else:
            if self.callback.on_fence() is False:
                return False
            self.zk.retry(self.zk.set, self.abcpath, self.id)
        return True
    def zk_delete_my_abc(self):
        try:
            data, stat = self.zk.get(self.abcpath)
            assert data.strip() == self.id
            self.zk.delete(self.abcpath)
            return True
        except:
            return False
    def retire(self):
        if self.state == Elector.ACT:
            if self.callback.on_become_active_to_standby():
                self.zk_delete_my_abc() #dont care it succeeds or not.
            else:
                pass #,that is, become standby leaving abc behind.
        self.state = Elector.SBY
        self.lock.release()
    def in_elector_loop(self):
        if self.zk.state != KazooState.CONNECTED:
            # zk listener will callback on LOST, so no need to call self.retire(),
            # but it takes a bit long to be LOST. Mostly other zha will fence me.
            return
        if self.in_entry is False:
            self.retire()
            return
        if self.state == Elector.ACT:
            return
        assert self.in_entry is True and self.state == Elector.SBY
        try:
            lock_result = self.lock.acquire(timeout=self.config.get("elector_interval",3))
        except LockTimeout:
            self.retire()
            logger.info("lock timeout")
            return
        if self.handle_abc() is False:
            self.retire()
            return
        if self.callback.on_become_active() is False:
            self.zk_delete_my_abc()
            self.retire()
            return
        # if reached here, all done with lock
        self.state = Elector.ACT
    def run(self):
        while self.should_run:
            self.in_elector_loop()
            time.sleep(self.config.get("elector_interval",3))
        self.retire()
        self.zk.stop()
        logger.info("elector thread stopped.")
