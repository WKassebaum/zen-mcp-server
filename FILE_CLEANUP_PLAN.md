# File Cleanup Plan for zen-mcp-server

## 🔴 CRITICAL ISSUE: README Missing Token Optimization!
The main README.md doesn't mention our 95% token optimization achievement - this is our biggest feature!

## Files to KEEP and COMMIT

### Important Documentation (6 files)
```bash
# These document our major achievements
CMAF_CLI_REPORT.md         # Comprehensive CLI development report
ZEN_CLI_CMAF_PLAN.md       # CLI development plan with CMAF
TOKEN_OPTIMIZATION_ACHIEVEMENT.md  # Documents 95% reduction
TOKEN_OPTIMIZATION_AB_TEST.md      # A/B testing documentation
DEPLOYMENT_GUIDE.md        # Deployment instructions
test_stage2_fix.py         # The test that proved our fix works
```

### Configuration Files (1 file)
```bash
.codeindexignore           # For semantic code indexing
```

## Files to DELETE

### Test Scripts (20+ files)
```bash
# All temporary test files
test_client.py
test_mcp_*.py
test_simple_mcp.py
test_two_stage_flow.py
quick_*.py
debug_*.py
minimal_mcp_test.py
verify_deployment.py
```

### Log Backups (9 files)
```bash
logs_backup_*.txt          # All old log backups
```

### Generated Files (2 files)
```bash
README.pdf
README_COMPREHENSIVE.pdf
```

### Shell Scripts (4 files)
```bash
ab_test_control.sh
generate_test_load.sh
run_baseline_tests.sh
quick_start.sh
```

### Other Test Files
```bash
baseline_commands.txt
server_integration.patch
zen_precommit.changeset
analyze_telemetry.py
fix_*.py
```

## Recommended Actions

1. **UPDATE README.md** - Add token optimization section
2. **COMMIT important docs** - Save achievement documentation
3. **DELETE test files** - Clean up workspace
4. **TAG documentation** - Mark as v5.12.0-docs

## Quick Commands

### To save important files:
```bash
git add CMAF_CLI_REPORT.md ZEN_CLI_CMAF_PLAN.md TOKEN_OPTIMIZATION_*.md DEPLOYMENT_GUIDE.md test_stage2_fix.py .codeindexignore
git commit -m "docs: Add token optimization documentation and CLI plans"
```

### To clean up:
```bash
# Remove test files
rm test_*.py quick_*.py debug_*.py minimal_mcp_test.py verify_deployment.py

# Remove logs
rm logs_backup_*.txt

# Remove PDFs and misc
rm *.pdf *.patch *.changeset

# Remove test scripts
rm ab_test_control.sh generate_test_load.sh run_baseline_tests.sh quick_start.sh
```