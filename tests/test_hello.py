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

def trigger_zha(z,timeout=30):
    def run(obj):
        obj.mainloop()
    thread.start_new_thread(run,(z,),{})
    time.sleep(timeout)
    z.stop()

def test_being_standby():
    obj = type('',(),{})
    obj.flg = False
    def _oa():
        obj.flg = True
        return 0
    config=skelton.Config()
    config.check_health=lambda:0
    config.become_active=_oa
    z = zha.ZHA(config)
    trigger_zha(z)
    assert obj.flg is False
    time.sleep(10)

def test_become_active():
    obj = type('',(),{})
    obj.flg = False
    def _oa():
        obj.flg = True
        return 0
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=_oa
    z = zha.ZHA(config)
    trigger_zha(z)
    assert obj.flg
    time.sleep(10)

def test_occasional_healtherror():
    health_seq = itertools.cycle([3,3,3,3,0]) 
    obj = type('',(),{})
    obj.flg, obj.flg2 = False, False
    def _ch():
        return health_seq.next()
    def _oa():
        obj.flg = True
        return 0
    def _os():
        obj.flg2 = True
        return 0
    config=skelton.Config()
    config.check_health=_ch
    config.become_active =_oa
    config.become_standby_from_active =_os
    z = zha.ZHA(config)
    trigger_zha(z,120)
    assert obj.flg and (obj.flg2 is False)
    time.sleep(10)

def test_handle_abc():
    subprocess.call("zookeeper-client create /zha-abc dummy",shell=True)
    obj = type('',(),{})
    obj.flg = False
    def _f():
        obj.flg = True
        return 0
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=lambda:0
    config.trigger_fence = _f
    z = zha.ZHA(config)
    trigger_zha(z)
    assert obj.flg
    time.sleep(10)

def test_handle_abc2():
    subprocess.call("zookeeper-client create /zha-abc hostA",shell=True)
    obj = type('',(),{})
    obj.flg = False
    def _f():
        obj.flg = True
        return 0
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=lambda:0
    config.trigger_fence = _f
    z = zha.ZHA(config)
    trigger_zha(z)
    assert obj.flg is False
    time.sleep(10)

def test_duplicate():
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active=lambda:0
    z = zha.ZHA(config)
    with pytest.raises(Exception) as exc:
        z2 = zha.ZHA(config)
    assert "Same name zha seems to exist already, Exit." in str(exc.value)
    trigger_zha(z)
    time.sleep(10)

def test_reentrant():
    obj = type('',(),{})
    obj.act=[]
    obj.sby=[]
    health_seq = itertools.cycle([3,3,3,3,1,1,1,1]) 
    def _ch():
        return health_seq.next()
    def _oa():
        obj.act.append(1)
        return 0
    def _os():
        obj.sby.append(1)
        return 0
    config=skelton.Config()
    config.check_health=_ch
    config.become_active =_oa
    config.become_standby_from_active =_os
    z = zha.ZHA(config)
    trigger_zha(z,300)
    assert obj.act.__len__() > 2 and obj.sby.__len__() > 2
    time.sleep(10)

def test_fail_activate():
    obj = type('',(),{})
    obj.act=[]
    def _oa():
        obj.act.append(1)
        return 1
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active =_oa
    z = zha.ZHA(config)
    trigger_zha(z,120)
    assert obj.act.__len__() > 10 
    time.sleep(10)

def test_fail_fence():
    subprocess.call("zookeeper-client create /zha-abc dummy",shell=True)
    obj = type('',(),{})
    obj.flg = False
    def _oa():
        obj.flg = True
        return 0
    def _f():
        return 1
    config=skelton.Config()
    config.check_health=lambda:3
    config.become_active =_oa
    config.trigger_fence = _f
    z = zha.ZHA(config)
    trigger_zha(z)
    assert obj.flg is False
    subprocess.call("zookeeper-client delete /zha-abc",shell=True)
    time.sleep(10)

def test_unexpected_exception():
    def _ch():
        raise Exception("")
    def _oa():
        return 0
    config=skelton.Config()
    config.check_health=_ch
    config.become_active =_oa
    z = zha.ZHA(config)
    ret = z.mainloop()
    assert ret == 1
    time.sleep(10)

