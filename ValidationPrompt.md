# ICD Implementation Compliance Analysis Prompt (Enhanced)

## Task Overview
Perform comprehensive compliance analysis of a software implementation against provided Interface Control Documents (ICDs), using iterative forward analysis, redundancy removal, iterative backward analysis, and produce a complete verified issue inventory artifact.

## Required Inputs
1. **Primary ICD** - Main interface specification (e.g., ASCOM Alpaca, REST API spec)
2. **Secondary ICD** - Hardware/protocol specification (e.g., LX200, MODBUS, etc.)  
3. **Implementation Code** - Source code to analyze

## Analysis Methodology

### Forward Analysis Process
**Definition**: Forward analysis identifies potential issues by examining implementation against ICD requirements, assuming discrepancies indicate problems.

1. **Perform initial analysis** identifying all compliance violations, implementation issues, and code quality problems
2. **Run second iteration** looking for missed issues and validating first iteration findings
3. **Continue iterations** until convergence (when new issues found ≤ 3 per iteration)
4. **Track discrepancies** between iterations, noting corrections and new discoveries
5. **Use ICDs as gold standard** - if ambiguity prevents resolution, note as ICD ambiguity rather than continue iterating

### Redundancy Removal
1. **Eliminate duplicate issues** reported across different categories or iterations
2. **Consolidate related issues** into single comprehensive items
3. **Remove superseded findings** where later analysis corrected earlier assessments

### Backward Analysis Process  
**Definition**: Backward analysis verifies each claimed issue by starting from the assumption it is NOT a real problem, then proving whether it actually violates ICD requirements.

1. **For each claimed issue**: Start with assumption "this is NOT a real problem"
2. **Verify against code**: Check if claimed issue actually exists in implementation
3. **Verify against ICDs**: Confirm whether behavior actually violates specifications
4. **Classify result**: Real issue, false positive, or requires specification clarification
5. **Iterate analysis** until convergence (consecutive iterations yield same verified issue count)
6. **Document verification**: Track which issues were false positives and why

### Analysis Scope

#### ICD Compliance Verification
- **Missing required methods/properties** from specifications
- **Incorrect method signatures** (parameters, return types, async vs sync)
- **Exception handling compliance** (correct exception types per ICD)
- **Input/output validation** (ranges, types, formats per ICD specifications)
- **Protocol compliance** (command formats, response handling per secondary ICD)
- **Logical consistency** (Logic flowpath results in correct outcome for each method/property)

#### Implementation Quality Assessment
- **Code structure** (class design, Single Responsibility Principle, Pythonic, Best Practices)
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
   - Total verified issues by category after backward analysis
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

5. **Medium Priority Issues**
   - Poor logic flow/redundant conditions
   - Poor pythonic implementation
   - Layout/Maintainability issues
   - Contrary to best practices
   - Logging/Documentation issues     

5. **Analysis Verification Summary**
   - Forward analysis iteration summary
   - Backward analysis results and false positive identification
   - Final issue count comparison between forward/backward analysis
   - Verification methodology explanation

6. **ICD Ambiguities**
   - Areas where specifications lack clarity
   - Cannot be resolved without ICD clarification

7. **Effort Estimation**
   - Implementation assessment (strengths/weaknesses)

### Quality Requirements
- **Complete verified issue inventory** - Every identified issue verified through backward analysis
- **False positive documentation** - Clear explanation why issues were rejected
- **Specific descriptions** - Avoid vague references like "multiple issues"
- **Requirement Wording** - Show the wording of the requirement from the applicable ICD
- **Code examples** - Show problematic code patterns where relevant
- **Priority justification** - Explain why issues are critical vs medium priority
- **Actionable recommendations** - Clear guidance for resolution

## Analysis Standards

### Use ICDs as Gold Standard
- Primary ICD defines interface requirements
- Secondary ICD defines protocol/hardware requirements
- All required capabilities in the primary ICD that are supported by the secondary ICD need to be implemented
- Not all capabilities allowed for in the secondary ICD need to be implemented
- Implementation must conform to both specifications
- Code quality assessed against Python best practices

### Forward Analysis Convergence Criteria
- Continue until fewer than 4 new issues found per iteration
- Document all discrepancies between iterations
- Note corrections where initial assessments were wrong

### Backward Analysis Verification Standards
- Each issue must be provable against actual code and ICD requirements
- For each issue reverify both the requirements within the ICD documentation and the implementation
- False positives must be documented with specific reasoning
- Convergence achieved when consecutive iterations yield same verified issue count
- Analysis must distinguish between specification violations vs. style preferences

### Issue Classification
- **Critical**: Prevents compliance or production use
- **High Priority**: Affects reliability or violates specifications
- **Medium Priority**: Code quality, maintainability, best practices

Analyze thoroughly using forward analysis until convergence, remove redundancies, then verify through backward analysis until convergence, and provide final actionable results for implementation improvement.
