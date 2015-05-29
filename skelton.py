import zha
import itertools

class Config(object):
    """This is skelton config class for ZHA.  Users MUST implement/overwrite the following methods:

    get(keyname, defaultvalue): 
        returns a specified value if keyname exists, otherwise default value.
        keyname="id" is required to specify zha identity, which MUST be unique among cluster.
        Another keys and default values zha uses are listed in skelton.py.
    check_health(): 
        returns 0 for OK, returns 1 for NG and throws no exception.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_active() : 
        returns 0 for OK, 1 or throws exception for NG.
        This methods will be called when state change from standby to active.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_standby():
        returns 0 for OK, 1 or throws exception for NG.
        This method will be called when state change from active to standby.
        This method SHOULD NOT block for a long time, so you should implement timeout.
    trigger_fence(): 
        MUST always suceed and never throw exceptions.
        This methods will be called only when state has changed from standby to active 
        AND the previous active is not did not cleanly retire 
        AND the previous active is not the host that calls this method.
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
        }
    def get(self,key,default=None):
        return self.properties.get(key,default)
    def check_health(self):
        return self.health_seq.next()
    def trigger_active(self):
        print "script:: attached VIP and send garp"
    def trigger_standby(self):
        print "script:: detached VIP if exists"
    def trigger_fence(self):
        print "script:: exec ipmitool....done"

if __name__ == '__main__':
    obj = zha.ZHA(Config())
    obj.mainloop() #Ctrl+C or SIGINT to stop this program
