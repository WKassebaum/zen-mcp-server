# Zen CLI Distribution Guide

## Installation Methods

### Method 1: pipx (Recommended)
The best way to install Python CLI tools - creates isolated environments automatically:

```bash
# Install pipx if needed
brew install pipx
pipx ensurepath

# Install from local directory (for development)
cd /path/to/zen-cli
pipx install . --force

# Or install from GitHub (once published)
pipx install git+https://github.com/yourusername/zen-cli.git

# Or install from PyPI (once published)
pipx install zen-cli
```

### Method 2: Direct pip install
```bash
# Install from local directory
pip install /path/to/zen-cli

# Or from GitHub
pip install git+https://github.com/yourusername/zen-cli.git
```

### Method 3: Homebrew (Future)
Once we create a Homebrew formula:
```bash
brew tap yourusername/zen-cli
brew install zen-cli
```

## Configuration

After installation, the CLI will automatically:
1. Create `~/.zen-cli/` directory
2. Look for `.env` file with API keys
3. Load environment variables on startup

Users need to create `~/.zen-cli/.env` with:
```env
GEMINI_API_KEY=your_actual_api_key
OPENAI_API_KEY=your_actual_api_key
```

## Publishing to PyPI

To make it installable via `pip install zen-cli`:

1. **Create PyPI account** at https://pypi.org

2. **Build the package**:
```bash
python -m pip install --upgrade build
python -m build
```

3. **Upload to PyPI**:
```bash
python -m pip install --upgrade twine
python -m twine upload dist/*
```

## Creating a Homebrew Formula

Create `zen-cli.rb`:

```ruby
class ZenCli < Formula
  include Language::Python::Virtualenv

  desc "AI-powered development assistant CLI"
  homepage "https://github.com/yourusername/zen-cli"
  url "https://files.pythonhosted.org/packages/zen-cli-0.1.0.tar.gz"
  sha256 "YOUR_SHA256_HERE"
  license "MIT"

  depends_on "python@3.11"

  resource "click" do
    url "https://files.pythonhosted.org/packages/click-8.1.0.tar.gz"
    sha256 "..."
  end

  # Add all other dependencies as resources...

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match "Zen CLI", shell_output("#{bin}/zen --version")
  end
end
```

## Distribution Checklist

- [x] Create `pyproject.toml` for modern Python packaging
- [x] Create `MANIFEST.in` to include all necessary files
- [x] Test with pipx installation
- [x] Create installation script
- [x] Set up automatic .env configuration
- [ ] Add version management
- [ ] Create GitHub Actions for automated releases
- [ ] Publish to PyPI
- [ ] Create Homebrew formula
- [ ] Add to Homebrew tap

## Advantages of this approach

1. **No repo cloning required** - Users can install directly
2. **Automatic dependency management** - pipx/pip handle all dependencies
3. **Isolated environment** - pipx prevents conflicts
4. **Global availability** - Command available from any directory
5. **Easy updates** - `pipx upgrade zen-cli`
6. **Standard Python packaging** - Works with all Python tools

## For End Users

Simple installation instructions:

```bash
# One-time setup
brew install pipx
pipx ensurepath

# Install Zen CLI
pipx install zen-cli

# Configure API keys
echo "GEMINI_API_KEY=your_key" >> ~/.zen-cli/.env
echo "OPENAI_API_KEY=your_key" >> ~/.zen-cli/.env

# Start using
zen chat "Hello!"
```