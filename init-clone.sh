#!/bin/bash
# Clona (shallow) os repos Agenteresolve em /workspace se ainda não existirem.
# Idempotente: repos já clonados são pulados. Roda em background no start.
set -uo pipefail

WORKSPACE="${WORKSPACE_DIR:-/workspace}"
ORG="${GITHUB_ORG:-alex-pimentel}"
DEPTH="${CLONE_DEPTH:-1}"

# Os 24 repos Agenteresolve (todos públicos). Sobrescreva com CLONE_REPOS
# (separado por vírgula ou espaço) para clonar um subconjunto/outra lista.
DEFAULT_REPOS="
agenteresolve-translate agenteresolve-docuextract agenteresolve-askyourdocs
agenteresolve-datachat agenteresolve-feedback agenteresolve-seo
agenteresolve-contracts agenteresolve-ocr agenteresolve-anonymize
agenteresolve-alttext agenteresolve-objectcount agenteresolve-transcribe
agenteresolve-tts agenteresolve-audio-enhance agenteresolve-voicechat
agenteresolve-services agenteresolve agenteresolve-ci agenteresolve-ui
louder bg-removal image-up qrcode imposition
"
REPOS="${CLONE_REPOS:-$DEFAULT_REPOS}"
REPOS="${REPOS//,/ }"

mkdir -p "$WORKSPACE"
cd "$WORKSPACE" || exit 1

echo "[init-clone] $(date -Iseconds) workspace=$WORKSPACE org=$ORG depth=$DEPTH"
for repo in $REPOS; do
    [ -n "$repo" ] || continue
    if [ -d "$repo/.git" ]; then
        echo "[init-clone] = $repo já existe"
        continue
    fi
    echo "[init-clone] + clonando $repo"
    if git clone --depth "$DEPTH" "https://github.com/$ORG/$repo.git" "$repo"; then
        echo "[init-clone] ok $repo"
    else
        echo "[init-clone] ERRO ao clonar $repo" >&2
    fi
done
echo "[init-clone] $(date -Iseconds) concluído"
