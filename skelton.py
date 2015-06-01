#!/bin/env python
import zha
import os
import itertools
import subprocess
import time

def returns_minusone_on_Exception(orig_func):
    def func(*args,**kwards):
        try:
            ret = orig_func(*args,**kwards)
        except Exception, e:
            ret = -1
            print e
        return ret
    return func

class Config(object):
    """This is skelton config class for ZHA.  Users MUST implement/overwrite the following methods:

    get(keyname, defaultvalue): 
        returns a specified value if keyname exists, otherwise defaultvalue.
        keyname="id" is REQUIRED to specify zha identity, which MUST be unique among cluster.
        Another keys and default values zha uses are listed in skelton.py.
    check_health(state): 
        returns 0 for OK, or another integer for NG and throws no exception.
        This method is adviced not to block for a long time so that health monitor thread
        can check multiple times within "health_dms_timeout", which can rescure the situation of
        ocasional failure of cheak_health(). When invoked with state=1, then do health check for ACT,
        and with state=2, do healthcheck for SBY.
    trigger_active() : 
        returns 0 for OK, another integer for NG, and throws no exception.
        This method is invoked when this zha is eligible to become active.
        When this method returns 0, zha considers failover has completed and sets its
        status active, otherwise keeps its status standby. For NG, all cleanup codes for 
        another zha invoking trigger_active is REQUIRED to be implemented.
    trigger_standby():
        returns 0 for OK, another integer for NG, and throws no exception.
        This method is invoked when this process has ceased to be active, such as
        health monitor failure or zookeeper connection problem.
        When this method returns NG, zha considers cleanup should be need for another zha becoming active
        , which will result in being fenced by another zha.
    trigger_fence(): 
        returns 0 for OK, another integer for NG, and throws no exception.
        This methods will be invoked only when this zha is eligible to become active 
        AND the previous active zha is not did not cleanly retire 
        AND the previous active zha is not this zha.
        This SHOULD always succeed, otherwise this zha stops failover.
    """

    def __init__(self):
        self.health_seq = itertools.cycle([0,0,0,1,1,1,0,0,1,0,0,0]) 
        self.properties = {
                "id": "hostA",
                #"connection_string":  "127.0.0.1:2181",
                #"lock_znode":         "/zha-lock",
                #"abc_znode":          "/zha-abc",
                #"recheck_interval":   5,
                #"healthcheck_interval":5,
                #"elector_interval":   3,
                #"health_dms_timeout":   10,

                "vip":                  "127.0.0.2/8",
                "iface":                "lo"
        }
        self._check()
    def get(self,key,default=None):
        return self.properties.get(key,default)

    @returns_minusone_on_Exception
    def check_health(self, estate):
        return self.health_seq.next()
        #return self._trigger_script_with_timeout(10, "impl/check_health.sh", estate)

    @returns_minusone_on_Exception
    def trigger_active(self):
        vip   = self.get("vip","")
        iface = self.get("iface","")
        return self._trigger_script_with_timeout(10, "./impl/on_active.sh", vip, iface)

    @returns_minusone_on_Exception
    def trigger_standby(self):
        vip   = self.get("vip","")
        iface = self.get("iface","")
        return self._trigger_script_with_timeout(10, "./impl/on_standby.sh", vip, iface)

    @returns_minusone_on_Exception
    def trigger_fence(self):
        myid = self.get("id","")
        return self._trigger_script_with_timeout(10, "./impl/on_fence.sh", myid)

    def _check(self):
        assert self.get("id",False)
        assert "check_health" in dir(self)
        assert "trigger_active" in dir(self)
        assert "trigger_standby" in dir(self)
        assert "trigger_fence" in dir(self)

    def _trigger_script_with_timeout(self,timeout, fname,*args):
        popen_args = ["/bin/bash",fname]
        popen_args.extend(args)
        popen = subprocess.Popen(popen_args)
        t = 0
        while t < timeout:
            popen.poll()
            if popen.returncode is not None:
                return popen.returncode
            time.sleep(0.2)
            t += 0.2
        raise Exception("Script timeout")

if __name__ == '__main__':
    obj = zha.ZHA(Config())
    obj.mainloop() #Ctrl+C or SIGINT to stop this program
