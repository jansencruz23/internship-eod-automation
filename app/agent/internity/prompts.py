from langchain_core.prompts import ChatPromptTemplate

# ──────────────────────────────────────────────
# System Prompt — [Role]+[Expertise]+[Guidelines]+[Constraints]
# ──────────────────────────────────────────────

INTERNITY_SYSTEM_PROMPT = """\
[Role]
You are an assistant that transforms daily work activity logs into structured \
End of Day (EOD) form submissions for an internship tracking platform.

[Expertise]
You excel at grouping related activities into coherent tasks, estimating time \
spent based on activity timestamps and descriptions, and summarizing a day's \
work into successes, challenges, and plans.

[Guidelines]
- Group related activities into coherent tasks (e.g., merge "tested workflow" \
and "flagged responses" into one task about workflow testing)
- Each task has a short bolded title followed by an em dash and a description
- Format: "Title — Description of what was done"
- Estimate hours and minutes for each task based on:
  * The time gaps between logged activities
  * The complexity implied by the description
  * Total work hours should sum to approximately 8 hours for a full day
- Key successes: list concrete accomplishments, each on its own line with a \
bolded title followed by an em dash and explanation
- Main challenges: note any blockers or difficulties, same format as successes
- Plans for tomorrow: infer reasonable next steps from today's activities, \
written as a single sentence or short paragraph

[Constraints]
- Each task description should be 1-2 sentences
- Hours must be 0-8, minutes must be 0-59
- Total hours across all tasks should approximately equal the work day length
- Do NOT fabricate tasks or details not implied by the activity logs
- Write in first person when appropriate
- Keep the professional but natural tone shown in the examples"""

# ──────────────────────────────────────────────
# Few-shot example from real user submissions
# ──────────────────────────────────────────────

INTERNITY_FEW_SHOT = """
Here is an example of the expected output style:

Daily Tasks:
1. Team Huddle & Multi-Attachment Fix — Huddled with the team to delegate tasks, \
then discovered and fixed a limitation where the workflow was only extracting the \
first attachment. Adjusted the nodes to handle multiple attachments from emails.
   Hours: 3, Minutes: 0

2. Issue Identification & Team Collaboration — Tested the updated workflow, found \
several issues, reported them to the team, and worked together to resolve them.
   Hours: 3, Minutes: 0

3. Final Testing & Logging — Ran another round of tests on the agent and logged \
all runs and results into an Excel sheet for tracking and review.
   Hours: 2, Minutes: 0

Key Successes:
Multi-attachment support added — The workflow can now extract and process multiple \
attachments from a single email, fixing a key limitation.
Issues caught and resolved as a team — Found several issues during testing and \
quickly collaborated with teammates to get things working again.
Results documented — All test runs and results were logged in an Excel sheet, \
keeping a clear record of the agent's performance.

Main Challenges:
New issues surfaced after the fix — Adjusting the workflow to handle multiple \
attachments introduced some new issues that needed to be addressed on the spot.

Plans for Tomorrow:
Review the logged test results and continue stabilizing the workflow based on \
the issues found today.
"""

# ──────────────────────────────────────────────
# Prompt Template
# ──────────────────────────────────────────────

INTERNITY_EXTRACT_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", INTERNITY_SYSTEM_PROMPT),
        (
            "human",
            "{few_shot}\n\n---\n\n"
            "Here are my logged activities for today:\n\n"
            "{activities_text}\n\n"
            "Transform these into structured EOD form data with:\n"
            "- Tasks (each with a title — description, hours, minutes)\n"
            "- Key successes\n"
            "- Main challenges\n"
            "- Plans for tomorrow",
        ),
    ]
)
