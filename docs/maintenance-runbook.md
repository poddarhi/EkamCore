# EkamCore Maintenance Runbook

Post-release operational procedures for v1.0.0+.

## Monitoring

### Daily Checks
- Manager app dashboard: all 10 service tiles green
- `docker compose ps` — all containers running + healthy
- Check backup ran overnight: `make backup-list`

### Weekly Checks
- Review security scan results (security.yml runs Mondays 6am UTC)
- Check disk usage: Manager > Storage
- Review any watchdog notifications received during the week

### Monthly
- Run `make soak-test-short` (8h abbreviated soak) to verify stability
- Refresh dependency audits: `pip-audit`, `pnpm audit`, `cargo audit`
- Update Docker base images if security patches released
- Verify SBOM: `scripts/sbom/generate_sbom.sh`

## Responding to Issues

### User Reports
1. Ask for diagnostics bundle (Manager > Diagnostics > Export)
2. Review `system_info.json` and `health_check.json` in the bundle
3. Check `container_logs/` for error patterns
4. No personal data is included in the bundle — safe to share

### Service Crashes
1. Watchdog auto-restarts within 5 minutes
2. If crash persists (5+ failures): `scripts/dr/container_recovery.sh`
3. If database corruption suspected: `scripts/dr/database_repair.sh --repair`
4. If all else fails: `scripts/dr/restore_from_backup.sh /backups/latest`

### Performance Degradation
1. Run `python scripts/benchmark/harness.py` — compare against baseline
2. Check container memory: `docker stats`
3. If memory growing: restart the leaking container
4. If disk full: `scripts/dr/disk_full_recovery.sh`

## Publishing Hotfixes

1. Create branch: `git checkout -b fix/v1.0.1-description`
2. Make fix with tests
3. Run: `make release-check` (full test suite)
4. Merge to main
5. Tag: `git tag v1.0.1`
6. Run: `gh workflow run release.yml -f version=1.0.1 -f release_type=stable`

## Backup Verification

- Backups run daily at 2am via launchd (configured in S15-005)
- Verify: `make backup-list` shows recent backup with non-zero size
- Test restore quarterly: `scripts/dr/restore_from_backup.sh /backups/YYYY-MM-DD --yes`
- Restore test should complete in < 15 minutes

## Dependency Updates

- Monthly: review `pip-audit` and `pnpm audit` output
- Quarterly: update minor versions of all dependencies
- Critical CVE: patch within 48 hours, publish hotfix release
