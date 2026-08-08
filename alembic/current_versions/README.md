# Current migration chain

This directory contains the migration chain used by Alembic.

The former revisions remain under `alembic/versions/` as an audit archive. Their
first revision was an empty marker that assumed an externally created ORM schema,
so that chain could not bootstrap a genuinely empty PostgreSQL database. The
active chain is a static, squashed initial schema at the same deployed head
revision. Existing databases already stamped at that head remain compatible,
while new databases can run `alembic upgrade head` without `create_all` or a
manual stamp.
