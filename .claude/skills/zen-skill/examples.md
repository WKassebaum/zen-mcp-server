# Zen - Real Usage Examples

This document contains actual examples from Zen usage, demonstrating effective patterns for AI orchestration and multi-model collaboration.

**Available in two forms:**
- **MCP Tools** - When MCP server is enabled (`mcp__zen__*`)
- **CLI Commands** - Always available via `zen` command

Each example shows **both MCP and CLI syntax** so you can use whichever is available.

---

## 🔄 MCP vs CLI Examples

### Quick Test: Check if Zen Works

**MCP (if server enabled):**
```python
mcp__zen__listmodels()  # Should return list of available models
```

**CLI (always available):**
```bash
zen listmodels  # Should list configured models
```

**If MCP fails but CLI works:** Use CLI versions of commands below.

---

## Example 1: Quick Technical Consultation

### Scenario
Need a second opinion on caching strategy for a high-traffic API

### MCP Version (when server enabled)

```python
mcp__zen__chat(
    prompt="""We're building a high-traffic API (10k req/s) and considering caching strategies.

    Current options:
    1. Redis cluster (familiar, proven)
    2. Memcached (simpler, faster?)
    3. In-memory with clustering (lower latency)

    What are the real tradeoffs? Our data is mostly read-heavy, sessions + API responses.""",
    model="gemini-2.5-pro",
    working_directory="/Users/wrk/projects/api-service"
)
```

### CLI Version (always available)

```bash
zen chat "We're building a high-traffic API (10k req/s) and considering caching strategies.

Current options:
1. Redis cluster (familiar, proven)
2. Memcached (simpler, faster?)
3. In-memory with clustering (lower latency)

What are the real tradeoffs? Our data is mostly read-heavy, sessions + API responses." \
  --model gemini-2.5-pro
```

**Why This Works:**
- ✅ Specific context (10k req/s, read-heavy workload)
- ✅ Clear options being evaluated
- ✅ Asks for tradeoffs, not just "what's best"
- ✅ Provides use case details (sessions + API responses)
- ✅ Uses high-capability model for nuanced analysis
- ✅ **CLI version works even when MCP is disabled**

## Example 2: Multi-Model Consensus for Critical Decision

### Scenario
Deciding whether to migrate from monolith to microservices

### MCP Version (when server enabled)

```python
mcp__zen__consensus(
    step="""Evaluate: Should we migrate our Django monolith (50k LOC, 8 engineers) to microservices?

Context:
- Current pain: Deploy bottlenecks, slow CI/CD (45min builds)
- Team: Strong Python, learning Go/Node
- Scale: 100k DAU, expected 2x growth in 6mo
- Budget: 2 engineers can dedicate 3mo to migration

Evaluate technical feasibility, team readiness, and ROI.""",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Starting consensus workflow for microservices migration decision",
    models=[
        {"model": "gemini-2.5-pro", "stance": "neutral"},
        {"model": "gpt-5", "stance": "for"},
        {"model": "o3", "stance": "against"}
    ],
    relevant_files=[
        "/Users/wrk/projects/api/architecture.md",
        "/Users/wrk/projects/api/deployment.yaml"
    ]
)
```

### CLI Version (always available)

```bash
zen consensus "Evaluate: Should we migrate our Django monolith (50k LOC, 8 engineers) to microservices?

Context:
- Current pain: Deploy bottlenecks, slow CI/CD (45min builds)
- Team: Strong Python, learning Go/Node
- Scale: 100k DAU, expected 2x growth in 6mo
- Budget: 2 engineers can dedicate 3mo to migration

Evaluate technical feasibility, team readiness, and ROI." \
  --models gemini-2.5-pro,gpt-5,o3 \
  -f architecture.md -f deployment.yaml
```

**Why This Works:**
- ✅ Comprehensive context (LOC, team size, pain points)
- ✅ Specific constraints (budget, timeline, team skills)
- ✅ Uses multiple models for balanced perspective
- ✅ Includes relevant architecture documentation
- ✅ **CLI version: simpler syntax, same quality**

## Example 3: Systematic Debugging Workflow

### Scenario
OAuth tokens not persisting, causing users to re-login constantly

### MCP Version (when server enabled)

```python
mcp__zen__debug(
    step="""OAuth tokens not persisting across requests. Users report being logged out after 1-2 minutes.

Initial observations:
- Token generation works (verified in logs)
- Database shows tokens being created
- Middleware appears to load user correctly
- Issue only in production, not local dev

Starting investigation with session configuration.""",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Token creation confirmed working. Issue likely in session persistence or cookie handling.",
    hypothesis="Cookie domain or secure flag misconfiguration in production environment",
    confidence="low",
    model="gemini-2.5-pro",
    relevant_files=[
        "/Users/wrk/projects/api/src/auth/oauth.py",
        "/Users/wrk/projects/api/src/middleware/session.py",
        "/Users/wrk/projects/api/config/production.py"
    ],
    files_checked=[
        "/Users/wrk/projects/api/src/auth/oauth.py"
    ]
)

# Step 2: After finding cookie configuration
mcp__zen__debug(
    step="""Examined session middleware configuration. Found suspicious cookie settings:

production.py:
  SESSION_COOKIE_SECURE = True
  SESSION_COOKIE_DOMAIN = '.example.com'
  SESSION_COOKIE_SAMESITE = 'Strict'

API is served from api.example.com but frontend is app.example.com.
SameSite=Strict might be blocking cross-domain cookies.""",
    step_number=2,
    total_steps=3,
    next_step_required=True,
    findings="Cookie SameSite policy set to Strict. This blocks cookies in cross-domain requests between app.example.com and api.example.com",
    hypothesis="SameSite=Strict preventing cookies from being sent in cross-origin requests from frontend to API",
    confidence="high",
    model="gemini-2.5-pro",
    relevant_files=[
        "/Users/wrk/projects/api/config/production.py",
        "/Users/wrk/projects/api/src/middleware/session.py"
    ],
    files_checked=[
        "/Users/wrk/projects/api/src/auth/oauth.py",
        "/Users/wrk/projects/api/config/production.py",
        "/Users/wrk/projects/api/config/development.py"
    ],
    continuation_id="debug-oauth-session-123"
)
```

**Why This Works:**
- ✅ Starts with low confidence, increases with evidence
- ✅ Documents what was checked (files_checked)
- ✅ Updates hypothesis as investigation progresses
- ✅ Provides specific code snippets as evidence
- ✅ Uses continuation_id to maintain context
- ✅ Clear progression from symptoms → hypothesis → evidence → solution

### CLI Version (always available)

```bash
# CLI debug provides simpler syntax with natural language
zen debug "OAuth tokens not persisting. Users logged out after 1-2 minutes.
Token generation works, issue only in production." \
  -f src/auth/oauth.py -f src/middleware/session.py -f config/production.py \
  --model gemini-2.5-pro

# Zen will guide you through investigation steps
# Follow prompts to update findings and hypothesis
```

**CLI Benefits:**
- ✅ Simpler syntax - just describe the problem
- ✅ Interactive prompts guide investigation
- ✅ Same systematic analysis as MCP version
- ✅ **Works when MCP server is unavailable**

---

## 📝 Note on Remaining Examples

Examples 4-10 below show MCP syntax. **For CLI equivalents**, follow this pattern:

```bash
# MCP tool name → CLI command
mcp__zen__codereview → zen codereview
mcp__zen__analyze → zen analyze
mcp__zen__planner → zen planner
mcp__zen__refactor → zen refactor
mcp__zen__testgen → zen testgen
mcp__zen__precommit → zen precommit
mcp__zen__secaudit → zen secaudit

# Use --help to see options
zen codereview --help
zen analyze --help
```

**When to use CLI:** If MCP tools show "not available", use `zen <command>` instead.

---

## Example 4: Comprehensive Code Review

**Scenario:** Reviewing authentication module before production deployment

```python
# Step 1: Security-focused review
mcp__zen__codereview(
    step="""Reviewing authentication module for security vulnerabilities before production deployment.

Focus areas:
1. Password hashing (bcrypt implementation)
2. Token generation (JWT implementation)
3. Session management
4. Rate limiting
5. Input validation

Starting with password and token handling.""",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Beginning systematic security review of authentication module",
    model="o3",
    relevant_files=[
        "/Users/wrk/projects/api/src/auth/password.py",
        "/Users/wrk/projects/api/src/auth/tokens.py",
        "/Users/wrk/projects/api/src/auth/session.py",
        "/Users/wrk/projects/api/src/middleware/rate_limit.py"
    ],
    review_type="security",
    confidence="exploring",
    issues_found=[]
)
```

**Why This Works:**
- ✅ Specific review type (security)
- ✅ Clear focus areas documented
- ✅ Uses o3 model for precision security analysis
- ✅ Includes all relevant authentication files
- ✅ Multi-step workflow for thorough coverage

## Example 5: Architecture Analysis

**Scenario:** Understanding a complex microservices codebase after joining team

```python
mcp__zen__analyze(
    step="""New team member analyzing microservices architecture to understand system design.

Goals:
1. Map service boundaries and responsibilities
2. Understand data flow between services
3. Identify communication patterns (sync/async)
4. Document dependencies
5. Assess scalability characteristics

Starting with service discovery and gateway configuration.""",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Initial architecture mapping. Found 12 services, API gateway, message queue for async communication.",
    model="gemini-2.5-pro",
    relevant_files=[
        "/Users/wrk/projects/microservices/docker-compose.yml",
        "/Users/wrk/projects/microservices/gateway/routes.yaml",
        "/Users/wrk/projects/microservices/docs/architecture.md"
    ],
    analysis_type="architecture",
    confidence="exploring"
)
```

**Why This Works:**
- ✅ Clear goals for analysis
- ✅ Systematic approach to understanding
- ✅ Includes infrastructure and documentation files
- ✅ Architecture-specific analysis type
- ✅ Appropriate for onboarding and knowledge transfer

## Example 6: Complex Feature Planning

**Scenario:** Planning implementation of real-time collaboration feature

```python
mcp__zen__planner(
    step="""Plan implementation of real-time collaboration feature for document editing.

Requirements:
- Multi-user editing with conflict resolution
- Real-time cursor positions and selections
- Presence awareness (who's viewing/editing)
- Undo/redo across collaborative sessions
- Must handle 50+ concurrent editors per document

Tech stack: React frontend, Node.js backend, considering WebSockets or WebRTC

Break down into phases, identify risks, estimate effort.""",
    step_number=1,
    total_steps=1,
    next_step_required=False,
    model="gemini-2.5-pro"
)
```

**Why This Works:**
- ✅ Comprehensive requirements
- ✅ Specific scale requirements (50+ concurrent users)
- ✅ Technology constraints mentioned
- ✅ Asks for phases, risks, and estimates
- ✅ Single-step planning for initial breakdown

## Example 7: Refactoring Analysis

**Scenario:** Large controller method needs refactoring (code smells)

```python
mcp__zen__refactor(
    step="""Analyzing UserController.createUser() method for refactoring opportunities.

Current issues:
- 250 lines in single method
- Handles validation, database, email, billing, logging
- Complex nested conditionals (6 levels deep)
- Difficult to test, hard to modify

Looking for decomposition opportunities and code smell patterns.""",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Starting code smell analysis and decomposition planning",
    model="gemini-2.5-pro",
    refactor_type="codesmells",
    confidence="incomplete",
    relevant_files=[
        "/Users/wrk/projects/api/src/controllers/UserController.py"
    ]
)
```

**Why This Works:**
- ✅ Specific method identified
- ✅ Current problems documented
- ✅ Clear refactoring goals
- ✅ Appropriate refactor_type
- ✅ Confidence set to "incomplete" for thorough analysis

## Example 8: Test Generation

**Scenario:** Generating comprehensive tests for payment processing module

```python
mcp__zen__testgen(
    step="""Generate comprehensive test suite for payment processing module.

Coverage needed:
1. Successful payment flows (credit card, ACH, wallet)
2. Failed transactions (declined, insufficient funds, network errors)
3. Edge cases (zero amount, negative amount, currency mismatches)
4. Concurrency issues (double charging, race conditions)
5. Security (token validation, amount tampering)

Framework: pytest
Database: PostgreSQL with test fixtures""",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Identifying test scenarios for payment processing with focus on edge cases and security",
    model="gpt-5",
    relevant_files=[
        "/Users/wrk/projects/api/src/payments/processor.py",
        "/Users/wrk/projects/api/src/payments/models.py"
    ]
)
```

**Why This Works:**
- ✅ Comprehensive coverage areas specified
- ✅ Framework and database context provided
- ✅ Includes security and edge case requirements
- ✅ Focus on real-world failure modes
- ✅ Uses gpt-5 for code generation capability

## Example 9: Pre-Commit Validation

**Scenario:** Validating major refactoring before committing

```python
mcp__zen__precommit(
    step="""Validating refactoring of authentication module before commit.

Changes:
- Extracted password hashing to separate service
- Moved token generation to JWT service
- Updated 15 files across auth module
- Added new dependency on PyJWT library

Validate: breaking changes, test coverage, security implications""",
    step_number=1,
    total_steps=3,
    next_step_required=True,
    findings="Reviewing authentication refactoring for breaking changes and security impact",
    model="o3",
    path="/Users/wrk/projects/api",
    confidence="exploring",
    include_staged=True,
    include_unstaged=True
)
```

**Why This Works:**
- ✅ Clear description of changes
- ✅ Specifies validation criteria
- ✅ Includes both staged and unstaged changes
- ✅ Uses o3 for precision analysis
- ✅ Multi-step workflow for thorough validation

## Example 10: Security Audit

**Scenario:** Comprehensive security audit before launch

```python
mcp__zen__secaudit(
    step="""Comprehensive security audit of API before production launch.

Focus areas:
1. OWASP Top 10 vulnerabilities
2. Authentication and authorization
3. Input validation and sanitization
4. SQL injection vectors
5. XSS protection
6. CSRF protection
7. Rate limiting
8. API key management

Application: FastAPI REST API with PostgreSQL""",
    step_number=1,
    total_steps=2,
    next_step_required=True,
    findings="Starting OWASP Top 10 security audit",
    model="o3",
    relevant_files=[
        "/Users/wrk/projects/api/src/",
        "/Users/wrk/projects/api/middleware/",
        "/Users/wrk/projects/api/config/"
    ],
    audit_focus="owasp",
    security_scope="web API, REST, FastAPI, PostgreSQL",
    threat_level="high"
)
```

**Why This Works:**
- ✅ Comprehensive audit scope
- ✅ Specific focus areas (OWASP Top 10)
- ✅ Application context provided
- ✅ Appropriate threat level set
- ✅ Uses o3 for security precision

## Common Anti-Patterns to Avoid

### ❌ Anti-Pattern 1: Insufficient Context

**Bad:**
```python
mcp__zen__chat(
    prompt="Should I use Redis?",
    model="gemini-2.5-pro",
    working_directory="/Users/wrk/project"
)
```

**Good:**
```python
mcp__zen__chat(
    prompt="""Should I use Redis for session storage in our e-commerce API?

Context:
- 50k concurrent users expected
- Session data: user cart (100KB avg), preferences
- Current: PostgreSQL sessions causing DB load
- Infrastructure: AWS, Docker, Kubernetes
- Budget: Can add managed Redis if ROI is clear""",
    model="gemini-2.5-pro",
    working_directory="/Users/wrk/project"
)
```

### ❌ Anti-Pattern 2: Wrong Model for Task

**Bad:**
```python
# Using flash model for complex security analysis
mcp__zen__secaudit(
    model="gemini-2.5-flash",  # Too lightweight for security
    # ... rest of parameters
)
```

**Good:**
```python
# Using precision model for security analysis
mcp__zen__secaudit(
    model="o3",  # Precision model for security work
    # ... rest of parameters
)
```

### ❌ Anti-Pattern 3: Skipping Workflow Steps

**Bad:**
```python
# Jumping to "certain" confidence without investigation
mcp__zen__debug(
    step="The bug is in the cache layer",
    confidence="certain",  # No investigation done!
    # ... rest of parameters
)
```

**Good:**
```python
# Progressive confidence with evidence
mcp__zen__debug(
    step="Investigating cache-related timeout. Examining cache configuration and monitoring logs.",
    confidence="exploring",  # Start with low confidence
    # ... gather evidence, then increase confidence in subsequent steps
)
```

### ❌ Anti-Pattern 4: Not Using Continuation IDs

**Bad:**
```python
# Starting new workflow each time, losing context
mcp__zen__debug(step="Found error in logs", ...)
# Later, without continuation_id
mcp__zen__debug(step="Checking database", ...)  # Lost previous context!
```

**Good:**
```python
# First call
response = mcp__zen__debug(step="Found error in logs", ...)
continuation_id = response["continuation_offer"]["continuation_id"]

# Subsequent calls with same context
mcp__zen__debug(
    step="Checking database connections",
    continuation_id=continuation_id,  # Maintains context
    # ...
)
```

### ❌ Anti-Pattern 5: Dumping Code Instead of File Paths

**Bad:**
```python
mcp__zen__codereview(
    step="""Review this code:

    ```python
    [500 lines of code pasted here]
    ```
    """,
    # ... no relevant_files provided
)
```

**Good:**
```python
mcp__zen__codereview(
    step="Review authentication module for security issues",
    relevant_files=[
        "/Users/wrk/projects/api/src/auth/password.py",
        "/Users/wrk/projects/api/src/auth/tokens.py"
    ],
    # Tools will read files with proper context
)
```

## Integration Tips

### 1. **Development Workflow Stage: Design & Planning**

Use `chat` for brainstorming, `planner` for breaking down work:

```python
# Explore approaches
mcp__zen__chat(prompt="Compare REST vs GraphQL for our use case", ...)

# Break down implementation
mcp__zen__planner(step="Plan GraphQL migration from REST API", ...)
```

### 2. **Development Workflow Stage: Implementation**

Use `debug` when stuck, `refactor` for quality:

```python
# When debugging takes >5 minutes
mcp__zen__debug(step="Investigation OAuth token expiry issue", ...)

# Before implementing complex logic
mcp__zen__refactor(step="Analyze UserService for decomposition opportunities", ...)
```

### 3. **Development Workflow Stage: Testing**

Use `testgen` for comprehensive coverage:

```python
mcp__zen__testgen(
    step="Generate edge case tests for payment processing",
    relevant_files=["/path/to/payment/processor.py"]
)
```

### 4. **Development Workflow Stage: Review & Commit**

Use `codereview` and `precommit` before committing:

```python
# Review code quality
mcp__zen__codereview(
    step="Security review of authentication changes",
    review_type="security"
)

# Validate changes
mcp__zen__precommit(
    step="Validate refactoring before commit",
    path="/Users/wrk/project"
)
```

### 5. **Decision Making at Crossroads**

Use `consensus` for critical technical decisions:

```python
mcp__zen__consensus(
    step="Evaluate migration from PostgreSQL to MongoDB",
    models=[
        {"model": "gemini-2.5-pro", "stance": "neutral"},
        {"model": "gpt-5", "stance": "for"},
        {"model": "o3", "stance": "against"}
    ]
)
```

## Performance Considerations

### When to Use Zen MCP

**✅ Optimal Use Cases:**
- Complex debugging (>5 min stuck)
- Critical architecture decisions
- Security-sensitive code review
- Performance bottleneck analysis
- Large-scale refactoring planning
- Multi-model perspective needed

**⚠️ Consider Alternatives:**
- Simple questions (use regular Claude conversation)
- Quick code snippets (no need for workflows)
- Well-defined tasks (direct implementation)
- Time-critical fixes (workflow overhead may slow you down)

### Model Selection for Performance

**Fast Models (gemini-2.5-flash, gpt-4o-mini):**
- Quick consultations
- Iterative workflows with many steps
- Code generation tasks
- When speed > depth

**Deep Models (gemini-2.5-pro, gpt-5, o3):**
- Architecture decisions
- Security analysis
- Complex debugging
- When depth > speed

### Managing Workflow Overhead

**Single-Step When Possible:**
```python
# For simple consultations, use chat
mcp__zen__chat(prompt="Quick question about Redis TTL", ...)
```

**Multi-Step for Complexity:**
```python
# For investigations, embrace multi-step workflows
mcp__zen__debug(
    step_number=1,
    total_steps=3,  # Plan for thorough investigation
    next_step_required=True
)
```

---

These examples demonstrate real patterns from Zen MCP usage across debugging, architecture decisions, code review, and planning. Adapt them to your specific use cases while maintaining the core principles of providing context, progressive confidence, and systematic workflows.
