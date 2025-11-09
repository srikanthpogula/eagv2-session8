# Detailed Code Analysis: C:/EAG/Session8/code2

## Executive Summary

This codebase implements **Cortex-R**, a reasoning-driven AI agent system that uses external tools and memory to solve complex tasks step-by-step. The architecture follows a modular design with clear separation of concerns: perception, planning, action, and memory management.

---

## 1. Architecture Overview

### 1.1 Core Components

The system is organized into several key layers:

```
┌─────────────────────────────────────────┐
│         agent.py (Entry Point)          │
└──────────────┬──────────────────────────┘
               │
┌──────────────▼──────────────────────────┐
│      core/loop.py (AgentLoop)           │
│  - Orchestrates the agent execution     │
│  - Manages step-by-step reasoning       │
└──────────────┬──────────────────────────┘
               │
    ┌──────────┴──────────┐
    │                     │
┌───▼────┐         ┌──────▼──────┐
│Perception│         │  Planning   │
│(modules/ │         │(modules/    │
│perception│         │decision)    │
└───┬────┘         └──────┬──────┘
    │                     │
┌───▼─────────────────────▼───┐
│      Action Execution      │
│   (modules/action.py)      │
└───────────┬────────────────┘
            │
    ┌───────┴────────┐
    │                │
┌───▼────┐    ┌──────▼──────┐
│ Memory │    │ MCP Servers │
│Manager │    │(mcp_server_*)│
└────────┘    └─────────────┘
```

### 1.2 Key Design Patterns

1. **Modular Architecture**: Each component (perception, decision, action, memory) is isolated in its own module
2. **MCP (Model Context Protocol) Integration**: Tools are exposed via FastMCP servers
3. **Strategy Pattern**: Configurable agent behavior via `core/strategy.py`
4. **Context Management**: Shared state via `AgentContext` class

---

## 2. File-by-File Analysis

### 2.1 Entry Point: `agent.py`

**Purpose**: Main entry point for running the agent interactively.

**Key Features**:
- Loads configuration from `config/profiles.yaml`
- Initializes `MultiMCP` to discover tools from multiple MCP servers
- Creates `AgentLoop` instance and executes it
- Handles user input via command-line prompt

**Code Flow**:
```python
1. Load profiles.yaml → Extract MCP server configs
2. Initialize MultiMCP → Discover all available tools
3. Create AgentLoop(user_input, dispatcher)
4. Execute agent.run() → Returns final answer
```

**Dependencies**:
- `core.loop.AgentLoop`
- `core.session.MultiMCP`
- `yaml` for config parsing

---

### 2.2 Core Loop: `core/loop.py`

**Purpose**: Orchestrates the agent's reasoning loop.

**Key Components**:

#### `AgentLoop` Class
- **Initialization**: Takes `user_input` and `dispatcher` (MultiMCP instance)
- **Main Loop**: Iterates up to `max_steps` (default: 3 from config)

#### Execution Flow (per step):
```
1. 🧠 Perception Phase
   - Calls extract_perception(query)
   - Extracts intent, entities, tool_hint
   - Handles FINAL_ANSWER detection

2. 💾 Memory Retrieval
   - Retrieves relevant memories using semantic search
   - Filters by type/session/tags

3. 📊 Planning Phase
   - Calls decide_next_action() → generate_plan()
   - LLM decides: FUNCTION_CALL or FINAL_ANSWER

4. ⚙️ Tool Execution
   - Parses FUNCTION_CALL string
   - Calls MCP tool via dispatcher
   - Stores result in memory

5. 🔁 Query Update
   - Updates query for next iteration
   - Includes previous tool result
```

**Key Methods**:
- `tool_expects_input(tool_name)`: Checks if tool uses `input` parameter wrapper
- `run()`: Main execution loop

**Error Handling**:
- Detects LLM prompt echoing
- Handles JSON parsing failures
- Gracefully exits on FINAL_ANSWER

---

### 2.3 Context Management: `core/context.py`

**Purpose**: Maintains session-wide state and agent identity.

#### `AgentProfile` Class
- Loads configuration from `profiles.yaml`
- Stores:
  - Agent name, ID, description
  - Strategy type (conservative, retry_once, explore_all)
  - Memory configuration (top_k, type_filter, embedding settings)
  - LLM configuration
  - Persona settings (tone, verbosity, behavior_tags)

#### `AgentContext` Class
- **Session Management**: Generates unique `session_id`
- **Memory Integration**: Wraps `MemoryManager` instance
- **State Tracking**:
  - Current step number
  - Memory trace (list of `MemoryItem`)
  - Tool call trace (list of `ToolCallTrace`)
  - Final answer

**Key Methods**:
- `add_tool_trace()`: Records tool execution
- `add_memory()`: Stores memory item and adds to vector index

---

### 2.4 Strategy Layer: `core/strategy.py`

**Purpose**: Wraps planning logic with strategy-aware control.

**Key Function**: `decide_next_action()`

**Strategy Types**:
1. **Conservative** (default): Uses hint-based tool filtering, returns plan as-is
2. **Retry Once**: If plan contains "unknown", retries with all tools
3. **Explore All** (placeholder): Future parallel planning

**Tool Filtering**:
- First tries tools matching `perception.tool_hint`
- Falls back to all tools if filtering fails (retry_once strategy)

---

### 2.5 Session Management: `core/session.py`

**Purpose**: Manages MCP server connections and tool discovery.

#### `MCP` Class (Legacy)
- Lightweight wrapper for one-time MCP tool calls
- Each call spins up a new subprocess

#### `MultiMCP` Class (Current)
- **Initialization**: Discovers tools from multiple MCP servers
- **Tool Mapping**: Maintains `tool_map` (tool_name → config + tool object)
- **Tool Execution**: Reconnects per tool call (stateless design)

**Key Methods**:
- `initialize()`: Scans all configured MCP servers, discovers tools
- `call_tool()`: Executes tool on appropriate server
- `get_all_tools()`: Returns list of all discovered tools

**MCP Server Configuration** (from `profiles.yaml`):
```yaml
mcp_servers:
  - id: math
    script: mcp_server_1.py
    cwd: C:/EAG/Session8/code2
  - id: documents
    script: mcp_server_2.py
    cwd: C:/EAG/Session8/code2
  - id: websearch
    script: mcp_server_3.py
    cwd: C:/EAG/Session8/code2
```

---

### 2.6 Perception Module: `modules/perception.py`

**Purpose**: Extracts structured information from user input using LLM.

#### `PerceptionResult` (Pydantic Model)
```python
- user_input: str
- intent: Optional[str]  # High-level goal
- entities: List[str]    # Keywords/values
- tool_hint: Optional[str]  # Suggested MCP tool name
```

#### `extract_perception()` Function
- **Input**: Raw user query string
- **Process**: 
  1. Constructs prompt with available tools context
  2. Calls LLM (via `ModelManager`)
  3. Parses JSON response
  4. Returns `PerceptionResult`
- **Error Handling**: Returns minimal `PerceptionResult` on failure

**Key Features**:
- Cleans markdown-wrapped JSON
- Handles null/undefined responses
- Fixes common entity parsing issues (dict → list)

---

### 2.7 Decision Module: `modules/decision.py`

**Purpose**: Generates the next action plan (tool call or final answer).

#### `generate_plan()` Function

**Input Parameters**:
- `perception`: PerceptionResult
- `memory_items`: Retrieved memories
- `tool_descriptions`: Formatted tool list
- `step_num`: Current step
- `max_steps`: Maximum steps allowed

**Prompt Structure**:
1. **Context**: Step number, memory items, available tools
2. **Input Summary**: User input, intent, entities, tool hint
3. **Examples**: FUNCTION_CALL and FINAL_ANSWER formats
4. **Rules**: 
   - Don't invent tools
   - Use `search_documents` for factual queries
   - Don't repeat tool calls
   - Always provide FINAL_ANSWER on final step

**Output Format**:
- `FUNCTION_CALL: tool_name|param1=value1|param2=value2`
- `FINAL_ANSWER: [result]`

**Key Features**:
- Extracts first valid FUNCTION_CALL or FINAL_ANSWER line
- Falls back to `FINAL_ANSWER: [unknown]` on error

---

### 2.8 Action Module: `modules/action.py`

**Purpose**: Parses and executes tool calls.

#### `parse_function_call()` Function

**Input Format**:
```
FUNCTION_CALL: tool_name|param1=value1|param2=value2
```

**Parsing Logic**:
1. Splits by `:` to get function call part
2. Splits by `|` to separate tool name and parameters
3. Parses each `key=value` pair
4. Supports nested keys (e.g., `input.string`)
5. Uses `ast.literal_eval()` for type inference

**Example**:
```
FUNCTION_CALL: strings_to_chars_to_int|input.string=INDIA
→ tool_name: "strings_to_chars_to_int"
→ arguments: {"input": {"string": "INDIA"}}
```

**Error Handling**: Raises `ValueError` on invalid format

---

### 2.9 Memory Module: `modules/memory.py`

**Purpose**: Semantic memory management using FAISS vector search.

#### `MemoryItem` (Pydantic Model)
```python
- text: str
- type: Literal["preference", "tool_output", "fact", "query", "system"]
- timestamp: Optional[str]
- tool_name: Optional[str]
- user_query: Optional[str]
- tags: List[str]
- session_id: Optional[str]
```

#### `MemoryManager` Class

**Initialization**:
- `embedding_model_url`: URL for embedding API (e.g., Ollama)
- `model_name`: Embedding model name (default: "nomic-embed-text")

**Key Methods**:
- `_get_embedding(text)`: Calls embedding API, returns numpy array
- `add(item)`: 
  1. Generates embedding
  2. Adds to FAISS index
  3. Stores in memory list
- `retrieve(query, top_k, type_filter, tag_filter, session_filter)`:
  1. Generates query embedding
  2. Searches FAISS index (overfetches for filtering)
  3. Applies filters (type, tag, session)
  4. Returns top_k results

**Vector Index**: Uses `faiss.IndexFlatL2` (L2 distance)

---

### 2.10 Tools Module: `modules/tools.py`

**Purpose**: Utility functions for tool management.

**Key Functions**:
- `summarize_tools(tools)`: Formats tool list for LLM prompts
- `filter_tools_by_hint(tools, hint)`: Filters tools by name hint
- `get_tool_map(tools)`: Creates tool_name → tool object mapping
- `tool_expects_input()`: Checks if tool uses `input` wrapper (standalone function, not method)

---

### 2.11 Model Manager: `modules/model_manager.py`

**Purpose**: Unified interface for LLM text generation.

#### `ModelManager` Class

**Initialization**:
- Loads `config/models.json` and `config/profiles.yaml`
- Determines model type from profile
- Initializes client (Gemini or Ollama)

**Supported Models**:
1. **Gemini** (`google-genai`):
   - Requires `GEMINI_API_KEY` environment variable
   - Uses `genai.Client`
   - Model: `gemini-2.0-flash` (from config)

2. **Ollama** (local):
   - Uses HTTP API (`http://localhost:11434/api/generate`)
   - Supports any Ollama model

**Key Method**: `generate_text(prompt)`
- Routes to appropriate model handler
- Returns text response (stripped)

**Error Handling**: Safely extracts text from Gemini response objects

---

### 2.12 MCP Servers

#### `mcp_server_1.py` - Math/Calculator Tools

**Purpose**: Mathematical operations and code execution.

**Available Tools**:
- Basic math: `add`, `subtract`, `multiply`, `divide`, `power`, `sqrt`, `cbrt`
- Advanced: `factorial`, `remainder`, `sin`, `cos`, `tan`
- String operations: `strings_to_chars_to_int`, `int_list_to_exponential_sum`
- Code execution: `run_python_sandbox`, `run_shell_command`, `run_sql_query`
- Image: `create_thumbnail`
- Sequences: `fibonacci_numbers`

**Special Tools**:
- `mine`: Custom mining operation (a - b - b)

**Resources**: `greeting://{name}` (dynamic greeting)

**Prompts**: `review_code`, `debug_error`

---

#### `mcp_server_2.py` - Document Processing

**Purpose**: Document indexing, search, and extraction.

**Key Features**:
- **FAISS Indexing**: Creates vector index of documents
- **Semantic Chunking**: Uses LLM to split documents intelligently
- **Multimodal Processing**: Handles PDFs, webpages, images
- **Image Captioning**: Uses Ollama vision model to caption images

**Available Tools**:
- `search_documents(query)`: Semantic search over indexed documents
- `extract_webpage(input)`: Converts webpage to markdown
- `extract_pdf(input)`: Converts PDF to markdown

**Processing Pipeline**:
```
1. File Detection → Determine file type
2. Extraction → Convert to markdown (Trafilatura, PyMuPDF4LLM, MarkItDown)
3. Image Processing → Extract images, caption them, delete local copies
4. Semantic Chunking → Split by topic using LLM
5. Embedding → Generate embeddings for each chunk
6. Indexing → Add to FAISS index with metadata
```

**Configuration**:
- Embedding: `nomic-embed-text` (Ollama)
- Vision Model: `gemma3:12b` (for image captioning)
- Chunking Model: `phi4` (for semantic chunking)
- Chunk Size: 256 words, 40 word overlap

**Caching**: Uses MD5 hashes to skip unchanged files

---

#### `mcp_server_3.py` - Web Search

**Purpose**: Web search and content fetching.

**Key Components**:

#### `DuckDuckGoSearcher` Class
- **Rate Limiting**: `RateLimiter` (30 requests/minute)
- **Search Method**: POST request to DuckDuckGo HTML interface
- **Parsing**: BeautifulSoup to extract results

#### `SearchResult` Dataclass
```python
- title: str
- link: str
- snippet: str
- position: int
```

**Available Tools** (from partial read):
- `web_search`: DuckDuckGo search
- `fetch_content`: Fetch webpage content

**Features**:
- User-Agent spoofing for bot detection avoidance
- Formatted results for LLM consumption
- Error handling for parsing failures

---

### 2.13 Configuration Files

#### `config/profiles.yaml`

**Structure**:
```yaml
agent:
  name: Cortex-R
  id: cortex_r_001
  description: Reasoning-driven AI agent

strategy:
  type: conservative  # conservative, retry_once, explore_all
  max_steps: 3

memory:
  top_k: 3
  type_filter: tool_output
  embedding_model: nomic-embed-text
  embedding_url: http://localhost:11434/api/embeddings

llm:
  text_generation: gemini
  embedding: nomic

persona:
  tone: concise
  verbosity: low
  behavior_tags: [rational, focused, tool-using]

mcp_servers:
  - id: math
    script: mcp_server_1.py
    cwd: C:/EAG/Session8/code2
  # ... more servers
```

**Key Settings**:
- `max_steps: 3`: Limits agent iterations (may be too low for complex tasks)
- `type_filter: tool_output`: Only retrieves tool outputs from memory
- `strategy: conservative`: Uses hint-based tool filtering

---

#### `config/models.json`

**Structure**:
```json
{
  "defaults": {
    "text_generation": "gemini",
    "embedding": "nomic"
  },
  "models": {
    "gemini": {
      "type": "gemini",
      "model": "gemini-2.0-flash",
      "api_key_env": "GEMINI_API_KEY"
    },
    "nomic": {
      "type": "huggingface",
      "model": "nomic-ai/nomic-embed-text-v1",
      "embedding_dimension": 768
    }
  }
}
```

**Model Types**:
- `gemini`: Google Gemini API
- `ollama`: Local Ollama instance
- `huggingface`: Hugging Face models (for embeddings)

---

## 3. Data Flow

### 3.1 Complete Execution Flow

```
User Input
    ↓
agent.py (loads config, initializes MultiMCP)
    ↓
AgentLoop.run()
    ↓
┌─────────────────────────────────────┐
│  Step 1: Perception                  │
│  extract_perception(query)           │
│  → Intent, Entities, Tool Hint       │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Step 2: Memory Retrieval           │
│  memory.retrieve(query)              │
│  → Top-k relevant memories           │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Step 3: Planning                   │
│  decide_next_action()               │
│  → generate_plan()                  │
│  → FUNCTION_CALL or FINAL_ANSWER    │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  Step 4: Action Execution            │
│  parse_function_call()              │
│  → mcp.call_tool()                  │
│  → Store result in memory           │
└─────────────────────────────────────┘
    ↓
Update query with result
    ↓
Repeat until FINAL_ANSWER or max_steps
```

### 3.2 Memory Flow

```
Tool Execution
    ↓
MemoryItem created
    ↓
Generate embedding (via Ollama API)
    ↓
Add to FAISS index
    ↓
Store in memory.data list
    ↓
Future queries → retrieve() → Semantic search
```

---

## 4. Key Strengths

1. **Modular Design**: Clear separation of concerns
2. **Extensible**: Easy to add new MCP servers and tools
3. **Memory Integration**: Semantic search for context retrieval
4. **Strategy Pattern**: Configurable agent behavior
5. **Error Handling**: Graceful degradation on failures
6. **Type Safety**: Uses Pydantic models for validation

---

## 5. Potential Issues & Recommendations

### 5.1 Current Issues

1. **Low max_steps (3)**: May be insufficient for complex multi-step tasks
   - **Recommendation**: Increase to 5-7 for production use

2. **Stateless MCP Connections**: Each tool call creates new subprocess
   - **Impact**: Higher latency, no persistent state
   - **Recommendation**: Consider persistent connections for frequently used tools

3. **Memory Type Filter**: Only retrieves `tool_output` memories
   - **Impact**: May miss relevant facts or queries
   - **Recommendation**: Use `type_filter: all` or `type_filter: null` for broader context

4. **No Tool Result Validation**: Doesn't verify tool results before proceeding
   - **Recommendation**: Add result validation layer

5. **Limited Error Recovery**: Breaks on first error in loop
   - **Recommendation**: Add retry logic for transient failures

### 5.2 Code Quality Issues

1. **Unused Function**: `tool_expects_input()` in `modules/tools.py` is standalone (not a method)
2. **Inconsistent Error Messages**: Some errors return `[no result]`, others `[unknown]`
3. **Hardcoded Paths**: MCP server paths are absolute Windows paths
   - **Recommendation**: Use relative paths or environment variables

### 5.3 Performance Considerations

1. **Sequential Tool Execution**: Tools run one at a time
   - **Recommendation**: Parallel execution for independent tools

2. **Embedding API Calls**: Each memory add/retrieve calls external API
   - **Impact**: Latency on memory operations
   - **Recommendation**: Batch embedding requests

3. **FAISS Index Loading**: Loads entire index on each search
   - **Recommendation**: Keep index in memory for active sessions

---

## 6. Dependencies

### Core Dependencies
- `mcp`: Model Context Protocol framework
- `pydantic`: Data validation
- `faiss-cpu`: Vector similarity search
- `numpy`: Numerical operations
- `yaml`: Configuration parsing
- `google-genai`: Gemini API client
- `requests`: HTTP requests (for Ollama, embeddings)
- `httpx`: Async HTTP client (for web search)
- `beautifulsoup4`: HTML parsing
- `trafilatura`: Web content extraction
- `pymupdf4llm`: PDF to markdown conversion
- `markitdown`: Document format conversion
- `pillow`: Image processing

### External Services Required
1. **Ollama** (localhost:11434):
   - Models: `nomic-embed-text`, `phi4`, `gemma3:12b`
   - Used for: Embeddings, semantic chunking, image captioning

2. **Google Gemini API**:
   - API Key: `GEMINI_API_KEY` environment variable
   - Model: `gemini-2.0-flash`
   - Used for: Text generation (perception, planning)

---

## 7. Usage Examples

### Example 1: Mathematical Query
```
User: "Find the ASCII values of INDIA and sum their exponentials"

Flow:
1. Perception → intent: "calculate", entities: ["INDIA", "ASCII"], tool_hint: "strings_to_chars_to_int"
2. Planning → FUNCTION_CALL: strings_to_chars_to_int|input.string=INDIA
3. Action → Result: [73, 78, 68, 73, 65]
4. Planning → FUNCTION_CALL: int_list_to_exponential_sum|input.int_list=[73,78,68,73,65]
5. Action → Result: <exponential sum>
6. Planning → FINAL_ANSWER: [result]
```

### Example 2: Document Search
```
User: "What do you know about Cricket and Sachin Tendulkar?"

Flow:
1. Perception → intent: "search documents", tool_hint: "search_documents"
2. Planning → FUNCTION_CALL: search_documents|query="Cricket and Sachin Tendulkar"
3. Action → Result: [relevant document chunks]
4. Planning → FINAL_ANSWER: [summary from documents]
```

---

## 8. Comparison with `code/` Folder

### Differences from `code/` (Session8/code):

1. **No Telegram/GDrive/Gmail Integration**: `code2/` doesn't have these features
2. **Simpler Agent Loop**: No shared `execute_agent()` function
3. **Different MCP Server Structure**: `mcp_server_3.py` is web search only (not Google services)
4. **No SSE Support**: No server-sent events for streaming
5. **Different Error Handling**: Less sophisticated error recovery

### Similarities:

1. **Core Architecture**: Same perception → planning → action flow
2. **Memory System**: Same FAISS-based semantic memory
3. **MCP Integration**: Same FastMCP framework
4. **Configuration**: Similar YAML-based config structure

---

## 9. Testing Recommendations

1. **Unit Tests**: Test each module independently
   - `parse_function_call()` with various formats
   - `extract_perception()` with edge cases
   - Memory retrieval with filters

2. **Integration Tests**: Test full agent loop
   - Simple math queries
   - Document search queries
   - Multi-step workflows

3. **Performance Tests**: Measure latency
   - Tool execution time
   - Memory retrieval time
   - Full loop execution time

---

## 10. Conclusion

The `code2/` folder contains a well-structured, modular AI agent system with:
- ✅ Clear separation of concerns
- ✅ Extensible tool system (MCP)
- ✅ Semantic memory integration
- ✅ Configurable behavior
- ⚠️ Some limitations (low max_steps, stateless connections)
- ⚠️ Missing features from `code/` (Telegram, GDrive, Gmail)

The codebase is production-ready with minor improvements needed for complex multi-step tasks.

