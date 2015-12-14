if [ -e /home/postgres/pg_data/9.4/recovery.conf ]
then
  /usr/local/pgsql/9.4/bin/psql -c "select 1" > /dev/null 2>&1
  if [ $? = 0 ] ; then exit 3; fi
  exit 0
fi
/usr/local/pgsql/9.4/bin/psql -c "select 1" > /dev/null 2>&1
if [ $? = 0 ] ; then exit 2; fi
exit 0
