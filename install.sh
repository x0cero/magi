#!/usr/bin/env bash
set -e

echo ""
echo "  ███╗   ███╗ █████╗  ██████╗ ██╗"
echo "  ████╗ ████║██╔══██╗██╔════╝ ██║"
echo "  ██╔████╔██║███████║██║  ███╗██║"
echo "  ██║╚██╔╝██║██╔══██║██║   ██║██║"
echo "  ██║ ╚═╝ ██║██║  ██║╚██████╔╝██║"
echo "  ╚═╝     ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝"
echo ""
echo "  installing MAGI — three-agent decision council"
echo ""

# Check for Python 3.11+
if command -v python3 &>/dev/null; then
    PY=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(echo "$PY" | cut -d. -f1)
    PY_MINOR=$(echo "$PY" | cut -d. -f2)
    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 11 ]; }; then
        echo "  ✗ Python $PY found, but MAGI needs 3.11+."
        echo "    install: https://www.python.org/downloads/"
        exit 1
    fi
    echo "  ✓ Python $PY"
else
    echo "  ✗ Python 3 not found."
    echo "    install: https://www.python.org/downloads/"
    exit 1
fi

# Check for pipx, install if missing
if command -v pipx &>/dev/null; then
    echo "  ✓ pipx"
else
    echo "  · installing pipx..."
    python3 -m pip install --user pipx 2>/dev/null || pip install --user pipx 2>/dev/null
    python3 -m pipx ensurepath 2>/dev/null || true
    export PATH="$HOME/.local/bin:$PATH"
    if command -v pipx &>/dev/null; then
        echo "  ✓ pipx installed"
    else
        echo "  ✗ could not install pipx. install manually: https://pipx.pypa.io"
        exit 1
    fi
fi

# Check for Ollama, install if missing
if command -v ollama &>/dev/null; then
    echo "  ✓ ollama"
else
    echo "  · ollama not found. installing..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        if command -v brew &>/dev/null; then
            brew install ollama
        else
            echo "    download Ollama from: https://ollama.com/download"
            echo "    then re-run this script."
            exit 1
        fi
    elif [[ "$OSTYPE" == "linux"* ]]; then
        curl -fsSL https://ollama.com/install.sh | sh
    else
        echo "    download Ollama from: https://ollama.com/download"
        echo "    then re-run this script."
        exit 1
    fi
    if command -v ollama &>/dev/null; then
        echo "  ✓ ollama installed"
    else
        echo "  ✗ ollama install failed. get it from: https://ollama.com/download"
        exit 1
    fi
fi

# Make sure Ollama is running
if ! curl -s http://localhost:11434/api/version &>/dev/null; then
    echo "  · starting ollama..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        open -a Ollama 2>/dev/null || ollama serve &>/dev/null &
    else
        ollama serve &>/dev/null &
    fi
    sleep 3
    if curl -s http://localhost:11434/api/version &>/dev/null; then
        echo "  ✓ ollama running"
    else
        echo "  ✗ could not start ollama. run 'ollama serve' manually, then re-run this script."
        exit 1
    fi
else
    echo "  ✓ ollama running"
fi

echo ""
echo "  pulling models (~23 GB total, this takes a while)..."
echo ""

ollama pull qwen3:4b
echo "  ✓ qwen3:4b"

ollama pull dolphin3:8b
echo "  ✓ dolphin3:8b"

ollama pull hermes3:8b
echo "  ✓ hermes3:8b"

ollama pull qwen3:4b
echo "  ✓ qwen3:4b (classifier)"

echo ""
echo "  installing magi..."
pipx install git+https://github.com/x0cero/magi 2>/dev/null || pipx install --force git+https://github.com/x0cero/magi

echo ""
echo "  ✓ done. type 'magi' to start."
echo ""
echo "  quick start:"
echo "    magi                              open the council"
echo "    magi \"should I take the job?\"     one-shot question"
echo "    magi doctor                       check everything is working"
echo ""
