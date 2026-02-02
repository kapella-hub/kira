"""Predefined coding workflow."""

from .models import Stage, Workflow

# Coding workflow: architect -> coder -> reviewer -> docs
CODING_WORKFLOW = Workflow(
    name="coding",
    description="Multi-stage workflow for coding tasks",
    triggers=[
        "implement",
        "create",
        "add feature",
        "build",
        "code",
        "develop",
        "write",
        "make",
    ],
    stages=[
        Stage(
            name="architect",
            description="Design the solution architecture",
            agent="architect",
            prompt_template="""Design the architecture for this task:

{original_prompt}

Provide:
1. High-level approach
2. Component breakdown
3. File changes needed
4. Key decisions and rationale

Output a structured design that a coder can implement.
""",
            output_key="architecture",
        ),
        Stage(
            name="coder",
            description="Implement the solution",
            agent="coder",
            prompt_template="""Implement this task based on the architecture:

## Original Task
{original_prompt}

## Architecture Design
{architecture}

Implement the solution. Make all necessary code changes.
Follow the architecture design closely.
""",
            depends_on=["architect"],
            output_key="implementation",
        ),
        Stage(
            name="reviewer",
            description="Review the implementation",
            agent="reviewer",
            prompt_template="""Review this implementation:

## Original Task
{original_prompt}

## Architecture
{architecture}

## Implementation
{implementation}

Provide a thorough code review:
- Issues found (critical, important, suggestions)
- Security concerns
- Performance considerations

End with: APPROVE or REQUEST_CHANGES
""",
            depends_on=["coder"],
            required=False,  # Can be skipped
            output_key="review",
        ),
        Stage(
            name="docs",
            description="Update documentation",
            agent="documenter",
            prompt_template="""Update documentation for this change:

## Task
{original_prompt}

## Implementation Summary
{implementation}

Update relevant documentation:
- README if needed
- Code comments for non-obvious logic
- API documentation if applicable
- Usage examples if helpful
""",
            depends_on=["coder"],
            required=False,  # Can be skipped
            output_key="documentation",
        ),
    ],
)


# Quick coding workflow (no review or docs)
QUICK_CODING_WORKFLOW = Workflow(
    name="quick-coding",
    description="Fast coding workflow (architect + coder only)",
    triggers=["quick", "fast", "just code"],
    stages=[
        Stage(
            name="architect",
            description="Quick architecture design",
            agent="architect",
            prompt_template="""Quickly design the approach for:

{original_prompt}

Keep it brief - just the essential structure and approach.
""",
            output_key="architecture",
        ),
        Stage(
            name="coder",
            description="Implement the solution",
            agent="coder",
            prompt_template="""Implement based on this design:

## Task
{original_prompt}

## Approach
{architecture}

Implement the solution.
""",
            depends_on=["architect"],
            output_key="implementation",
        ),
    ],
)


# Available workflows
WORKFLOWS: dict[str, Workflow] = {
    "coding": CODING_WORKFLOW,
    "quick-coding": QUICK_CODING_WORKFLOW,
}


def get_workflow(name: str) -> Workflow | None:
    """Get a workflow by name."""
    return WORKFLOWS.get(name)


def list_workflows() -> list[Workflow]:
    """List all available workflows."""
    return list(WORKFLOWS.values())
