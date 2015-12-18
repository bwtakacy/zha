if [ -e ${PGDATA}/recovery.conf ]
then
  psql -c "select 1" > /dev/null 2>&1
  if [ $? = 0 ] ; then exit 3; fi
  exit 0
fi
psql -c "select 1" > /dev/null 2>&1
if [ $? = 0 ] ; then exit 2; fi
exit 0
