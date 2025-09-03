# Zen CLI Installation Fix

## Issue
The `zen` command isn't being found even though it's installed and the directory is in PATH.

## Solution Options

### Option 1: Create an alias (Quick Fix)
Add this to your `~/.zshrc` or `~/.bashrc`:
```bash
alias zen='/Users/wrk/Library/Python/3.13/bin/zen'
```

Then reload:
```bash
source ~/.zshrc  # or ~/.bashrc
```

### Option 2: Create a symlink (Better)
```bash
ln -s /Users/wrk/Library/Python/3.13/bin/zen /usr/local/bin/zen
```

### Option 3: Fix PATH ordering (Best)
The issue is that `/Users/wrk/Library/Python/3.13/bin` is at the end of your PATH. Move it earlier:

In your `~/.zshrc` or `~/.bashrc`, change:
```bash
export PATH="$PATH:/Users/wrk/Library/Python/3.13/bin"
```

To:
```bash
export PATH="/Users/wrk/Library/Python/3.13/bin:$PATH"
```

### Option 4: Reinstall with pipx (Cleanest)
```bash
# First uninstall current version
pip3 uninstall zen-cli

# Install pipx if not already installed
brew install pipx
pipx ensurepath

# Install zen-cli with pipx (handles PATH automatically)
pipx install /Users/wrk/WorkDev/MCP-Dev/zen-cli
```

## Testing
After any of these fixes, test with:
```bash
zen --version
# Should output: zen, version 1.0.0
```

## Current Working Command
Until fixed, you can always use:
```bash
/Users/wrk/Library/Python/3.13/bin/zen [command] [args]
```