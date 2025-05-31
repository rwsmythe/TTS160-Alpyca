# ICD Implementation Compliance Analysis Prompt

## Task Overview
Perform comprehensive compliance analysis of a software implementation against provided Interface Control Documents (ICDs), using iterative analysis until convergence, and produce a complete issue inventory artifact.

## Required Inputs
1. **Primary ICD** - Main interface specification (e.g., ASCOM Alpaca, REST API spec)
2. **Secondary ICD** - Hardware/protocol specification (e.g., LX200, MODBUS, etc.)  
3. **Implementation Code** - Source code to analyze

## Analysis Methodology

### Iteration Process
1. **Perform initial analysis** identifying all compliance violations, implementation issues, and code quality problems
2. **Run second iteration** looking for missed issues and validating first iteration findings
3. **Continue iterations** until convergence (when new issues found ≤ 3 per iteration)
4. **Track discrepancies** between iterations, noting corrections and new discoveries
5. **Use ICDs as gold standard** - if ambiguity prevents resolution, note as ICD ambiguity rather than continue iterating

### Analysis Scope

#### ICD Compliance Verification
- **Missing required methods/properties** from specifications
- **Incorrect method signatures** (parameters, return types, async vs sync)
- **Exception handling compliance** (correct exception types per ICD)
- **Input/output validation** (ranges, types, formats per ICD specifications)
- **Protocol compliance** (command formats, response handling per secondary ICD)

#### Implementation Quality Assessment
- **Code structure** (class design, Single Responsibility Principle)
- **Documentation quality** (docstrings, type hints, parameter documentation)
- **Edge case handling** (boundary conditions, error scenarios, resource limits)
- **Thread safety** (race conditions, locking consistency, resource cleanup)
- **Redundancy identification** (duplicate code, repeated patterns, unused variables)
- **Pythonic practices** (appropriate use of language features, naming conventions)

#### Operational Readiness
- **Logging sufficiency** (troubleshooting support, operational visibility)
- **Error context** (meaningful error messages, exception chaining)
- **Resource management** (cleanup, memory leaks, connection handling)
- **Configuration handling** (validation, persistence, defaults)

## Deliverable Format

### Final Artifact Structure
Create comprehensive artifact with:

1. **Executive Summary**
   - Total issues found by category
   - Critical compliance violations count
   - Production readiness assessment

2. **Critical Issues (Must Fix)**
   - Missing required elements
   - Incorrect implementations preventing compliance
   - Each item numbered and specifically described

3. **High Priority Issues**
   - Protocol violations
   - Exception handling gaps
   - Security/reliability concerns
   - Each item numbered and specifically described

4. **Medium Priority Issues (Code Quality)**
   - Design problems
   - Code duplication (with occurrence counts)
   - Threading issues
   - Unused code
   - Magic numbers/constants
   - Each item numbered and specifically described

5. **Analysis Iteration Summary**
   - Issues found per iteration
   - Discrepancies between iterations
   - Corrections made during analysis

6. **ICD Ambiguities**
   - Areas where specifications lack clarity
   - Cannot be resolved without ICD clarification

7. **Effort Estimation**
   - Time estimates by priority category
   - Implementation assessment (strengths/weaknesses)

### Quality Requirements
- **Complete issue inventory** - Every identified issue numbered and described
- **Specific descriptions** - Avoid vague references like "multiple issues"
- **Code examples** - Show problematic code patterns where relevant
- **Priority justification** - Explain why issues are critical vs medium priority
- **Actionable recommendations** - Clear guidance for resolution

## Analysis Standards

### Use ICDs as Gold Standard
- Primary ICD defines interface requirements
- Secondary ICD defines protocol/hardware requirements
- Implementation must conform to both specifications
- Code quality assessed against Python best practices

### Iteration Convergence Criteria
- Continue until fewer than 4 new issues found per iteration
- Document all discrepancies between iterations
- Note corrections where initial assessments were wrong

### Issue Classification
- **Critical**: Prevents compliance or production use
- **High Priority**: Affects reliability or violates specifications
- **Medium Priority**: Code quality, maintainability, best practices

Analyze thoroughly using multiple passes to ensure comprehensive coverage and provide actionable results for implementation improvement.
