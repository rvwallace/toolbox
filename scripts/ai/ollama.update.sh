#!/usr/bin/env bash
# toolbox-platforms: all
set -euo pipefail

# --- Ollama Model Update Script ---

echo "==================================================="
echo "🌐 Starting Ollama Model Update Process"
echo "==================================================="

# Check if ollama is installed
if ! command -v ollama &> /dev/null; then
    echo "ERROR: 'ollama' command not found. Please ensure Ollama is installed and running."
    exit 1
fi

# Use awk to safely extract only the names from the 'ollama ls' output.
# NR > 1 skips the header row.
# {print $1} prints the first field (the model name).
MODEL_NAMES=$(ollama ls | awk 'NR > 1 {print $1}')

if [ -z "$MODEL_NAMES" ]; then
    echo "No models found installed by ollama. Exiting."
    exit 0
fi

echo "Found the following models to update:"
echo "$MODEL_NAMES"
echo "---------------------------------------------------"

# Loop through each model name found
for model in $MODEL_NAMES; do
    echo -e "\n-> Updating model: $model"
    
    # Save cursor position before pull output
    printf "\0337"
    
    # The 'ollama pull' command updates the local model to the latest version
    # if a new version is available on the registry.
    if ollama pull "$model"; then
        # Restore cursor position and clear all output after it
        printf "\0338\033[J"
        echo "✅ Success: $model updated successfully."
    else
        # Restore cursor position and clear all output after it
        printf "\0338\033[J"
        echo "❌ Warning: Failed to update $model. Please check your connection or model name."
    fi
done

echo "==================================================="
echo "✨ All updates attempted. Process complete!"
echo "==================================================="
