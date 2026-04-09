# Pre-Deploy Checks

Run these on your **development machine** (WSL2/Linux, `python3`) before deploying to production.

## 1. Run the full test suite

```bash
python3 manage.py test
```

All tests must pass. Do not deploy with failing tests.

## 2. Test migrations against production data

```bash
python3 manage.py preflight_migrate
```

This simulates applying pending migrations against a copy of the production database. If it fails, do NOT run `migrate` on the production server — fix the migration first.

## 3. Review the diff

```bash
git log --oneline main..HEAD
git diff main --stat
```

Verify the changes are what you expect to deploy. Check that documentation (README.md, CLAUDE.md, TODOS.md) has been updated if features changed.

## 4. Confirm the branch is up to date

```bash
git pull --rebase origin main
```

Re-run tests after rebasing if there were changes.
