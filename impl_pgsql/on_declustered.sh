rm -f ${PGDATA}/postgresql.conf
ln -s ${PGDATA}/postgresql.conf.standalone ${PGDATA}/postgresql.conf
psql -c "select pg_reload_conf()" 2> /dev/null
