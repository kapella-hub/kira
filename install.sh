#!/bin/bash
set -e

# Kira Installer for macOS/Linux
# Usage: curl -sSL https://raw.githubusercontent.com/kapella-hub/kira/main/install.sh | bash

REPO="https://github.com/kapella-hub/kira.git"
MIN_PYTHON_MAJOR=3
MIN_PYTHON_MINOR=12

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

print_banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  _    _           "
    echo " | | _(_)_ __ __ _ "
    echo " | |/ / | '__/ _\` |"
    echo " |   <| | | | (_| |"
    echo " |_|\_\_|_|  \__,_|"
    echo -e "${NC}"
    echo -e "${DIM}Agentic CLI with memory & skills${NC}"
    echo ""
}

info() {
    echo -e "${BLUE}==>${NC} $1"
}

success() {
    echo -e "${GREEN}✓${NC} $1"
}

warn() {
    echo -e "${YELLOW}!${NC} $1"
}

error() {
    echo -e "${RED}✗${NC} $1"
}

check_python() {
    info "Checking Python version..."

    # Try python3 first, then python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        error "Python not found. Please install Python ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+"
        echo ""
        echo "Install Python from: https://www.python.org/downloads/"
        exit 1
    fi

    # Get version
    PYTHON_VERSION=$($PYTHON_CMD -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PYTHON_MAJOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.major)')
    PYTHON_MINOR=$($PYTHON_CMD -c 'import sys; print(sys.version_info.minor)')

    if [ "$PYTHON_MAJOR" -lt "$MIN_PYTHON_MAJOR" ] || ([ "$PYTHON_MAJOR" -eq "$MIN_PYTHON_MAJOR" ] && [ "$PYTHON_MINOR" -lt "$MIN_PYTHON_MINOR" ]); then
        error "Python ${PYTHON_VERSION} found, but ${MIN_PYTHON_MAJOR}.${MIN_PYTHON_MINOR}+ is required"
        echo ""
        echo "Install Python from: https://www.python.org/downloads/"
        exit 1
    fi

    success "Python ${PYTHON_VERSION} ($PYTHON_CMD)"
}

check_kiro() {
    info "Checking kiro-cli..."

    if command -v kiro-cli &> /dev/null || command -v kiro &> /dev/null; then
        KIRO_VERSION=$(kiro-cli --version 2>/dev/null || kiro --version 2>/dev/null || echo "unknown")
        success "kiro-cli found: ${KIRO_VERSION}"
    else
        warn "kiro-cli not found"
        echo -e "   ${DIM}kira requires kiro-cli for LLM interaction${NC}"
        echo -e "   ${DIM}Install from: https://kiro.dev${NC}"
        echo ""
    fi
}

install_kira() {
    info "Installing kira..."

    # Install with pip --user
    $PYTHON_CMD -m pip install --user --upgrade "git+${REPO}" --quiet

    success "kira installed"
}

setup_path() {
    info "Setting up PATH..."

    # Get the user's local bin directory
    USER_BIN="$HOME/.local/bin"

    # Check if already in PATH
    if [[ ":$PATH:" == *":$USER_BIN:"* ]]; then
        success "PATH already configured"
        return
    fi

    # Detect shell and profile file
    SHELL_NAME=$(basename "$SHELL")
    case "$SHELL_NAME" in
        zsh)
            PROFILE="$HOME/.zshrc"
            ;;
        bash)
            if [ -f "$HOME/.bash_profile" ]; then
                PROFILE="$HOME/.bash_profile"
            else
                PROFILE="$HOME/.bashrc"
            fi
            ;;
        *)
            PROFILE="$HOME/.profile"
            ;;
    esac

    # Add to profile if not already there
    PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'

    if [ -f "$PROFILE" ] && grep -q '\.local/bin' "$PROFILE"; then
        success "PATH export already in $PROFILE"
    else
        echo "" >> "$PROFILE"
        echo "# Added by kira installer" >> "$PROFILE"
        echo "$PATH_EXPORT" >> "$PROFILE"
        success "Added PATH to $PROFILE"
    fi

    # Export for current session
    export PATH="$USER_BIN:$PATH"
}

verify_install() {
    info "Verifying installation..."

    if command -v kira &> /dev/null; then
        KIRA_VERSION=$(kira version 2>/dev/null | head -n1 || echo "installed")
        success "kira is ready: ${KIRA_VERSION}"
    else
        # Try with full path
        if [ -x "$HOME/.local/bin/kira" ]; then
            KIRA_VERSION=$("$HOME/.local/bin/kira" version 2>/dev/null | head -n1 || echo "installed")
            success "kira is ready: ${KIRA_VERSION}"
            warn "Restart your terminal or run: source ${PROFILE}"
        else
            error "Installation verification failed"
            echo "Try running: $PYTHON_CMD -m pip install --user git+${REPO}"
            exit 1
        fi
    fi
}

print_success() {
    echo ""
    echo -e "${GREEN}${BOLD}Installation complete!${NC}"
    echo ""
    echo "Get started:"
    echo -e "  ${CYAN}kira${NC}              Start interactive REPL"
    echo -e "  ${CYAN}kira chat \"...\"${NC}   One-shot prompt"
    echo -e "  ${CYAN}kira --help${NC}       Show all commands"
    echo ""
    echo "Update:"
    echo -e "  ${CYAN}kira update${NC}       Update to latest version"
    echo ""
}

main() {
    print_banner
    check_python
    check_kiro
    install_kira
    setup_path
    verify_install
    print_success
}

main "$@"
