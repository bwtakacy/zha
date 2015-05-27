import zha
import itertools
class DummySystem(object):
    """This is sample class for ZHA.

    Users must implement the following methods.

    get_id(): returns cluster-unique string (i.e. hostname)
    check_health(): returns 0 for OK, returns 1 for NG, never
    trigger_active() : methods to be called when state changed 
                       from standby to active (i.e. attach VIP and broadcast garp)
    trigger_standby(): methods to be called when state changed 
                       from standby to active (i.e. detach VIP)
    trigger_fence()  : methods to be called only when state changed 
                       from standby to active and the previous active
                       does not cleanly retired.
    """

    def __init__(self):
        o,x = zha.HealthMonitor.OK, zha.HealthMonitor.NG
        self.health_seq = itertools.cycle([o,o,o,o,o,o,o,o,x,x,x,x,x,x,x,o,o,o,o,o,o,o]) 
    def get_id(self):
        return "test"
    def check_health(self):
        h = self.health_seq.next()
        print h,
        return h
    def trigger_active(self):
        print "script:: attached VIP and send garp"
    def trigger_standby(self):
        print "script:: detached VIP if exists"
    def trigger_fence(self):
        print "script:: exec ipmitool....done"

obj = zha.ZHA(DummySystem())
obj.mainloop()
