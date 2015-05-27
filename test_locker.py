from kazoo.client import KazooClient

ZNODE_LOCK = "/zha_lock"
zk = KazooClient(hosts='127.0.0.1:2181')
lock = zk.Lock(ZNODE_LOCK)
zk.start()
lock.acquire()
print "locked!"
raw_input("Press enter to exit:")
lock.release()
zk.stop()
