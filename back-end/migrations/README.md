# Database Migrations

This folder contains SQL schema changes and Python helpers for applying selected upgrades to existing databases. Migration filenames identify their intended sequence or feature; use the deployment instructions and root README to determine which upgrades are required for an installation.

Treat migrations as durable upgrade history. Do not edit a migration that has already been applied to a shared database; add a new migration for a later schema change.