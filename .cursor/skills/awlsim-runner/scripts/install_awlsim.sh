#!/bin/bash
# install_awlsim.sh - Idempotent installer for awlsim PLC simulator
#
# Clones a pinned commit of the awlsim repo, verifies the SHA matches,
# and checks that Python imports work. This ensures reproducible builds
# and protects against upstream drift.
#
# Version: 1.1.0

set -e

AWLSIM_DIR="/home/claude/awlsim"
REPO_URL="https://github.com/mbuesch/awlsim.git"

# ---- Pinned version ----
# Known-good awlsim commit (tested with awlsim-runner v1.1.0)
PINNED_SHA="b02373bc388f02efe2537f371b3fa91762e32d83"

# ---- Minimum Python version ----
PYTHON_MIN_MAJOR=3
PYTHON_MIN_MINOR=8

INSTALLER_VERSION="1.1.0"

# JSON output helper
json_result() {
    echo "{\"status\": \"$1\", \"message\": \"$2\", \"path\": \"$AWLSIM_DIR\", \"awlsim_sha\": \"$PINNED_SHA\", \"installer_version\": \"$INSTALLER_VERSION\"}"
}

# ---- Check Python version ----
check_python() {
    local py_version
    py_version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
    if [ -z "$py_version" ]; then
        json_result "error" "python3 not found"
        exit 1
    fi

    local py_major py_minor
    py_major=$(echo "$py_version" | cut -d. -f1)
    py_minor=$(echo "$py_version" | cut -d. -f2)

    if [ "$py_major" -lt "$PYTHON_MIN_MAJOR" ] || { [ "$py_major" -eq "$PYTHON_MIN_MAJOR" ] && [ "$py_minor" -lt "$PYTHON_MIN_MINOR" ]; }; then
        json_result "error" "Python ${PYTHON_MIN_MAJOR}.${PYTHON_MIN_MINOR}+ required, found ${py_version}"
        exit 1
    fi
}

# ---- Verify SHA matches pinned commit ----
verify_sha() {
    local actual_sha
    actual_sha=$(cd "$AWLSIM_DIR" && git rev-parse HEAD 2>/dev/null)
    if [ "$actual_sha" != "$PINNED_SHA" ]; then
        echo "SHA mismatch: expected $PINNED_SHA, got $actual_sha" >&2
        return 1
    fi
    return 0
}

# ---- Verify Python imports work ----
verify_imports() {
    PYTHONPATH="$AWLSIM_DIR" python3 -c "from awlsim.core.main import AwlSim; from awlsim.awlcompiler import AwlParser" 2>/dev/null
}

# ---- Main ----
check_python

# Check if already installed, correct SHA, and imports work
if [ -d "$AWLSIM_DIR/awlsim/core" ]; then
    if verify_sha && verify_imports; then
        json_result "already_installed" "awlsim is already installed at pinned commit ${PINNED_SHA:0:8}"
        exit 0
    else
        echo "awlsim directory exists but SHA mismatch or imports fail. Re-cloning..." >&2
        rm -rf "$AWLSIM_DIR"
    fi
fi

# Clone the repository at the pinned commit
echo "Cloning awlsim from $REPO_URL at commit ${PINNED_SHA:0:8}..." >&2
if git clone "$REPO_URL" "$AWLSIM_DIR" 2>&1 >&2; then
    # Checkout the pinned commit
    cd "$AWLSIM_DIR"
    if ! git checkout "$PINNED_SHA" --quiet 2>&1 >&2; then
        json_result "error" "Failed to checkout pinned commit $PINNED_SHA"
        exit 1
    fi

    # Verify SHA
    if ! verify_sha; then
        json_result "error" "SHA verification failed after checkout"
        exit 1
    fi

    # Verify imports
    if verify_imports; then
        json_result "installed" "awlsim cloned and verified at pinned commit ${PINNED_SHA:0:8}"
        exit 0
    else
        json_result "error" "Clone succeeded but Python imports failed"
        exit 1
    fi
else
    json_result "error" "git clone failed"
    exit 1
fi
