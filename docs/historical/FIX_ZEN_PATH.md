# Fix for "zen command not found" Issue

## Quick Fix (Run this in the terminal where zen is missing):

```bash
# Add zen to PATH for current session
export PATH="$PATH:/Users/wrk/Library/Python/3.13/bin"

# Test that it works
zen --version
```

## Permanent Fix (Add to shell configuration):

```bash
# Add to ~/.zshrc for permanent access
echo 'export PATH="$PATH:/Users/wrk/Library/Python/3.13/bin"' >> ~/.zshrc

# Reload shell configuration
source ~/.zshrc

# Verify it works
zen --version
```

## Alternative: Create a symbolic link (System-wide access):

```bash
# Create symlink in /usr/local/bin (may require sudo)
sudo ln -sf /Users/wrk/Library/Python/3.13/bin/zen /usr/local/bin/zen

# Now zen should work from any terminal
zen --version
```

## Verify Installation:

The zen CLI is already installed at:
- **Location**: `/Users/wrk/Library/Python/3.13/bin/zen`
- **Version**: 5.13.0

You just need to add it to your PATH or create a symlink.

## For the Other Claude Terminal:

Run ONE of these options:

### Option 1: Quick (Current Session Only)
```bash
export PATH="$PATH:/Users/wrk/Library/Python/3.13/bin"
```

### Option 2: Permanent (Recommended)
```bash
echo 'export PATH="$PATH:/Users/wrk/Library/Python/3.13/bin"' >> ~/.zshrc && source ~/.zshrc
```

### Option 3: System-wide
```bash
sudo ln -sf /Users/wrk/Library/Python/3.13/bin/zen /usr/local/bin/zen
```

After any of these, the zen command should work:
```bash
zen codereview --files "packages/*/src/**/*.ts" --type all --model gemini-pro
```