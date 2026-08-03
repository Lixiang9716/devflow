#!/bin/bash
# DevFlow AgentTeams Deployment Script
# Deploys the complete DevFlow agent team to a running AgentTeams (Hiclaw) instance.
#
# Prerequisites:
#   1. AgentTeams installed and running (hiclaw-controller + hiclaw-manager)
#   2. DevFlow MCP server available (python devflow/mcp_server.py)
#   3. DEEPSEEK_API_KEY set in environment
#
# Usage:
#   bash deploy/agentteams/deploy.sh
#   bash deploy/agentteams/deploy.sh --dry-run    # Show what would be done
#   bash deploy/agentteams/deploy.sh --clean      # Remove existing devflow resources first

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

DRY_RUN=false
CLEAN_FIRST=false

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --clean) CLEAN_FIRST=true ;;
        *) echo "Unknown arg: $arg"; exit 1 ;;
    esac
done

hiclaw_cmd() {
    if $DRY_RUN; then
        echo "[DRY RUN] docker exec hiclaw-controller hiclaw $*"
    else
        docker exec hiclaw-controller hiclaw "$@"
    fi
}

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  DevFlow AgentTeams Deployment                          ║"
echo "║  7 agents, 23 tools, 5-phase pipeline                   ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Step 0: Verify AgentTeams is running
echo "🔍 Checking AgentTeams status..."
if ! docker ps --format '{{.Names}}' | grep -q 'hiclaw-controller'; then
    echo "❌ AgentTeams controller not running. Install first:"
    echo "   bash <(curl -sSL https://higress.ai/hiclaw/install.sh)"
    exit 1
fi
echo "   ✅ AgentTeams controller running"

# Step 1: Clean if requested
if $CLEAN_FIRST; then
    echo ""
    echo "🧹 Cleaning existing DevFlow resources..."
    for worker in devflow-analyst devflow-architect devflow-developer devflow-qa devflow-ops devflow-librarian devflow-attacker; do
        hiclaw_cmd delete worker "$worker" 2>/dev/null || true
    done
    hiclaw_cmd delete team devflow 2>/dev/null || true
    echo "   ✅ Cleaned"
fi

# Step 2: Create Workers (individual agents)
echo ""
echo "🤖 Creating DevFlow Workers..."

create_worker() {
    local name="$1" runtime="$2" model="$3" role="$4" identity="$5" skills="$6" tool_group="$7" soul_file="$8"

    echo "   📝 $name ($runtime, $model)"
    if $DRY_RUN; then
        echo "      [DRY RUN] Would create worker: $name"
        return
    fi

    # Check if worker already exists
    if docker exec hiclaw-controller hiclaw get workers 2>/dev/null | grep -q "\"$name\""; then
        echo "      ⚠️  Worker '$name' already exists, skipping"
        return
    fi

    hiclaw_cmd create worker \
        --name "$name" \
        --runtime "$runtime" \
        --model "$model" \
        --role "$role" \
        --identity "$identity" \
        --skills "$skills" \
        --soul-file "$soul_file" \
        --team devflow \
        --wait-timeout 2m
}

create_worker "devflow-analyst" "openclaw" "deepseek-v4-pro" "team_leader" \
    "Requirements Engineer — converts natural language into structured use cases, FRs, and Lean ACs" \
    "analyst-phase1,lean-ac-format" \
    "T1,T2,T11" \
    "$SCRIPT_DIR/souls/SOUL-analyst.md"

create_worker "devflow-architect" "openclaw" "deepseek-v4-pro" "worker" \
    "Software Architect — PoC feasibility, top-down architecture, ADR, interface contracts" \
    "architect-phase2,architect-phase3,adr-template" \
    "T3,T5,T11" \
    "$SCRIPT_DIR/souls/SOUL-architect.md"

create_worker "devflow-developer" "hermes" "deepseek-v4-pro" "worker" \
    "Software Developer — code as patches, interface-first, exception paths first, self-review" \
    "developer-phase4,patch-generation,self-review-checklist" \
    "T6,T7" \
    "$SCRIPT_DIR/souls/SOUL-developer.md"

create_worker "devflow-qa" "copaw" "deepseek-v4-flash" "worker" \
    "QA Engineer — independent verification, mutation testing, issue classification decision tree" \
    "qa-phase5,issue-classification-tree,test-quality-gates" \
    "T8,T9,T12" \
    "$SCRIPT_DIR/souls/SOUL-qa.md"

create_worker "devflow-ops" "copaw" "deepseek-v4-flash" "worker" \
    "DevOps/SRE — CI/CD, staging, canary releases, health checks, auto-rollback" \
    "devops-deployment" \
    "T7,T8" \
    "$SCRIPT_DIR/souls/SOUL-devops.md"

create_worker "devflow-librarian" "openclaw" "deepseek-v4-pro" "worker" \
    "Knowledge Manager — dual-channel index, context retrieval, pattern extraction, feedback audit" \
    "knowledge-retrieval,knowledge-indexing,feedback-audit" \
    "T11,T12" \
    "$SCRIPT_DIR/souls/SOUL-knowledge.md"

create_worker "devflow-attacker" "openclaw" "deepseek-v4-pro" "worker" \
    "Adversarial Tester — 5 attack strategies, finds use case and architecture weaknesses" \
    "attacker-phase1,five-strategies,probe-report-format" \
    "T1,T2" \
    "$SCRIPT_DIR/souls/SOUL-attacker.md"

# Step 3: Create Team
echo ""
echo "👥 Creating DevFlow Team..."
if ! $DRY_RUN; then
    if docker exec hiclaw-controller hiclaw get teams 2>/dev/null | grep -q '"devflow"'; then
        echo "   ⚠️  Team 'devflow' already exists, skipping"
    else
        hiclaw_cmd create team \
            --name devflow \
            --leader-name devflow-analyst \
            --leader-model deepseek-v4-pro \
            --workers devflow-architect,devflow-developer,devflow-qa,devflow-ops,devflow-librarian,devflow-attacker \
            --description "DevFlow — AI-driven structured SE: 5-phase pipeline, 7 agents, dual-channel knowledge"
    fi
fi

# Step 4: Register Skills
echo ""
echo "🎯 Registering DevFlow Skills..."

register_skill() {
    local skill_name="$1" skill_file="$2"
    echo "   📚 $skill_name"
    if $DRY_RUN; then
        echo "      [DRY RUN] Would register skill: $skill_name"
        return
    fi
    # Skills are registered via the Nacos registry or API
    # For now, skills are embedded via --skills flag on worker creation
}

register_skill "analyst-phase1" "$SCRIPT_DIR/../skills/SKILL-analyst-phase1.md"
register_skill "architect-phase3" "$SCRIPT_DIR/../skills/SKILL-architect-phase3.md"
register_skill "developer-phase4" "$SCRIPT_DIR/../skills/SKILL-developer-phase4.md"
register_skill "qa-phase5" "$SCRIPT_DIR/../skills/SKILL-qa-phase5.md"

# Step 5: Status
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  DevFlow Deployment Complete!"
echo "══════════════════════════════════════════════════════════"
echo ""
echo "📊 Status:"
if ! $DRY_RUN; then
    docker exec hiclaw-controller hiclaw get workers 2>/dev/null | python3 -c "
import sys, json
workers = json.load(sys.stdin)
for w in workers:
    print(f'   {w[\"name\"]}: {w.get(\"status\", \"unknown\")} ({w.get(\"runtime\", \"?\")})')
" 2>/dev/null || echo "   (run 'hiclaw get workers' to check)"
fi
echo ""
echo "🌐 Access:"
echo "   Manager Console: http://127.0.0.1:18888"
echo "   Element Web UI:  http://127.0.0.1:18088"
echo "   Higress Console: http://127.0.0.1:18001"
echo ""
echo "📝 Next Steps:"
echo "   1. Open Element Web UI to chat with agents"
echo "   2. Submit a task: '电商平台需要支持多币种订单功能'"
echo "   3. Watch the 5-phase pipeline execute"
