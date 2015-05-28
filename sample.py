import zha
import itertools

class DummyConfig(object):
    """This is sample class for ZHA.  Users MUST implement the following methods:

    get(keyname, defaultvalue): 
        returns a specified value if keyname exists, otherwise default value.
        keyname="id" is required to specify zha identity, which MUST be unique among cluster.
        Another keys and default values zha uses are listed in sample.py.
    check_health(): 
        returns 0 for OK, returns 1 for NG and exception.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_active() : 
        returns 0 for OK, 1 for NG and exceptions.
        This methods will be called when state change from standby to active.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_standby():
        returns 0 for OK, 1 for NG and exception.
        This method will be called when state change from active to standby.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_fence(): 
        MUST always suceed and never throw exceptions.
        This methods will be called only when state has changed from standby to active 
        AND the previous active is not did not cleanly retire 
        AND the previous active is not the host that calls this method.
    """

    def __init__(self):
        o,x = zha.HealthMonitor.OK, zha.HealthMonitor.NG
        self.health_seq = itertools.cycle([o,o,o,o,o,o,o,o,x,x,x,x,x,x,x,o,o,o,o,o,o,o]) 
        self.properties = {
                "id": "hostA",
                #"connection_string":  "127.0.0.1:2181",
                #"lock_znode":         "/zha-lock",
                #"abc_znode":          "/zha-abc",
                #"recheck_interval":   5,
                #"healthcheck_interval":5,
                #"elector_interval":   3,
        }
    def get(self,key,default=None):
        return self.properties.get(key,default)
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

obj = zha.ZHA(DummyConfig())
obj.mainloop() #Ctrl+C or SIGINT to stop this program
