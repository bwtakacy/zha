if [ -e /var/lib/pgsql/9.4/data/recovery.conf ]
then
  /usr/pgsql-9.4/bin/psql -c "select 1" > /dev/null 2>&1
  if [ $? = 0 ] ; then exit 3; fi
  exit 0
fi
ret=0
psql -c "select 1" > /dev/null 2>&1
if [ $? = 0 ] ; then ret=1; fi
state=`psql -c "select sync_state from pg_stat_replication" -t 2> /dev/null`
if [ -z "$state" ] ; then exit $ret; fi
[[ $state == 'async' || $state == 'sync' ]] ; exit 2
exit 0
