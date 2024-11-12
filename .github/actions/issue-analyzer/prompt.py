from jinja2 import Template

ISSUE_ANALYSIS_PROMPT = """You are about to see a post from a Github user filing a Github Issue with the open source project {{project}}.
Your task will be to (1) discern whether the issue is a bug report that is not actionable, and if so then (2) show the user as clearly as possible what an MRE for their bug report would look like.
First, in <thinking> tags, evaluate (a) whether this is a bug report, or some other type of issue (such as a feature request or a general discussion), and (b) if a bug report, how actionable it seems to be.
Second, in <decision> tags, output either “BUG REPORT - ACTIONABLE", “BUG REPORT - NOT ACTIONABLE”, or "OTHER"
If you chose “BUG REPORT - ACTIONABLE" or "OTHER", then stop here.
Only if you chose “BUG REPORT - NOT ACTIONABLE”, then third, use <scratchpad> tags to brainstorm how you could most clearly teach and handhold this user to understanding what they need to provide. Remember, if this user did not *already* provide an MRE, they are likely an inexperienced open source contributor, and do not already have in mind what an actionable issue would look like. Make reference to what they reported. Avoid unnecessary wordiness. This is going to be your only post on the thread (you won't be returning), so don't offer to personally help more with the issue.
Finally, if you chose “BUG REPORT - NOT ACTIONABLE”, output your response between <response> tags (use both opening and closing tags). Keep your response focused and concise. This response will be posted *verbatim* as a reply on the github comment thread on behalf of the project maintainers, so ensure it is complete and does not contain placeholders or templates.
Here is the post from user:
{{title}}
{{issue}}
"""

def render_prompt(project: str, title: str, body: str) -> str:
    """Render the prompt template with the given variables."""
    template = Template(ISSUE_ANALYSIS_PROMPT)
    return template.render(
        project=project,
        title=title,
        body=body
    )
