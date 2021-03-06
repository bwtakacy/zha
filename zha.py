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

__version__ = 'devel'
import logging
logging.basicConfig(format='%(asctime)-15s %(message)s', level=logging.INFO)
logger = logging.getLogger('zha')

import signal
import sys
import threading
import time

from kazoo.client import KazooClient
from kazoo.client import KazooState
from kazoo.exceptions import LockTimeout

class ZHA(object):
    def __init__(self, config):
        self.config = config
        #state
        self.last_health_ok_act = 0
        self.last_health_ok_sby = 0
        self.state = "SBY:UNKNOWN"
        self.is_clustered = False
        #threads
        self.hmonitor = HealthMonitor(self)
        self.cmonitor = ClusterMonitor(self)
        self.elector = Elector(self)
        signal.signal(signal.SIGINT, self.on_sigint)
        self.retcode = 0
    def on_sigint(self,sig,frm):
        self.should_run = False
    def stop(self):
        self.should_run = False
    def mainloop(self):
        self.should_run = True
        self.threads = [self.hmonitor, self.cmonitor, self.elector]
        for th in self.threads:
            th.start()
        while self.should_run:
            now = time.time()
            self.report_status()
            time.sleep(3) #recheck() is invoked by monitors
        self._finalize()
        return self.retcode
    def _finalize(self):
        self.should_run = False
        for th in self.threads:
            th.should_run = False
        for th in self.threads:
            th.join()
        logger.info("ZHA: main thread stopped.")
    def report_status(self):
        report_str = ""
        #state
        mode = self.state.split(":")[0]
        report_str += "State=("+self.state
        if mode == "ACT":
            if self.is_clustered: report_str += ":CLUSTERED)"
            else:                 report_str += ":DECLUSTERED)"
        else:
            report_str += ")"
        #health
        ttl_act = max([0, int(self.config.get("health_dms_timeout",10)-time.time()+self.last_health_ok_act)])
        ttl_sby = max([0, int(self.config.get("health_dms_timeout",10)-time.time()+self.last_health_ok_sby)])
        report_str += " TTL=(%d,%d)"%(ttl_act,ttl_sby)
        report_str += " Threads=("
        is_ok = True
        for th in [self.hmonitor, self.cmonitor, self.elector]:
            if th.is_alive():
                report_str += "ON,"
            else:
                report_str += "OFF,"
                is_ok = False
        report_str += ")"
        logging.info(report_str)
        if is_ok is False:
            logger.error("monitor/elector thread ended unexpectedly. Exit")
            self.retcode = 1
            self._finalize()
        return report_str
    def set_state(self, state):
        self.state = state
    def recheck(self):
        mode = self.state.split(":")[0]
        if time.time() - self.last_health_ok_act < self.config.get("health_dms_timeout",10):
            self.elector.in_entry_act = True
            if mode == "ACT":
                self.set_state("ACT:HEALTHY")
        else: #dms timeout
            self.elector.in_entry_act = False
            if mode == "ACT":
                self.set_state("ACT:UNHEALTHY")
        if time.time() - self.last_health_ok_sby < self.config.get("health_dms_timeout",10):
            self.elector.in_entry_sby = True
            if mode == "SBY":
                self.set_state("SBY:HEALTHY")
        else: #dms timeout
            self.elector.in_entry_sby = False
            if mode == "SBY":
                self.set_state("SBY:UNHEALTHY")

class HealthMonitor(threading.Thread):
    """periodically checks resource health. This changes ZHA.last_health_ok_act/sby"""
    SBY_OK,ACT_OK = 1,2
    def __init__(self,zha):
        threading.Thread.__init__(self)
        self.zha = zha
        self.should_run = True
    def monitor(self):
        state = self.zha.config.check_health()
        if state & HealthMonitor.ACT_OK == HealthMonitor.ACT_OK:
            self.zha.last_health_ok_act = time.time()
        if state & HealthMonitor.SBY_OK == HealthMonitor.SBY_OK:
            self.zha.last_health_ok_sby = time.time()
        logger.debug("ZHA: latest Health state is: %d" %(state))
        self.zha.recheck()
    def run(self):
        while self.should_run:
            self.monitor()
            time.sleep(self.zha.config.get("healthcheck_interval",5))
        logger.info("health monitor thread stopped.")

class ClusterMonitor(threading.Thread):
    """periodically checks cluster member.
    This class is delegated to change state between ACT clustered and ACT declustered."""
    def __init__(self, zha):
        threading.Thread.__init__(self)
        self.zha = zha
        self.should_run = True
        self.zk = KazooClient(hosts=self.zha.config.get("connection_string","127.0.0.1:2181"), logger=logger)
        self.zk.add_listener(self._zk_listener)
        self.zk.start()
        self.zroot = self.zha.config.get("cluster_znode","/zha-state")
        self.znode = self.zroot + "/" + self.zha.config.get("id") 
        self._zk_register(first=True)
        self.not_alone = None
    def run(self):
        while self.should_run:
            time.sleep(self.zha.config.get("clustercheck_interval",3))
            self.zha.recheck()
            self._zk_register()
            self.check_cluster()
            self.trigger()
        if self.zha.is_clustered:
            self.zha.config.become_declustered()
            self.zha.is_clustered = False
        self.zk.delete(self.znode)
        logger.info("cluster monitor thread stopped.")
    def check_cluster(self):
        try:
            count = 0
            chs = self.zk.get_children(self.zroot)
            for ch in chs:
                data, stats = self.zk.get(self.zroot+"/"+ch)
                if data.strip()=="SBY:HEALTHY" and ch != self.zha.config.get("id"):
                    count += 1
            if count != 0:
                self.not_alone = time.time()
            logger.debug("healthy sbys: %d"%(count,))
        except Exception,e:
            logger.warn("check cluster failed. Try next time.%s"%e)
    def trigger(self):
        if self.zha.state != "ACT:HEALTHY":
            return
        if self.zha.is_clustered:
            if time.time()-self.not_alone > self.zha.config.get("cluster_dms_timeout",10):
                if self.zha.config.become_declustered() == 0:
                    logger.info("successfully declustered")
                    self.zha.is_clustered = False
                else:
                    logger.info("declustering failed..")
                return
        elif self.zha.is_clustered is False:
            if self.not_alone is None:
                return
            if time.time()-self.not_alone < self.zha.config.get("cluster_dms_timeout",10):
                if self.zha.config.become_clustered() == 0:
                    logger.info("successfully become clustered")
                    self.zha.is_clustered = True
                else:
                    logger.info("clustering failed..")
                return
    def _zk_listener(self,zkstate):
        logger.info("zookeeper connection state changed %s"%(zkstate,) )
        if zkstate == KazooState.LOST:
            self._zk_register()
        elif zkstate == KazooState.SUSPENDED:
            return
        else:
            return
    def _zk_register(self,first=False):
        try:
            if not self.zk.exists(self.zroot):
                self.zk.create(self.zroot,"",makepath=True)
            if self.zk.exists(self.znode):
                if first:
                    logger.error("Same name zha seems to exist already, Exit.")
                    raise AlreadyExistException("Same name zha seems to exist already, Exit.")
                self.zk.set(self.znode,self.zha.state)
            else:
                self.zk.create(self.znode,self.zha.state, ephemeral=True)
        except AlreadyExistException,e:
            raise e
        except Exception, e:
            logger.warn("state-update failed. Try next time.%s"%e)

class AlreadyExistException(Exception):
    pass

class Elector(threading.Thread):
    LOCKING, NOLOCK = 1,2
    def __init__(self, zha):
        threading.Thread.__init__(self)
        self.zha = zha
        self.should_run = True
        self.in_entry_act = False
        self.in_entry_sby = False

        self.state = Elector.NOLOCK
        self.zk = KazooClient(hosts=self.zha.config.get("connection_string","127.0.0.1:2181"), logger=logger)
        self.zk.add_listener(self.zk_listener)
        self.zk.start()
        self.id = self.zha.config.get("id")
        self.lock = self.zk.Lock(self.zha.config.get("lock_znode","/zha-lock"), self.id)
        self.abcpath = self.zha.config.get("abc_znode","/zha-abc")

    #callbacks
    def on_become_active(self):
        if self.zha.config.become_active() == 0:
            logger.info("successfully become active")
            self.zha.set_state("ACT:HEALTHY")
            return True
        else:
            logger.info("activation failed..")
            return False

    def on_become_active_to_standby(self):
        self.zha.set_state("SBY:UNKNOWN") # state changed to SBY anyway.
        if self.zha.config.become_standby_from_active() == 0:
            logger.info("successfully become standby")
            return True
        else:
            logger.info("could not retire cleanly...")
            return False

    def on_fence(self):
        if self.zha.config.trigger_fence() == 0:
            logger.info("shooted the node")
            return True
        else:
            logger.info("could not retire cleanly...")
            return False

    def run(self):
        while self.should_run:
            self.in_elector_loop()
            time.sleep(self.zha.config.get("elector_interval",3))
        self.retire()
        self.zk.stop()
        logger.info("elector thread stopped.")

    def in_elector_loop(self):
        if self.zk.state != KazooState.CONNECTED:
            # zk listener will callback on LOST, so no need to call self.retire(),
            # but it takes a bit long to be LOST. Mostly other zha will fence me.
            return
        #for locker
        if self.state == Elector.LOCKING:
            if self.in_entry_act is False:
                self.retire()
                return
            return
        #for waiters 
        try:
            lock_result = self.lock.acquire(timeout=self.zha.config.get("elector_interval",3))
        except LockTimeout:
            self.retire()
            logger.info("lock timeout")
            return
        if self.in_entry_act is False:
            self.retire()
            return
        if self.handle_abc() is False:
            self.retire()
            return
        if self.on_become_active() is False:
            self.zk_delete_my_abc()
            self.retire()
            return
        # if reached here, all done with lock
        self.state = Elector.LOCKING

    def zk_listener(self,zkstate):
        logger.info("zookeeper connection state changed %s"%(zkstate,) )
        if zkstate == KazooState.LOST:
            logger.info("(connection to zookeeper is lost/closed)")
            if self.state != Elector.LOCKING:
                return
            logger.info("become standby due to zk connection problem.")
            self.on_become_active_to_standby()
            self.state = Elector.NOLOCK
        elif zkstate == KazooState.SUSPENDED:
            return
        else:
            return

    def retire(self):
        if self.state == Elector.LOCKING:
            if self.on_become_active_to_standby():
                self.zk_delete_my_abc() #dont care it succeeds or not, that is, may become standby leaving abc behind.
        self.state = Elector.NOLOCK
        self.lock.release()

    def handle_abc(self):
        if not self.zk.retry(self.zk.exists,self.abcpath):
            self.zk.retry(self.zk.create, self.abcpath, self.id)
            return True
        data, stat = self.zk.retry(self.zk.get, self.abcpath)
        if data.strip()==self.id:
            return True
        else:
            if self.on_fence() is False:
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

