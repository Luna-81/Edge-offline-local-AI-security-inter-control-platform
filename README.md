# Edge-offline-local-AI-security-inter-control-platform

[![Python](https://img.shields.io/badge/Python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109.0-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![LanceDB](https://img.shields.io/badge/LanceDB-0.6.0-orange.svg)](https://lancedb.com/)

>  A multi-expert discussion system for intelligent system optimization - Let AI think like a team of experts and automatically execute optimizations!

##  Key Features

###  6-Parliament Discussion Mechanism
* **6 Expert Roles**: Intent Understanding, Security Compliance, Business Logic, Execution Technology, Deep Tracking, Precision Locking
* **Three-Round Debate**: Independent Analysis → Cross-Examination → Consensus Formation
* **Dynamic Dimension Adjustment**: Automatically adjusts expert output precision (8-512 dimensions) based on problem complexity
* **Gradient-Enhanced Learning**: Auto scaling dimensions up/down for optimal discussion efficiency

###  Intelligent Memory System
* **LanceDB Vector Storage**: Local storage, no additional deployment required
* **Short-Term Memory**: Conversation history management (10-turn context)
* **Long-Term Memory**: Permanent storage of critical knowledge with semantic retrieval
* **Auto Learning**: Execution results automatically stored, system gets smarter over time

###  Executable Skill Generation
* **JSON Skill Generation**: Convert expert advice to structured executable commands
* **Risk Grading**: Auto-evaluate risk levels for each command (Low/Medium/High)
* **Rollback Plans**: Provide rollback commands for every operation
* **Execution Validation**: Harness QVK framework validates command effectiveness

###  Multi-Mode Conversation
* **Full Mode**: All 6 experts discuss together, forming comprehensive advice
* **Single Mode**: `@expert_name` to consult a specific expert directly
* **Session Management**: `/exit` to leave single mode and return to full mode

###  Real-time WebSocket Interaction
* **Real-time Streaming**: Expert responses pushed one by one
* **Progress Visualization**: Shows the three-round discussion progress
* **Interactive Panel**: Collapsible/expandable with customizable height

##  Quick Start

### Requirements
```bash
Python 3.12+
CUDA 11.8+ (optional, for GPU acceleration)
8GB+ RAM (16GB recommended)
```

### Installation
```bash
git clone [https://github.com/yourusername/aegisnet.git](https://github.com/yourusername/aegisnet.git)
cd aegisnet
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Download Models

To ensure the system functions correctly, you need to download the required LLM (Gemma-2-2B) and embedding model (BGE-small-zh) into your local `models` directory.

```bash
mkdir -p models
cd models

# Download the quantized Gemma-2 model
wget [https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf](https://huggingface.co/bartowski/gemma-2-2b-it-GGUF/resolve/main/gemma-2-2b-it-Q4_K_M.gguf)

# Clone the BGE-small embedding model repository
git clone [https://huggingface.co/BAAI/bge-small-zh-v1.5](https://huggingface.co/BAAI/bge-small-zh-v1.5)
```

### Configure Environment

Create a `.env` file in the root directory of the project to manage your application's configuration and security keys.

```bash
cat > .env << EOF
JWT_SECRET=your-secret-key-change-in-production
DATABASE_URL=./users.db
TOKEN_EXPIRE_MINUTES=600
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
EOF
```

### Start Service
```bash
python main.py
# Or: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```
# Architecture
User Input → Smart Router → 6-Parliament Discussion → Executable JSON → Validation → Execution → Results Storage → Learning

## Usage Examples
Full Mode (6-Parliament Discussion)
User: "How to optimize Linux system?"

System Response:
```bash
{
  "actions": [
    {"command": "sysctl -w vm.swappiness=10", "risk": "low"},
    {"command": "echo deadline > /sys/block/sda/queue/scheduler", "risk": "medium"}
  ]
}
```

Single Mode
User: "@tech How to optimize SQL queries?"

Tech Expert: "Recommend using index optimization on columns used in WHERE clauses. Specific steps: CREATE INDEX idx_column ON table(column);"

Exit Single Mode
User: "/exit"

System Response:
 Exited single mode, back to full mode

# Project Structure
```bash
aegisnet/
├── src/agent/ai/
│   ├── main.py                    # FastAPI + WebSocket main service
│   ├── local_brain.py             # Local brain core
│   ├── talker.py                  # Conversation engine
│   ├── memory_vault.py            # Memory system
│   ├── models/                    # Model files
│   ├── haystack_pipeline/
│   │   ├── pipelines/
│   │   │   └── chat_pipeline.py
│   │   ├── roundtable/
│   │   │   ├── experts.py
│   │   │   ├── three_round.py
│   │   │   ├── roundtable_say.py
│   │   │   ├── harness_qvk.py
│   │   │   └── session_manager.py
│   └── vault_lancedb/             # LanceDB data
├── src/web/user.html              # Frontend interface
├── requirements.txt
├── .env.example
└── README.md
```


