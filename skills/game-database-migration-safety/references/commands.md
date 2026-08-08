# MySQL Migration Safety Command Reference

Use a project-owned option file or secret manager. Never put `--password=...` in commands, evidence, shell history, or process arguments.

## Read-only identity checks

```bash
mysql --defaults-extra-file=/secure/project.cnf --protocol=TCP \
  --host=127.0.0.1 --port=3307 --database=game \
  --batch --skip-column-names \
  -e "SELECT DATABASE(), @@hostname, @@port, VERSION();"
```

```sql
SELECT version FROM schema_version ORDER BY applied_at DESC LIMIT 1;
SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE();
```

## Backup and integrity

```bash
mysqldump --defaults-extra-file=/secure/project.cnf --protocol=TCP \
  --host=127.0.0.1 --port=3307 --single-transaction \
  --routines --triggers --events game > game-before-migration.sql
sha256sum game-before-migration.sql
```

```powershell
Get-Item -LiteralPath '.\game-before-migration.sql' | Select-Object FullName,Length,LastWriteTimeUtc
Get-FileHash -LiteralPath '.\game-before-migration.sql' -Algorithm SHA256
```

## Disposable dry run

Restore the backup into an isolated disposable schema or container, then run the migration there. Capture schema diff, row counts, warnings, duration, and validation-query output.

```bash
mysql --defaults-extra-file=/secure/project.cnf --protocol=TCP \
  --host=127.0.0.1 --port=3307 disposable_game < migration.sql
```

## Restore command template

```bash
mysql --defaults-extra-file=/secure/project.cnf --protocol=TCP \
  --host=127.0.0.1 --port=3307 game < game-before-migration.sql
```

## Evidence

Record target identity, observed schema version, migration hash, backup path/hash, dry-run output, validation queries, restore command, reviewer, and exact human approval scope.

Do not run migration or restore commands against a real database without explicit approval. Do not infer that port 3306 or 3307 identifies the correct project.
