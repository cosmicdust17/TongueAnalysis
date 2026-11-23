-- STEP 1: execute as a MySQL administrator. This script does not drop existing data.
CREATE DATABASE IF NOT EXISTS tongue_analysis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE tongue_analysis;
-- Next: run 01_schema.sql and then `alembic stamp head`, OR run `alembic upgrade head`.
-- Docker Compose creates tongue_app and grants access using the generated environment password.
