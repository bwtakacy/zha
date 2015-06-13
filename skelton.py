#!/bin/env python
import zha
import os
import subprocess
import time

from functools import wraps
def returns_minusone_on_Exception(orig_func):
    @wraps(orig_func)
    def func(*args,**kwards):
        try:
            ret = orig_func(*args,**kwards)
        except Exception, e:
            ret = -1
            print e
        return ret
    return func

def returns_zero_on_Exception(orig_func):
    @wraps(orig_func)
    def func(*args,**kwards):
        try:
            ret = orig_func(*args,**kwards)
        except Exception, e:
            ret = 0
            print e
        return ret
    return func

class Config(object):
    """This is skelton config class for ZHA.  Users MUST implement/overwrite the following methods:

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
    """

    def __init__(self):
        self.properties = {
                "id": "hostA",
                #"connection_string":  "127.0.0.1:2181",
                #"lock_znode":         "/zha-lock",
                #"abc_znode":          "/zha-abc",
                #"cluster_znode":      "/zha-state",
                #"clustercheck_interval":   3,
                #"healthcheck_interval":    5,
                #"elector_interval":   3,
                #"health_dms_timeout":   10,
                #"cluster_dms_timeout":   10,
        }

    def get(self,key,default=None):
        return self.properties.get(key,default)

    @returns_zero_on_Exception
    def check_health(self):
        return self._trigger_script_with_timeout(10, "impl/check_health.sh")

    @returns_minusone_on_Exception
    def become_active(self):
        return self._trigger_script_with_timeout(10, "./impl/on_active.sh")

    @returns_minusone_on_Exception
    def become_clustered(self):
        return self._trigger_script_with_timeout(10, "./impl/on_clustered.sh")

    @returns_minusone_on_Exception
    def become_declustered(self):
        return self._trigger_script_with_timeout(10, "./impl/on_declustered.sh")

    @returns_minusone_on_Exception
    def become_standby_from_active(self):
        return self._trigger_script_with_timeout(10, "./impl/on_standby.sh")

    @returns_minusone_on_Exception
    def trigger_fence(self):
        return self._trigger_script_with_timeout(10, "./impl/on_fence.sh")

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
