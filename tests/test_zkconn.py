import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__),".."))
import zha
import skelton
import threading
import thread
import time
import itertools
import subprocess
import pytest
from kazoo.client import KazooClient

def test_zkconnlost():
    obj = type('',(),{})
    obj.sc = [] 
    def _oa():
        obj.sc.append(1)
        return 0
    def _os():
        obj.sc.append(-1)
        return 0
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=_oa
    config.become_standby_from_active=_os
    z = zha.ZHA(config)

    class Runner(threading.Thread):
        def __init__(self,z):
            self.z = z 
            threading.Thread.__init__(self)
        def run(self):
            self.z.mainloop()

    r = Runner(z)
    r.start()
    time.sleep(30)
    subprocess.call("sudo service zookeeper-server stop",shell=True)
    time.sleep(30)
    subprocess.call("sudo service zookeeper-server start",shell=True)
    time.sleep(60)
    z.stop()
    r.join()
    assert obj.sc[:3] == [1,-1,1]
    time.sleep(10)
