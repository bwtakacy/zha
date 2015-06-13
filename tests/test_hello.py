import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__),".."))
import zha
import skelton
import threading
import thread
import time
import itertools

def trigger_zha(z,timeout=30):
    def run(obj):
        obj.mainloop()
    thread.start_new_thread(run,(z,),{})
    time.sleep(timeout)
    z.stop()

def test_being_standby():
    def _oa():
        with open("/tmp/test_xyz","w") as f:
            f.write("aaa")
    config=skelton.Config()
    config.check_health=lambda:0
    config.become_active=_oa
    z = zha.ZHA(config)
    trigger_zha(z)
    assert not os.path.exists("/tmp/test_xyz")
    time.sleep(10)

def test_become_active():
    def _oa():
        with open("/tmp/test_aaa","w") as f:
            f.write("aaa")
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=_oa
    z = zha.ZHA(config)
    trigger_zha(z)
    assert open("/tmp/test_aaa").read() == "aaa"
    time.sleep(10)

def test_occasional_healtherror():
    health_seq = itertools.cycle([3,3,3,3,0]) 
    def _ch():
        return health_seq.next()
    def _oa():
        with open("/tmp/test_abc","w") as f:
            f.write("aaa")
    def _os():
        with open("/tmp/test_def","w") as f:
            f.write("dead")
    config=skelton.Config()
    config.check_health=_ch

    config.become_active =_oa
    config.become_standby_from_active =_os
    z = zha.ZHA(config)
    trigger_zha(z,120)
    assert open("/tmp/test_abc").read() == "aaa"
    assert not os.path.exists("/tmp/test_def")
    time.sleep(10)
