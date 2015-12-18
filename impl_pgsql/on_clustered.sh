rm -f ${PGDATA}/postgresql.conf
ln -s ${PGDATA}/postgresql.conf.clustered ${PGDATA}/postgresql.conf
psql -c "select pg_reload_conf()"
