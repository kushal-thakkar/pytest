#!/usr/bin/env python3
import os
import sys
import json
import argparse
import logging
from typing import Dict, Any, Tuple, Optional, List
import re
from anthropic import Anthropic
from github import Github
from github.Issue import Issue
from github.GithubException import GithubException

from prompt import render_prompt, DEFAULT_LABEL_MAPPING

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


def get_label_mapping() -> Dict[str, str]:
    """Get label mapping from environment or use defaults."""
    return DEFAULT_LABEL_MAPPING

def extract_decision_tag(analysis: str) -> Optional[str]:
    """Extract content between <decision> tags if present."""
    decision_match = re.search(r'<decision>(.*?)</decision>', analysis, re.DOTALL)
    return decision_match.group(1).strip() if decision_match else None

def should_add_label(issue: Issue) -> bool:
    """Check if the issue should receive an auto-label."""
    # If issue already has any labels, don't add more
    return len(list(issue.get_labels())) == 0

def add_label_to_issue(issue: Issue, decision: str, label_mapping: Dict[str, str]):
    """Add appropriate label based on Claude's decision."""
    if not should_add_label(issue):
        logging.info(f"Issue #{issue.number} already has labels - skipping label addition")
        return
        
    label_name = label_mapping.get(decision.strip())
    if label_name:
        try:
            issue.add_to_labels(label_name)
            logging.info(f"Added label '{label_name}' to issue #{issue.number}")
        except GithubException as e:
            logging.error(f"Failed to add label '{label_name}' to issue #{issue.number}: {e}")
    else:
        logging.warning(f"No matching label found for decision: {decision}")

def load_prompt(project: str, title: str, body: str) -> str:
    """Load and format the prompt template."""
    return render_prompt(
        project=project,
        title=title,
        body=body
    )

def get_github_event() -> Dict[str, Any]:
    """Read GitHub event data from the event file."""
    event_path = os.getenv('GITHUB_EVENT_PATH')
    if not event_path:
        raise ValueError("GITHUB_EVENT_PATH not set")
    
    with open(event_path, 'r') as f:
        return json.load(f)

def fetch_issue(repo_name: str, issue_number: int) -> Tuple[str, str]:
    """
    Fetch a GitHub issue and return its title and body.
    
    Args:
        repo_name: Repository name in format 'owner/repo'
        issue_number: Issue number to fetch
        
    Returns:
        Tuple of (title, body)
    """
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        raise ValueError("GITHUB_TOKEN environment variable not set")
    
    try:
        gh = Github(github_token)
        repo = gh.get_repo(repo_name)
        issue = repo.get_issue(number=issue_number)
        return issue.title, issue.body
        
    except GithubException as e:
        logger.error(f"GitHub API error: {e}")
        sys.exit(1)

def extract_response_tag(analysis: str) -> Optional[str]:
    """Extract content between <response> tags if present."""
    response_match = re.search(r'<response>(.*?)</response>', analysis, re.DOTALL)
    return response_match.group(1).strip() if response_match else None

def analyze_issue_with_claude(project: str, issue_title: str, issue_body: str) -> Tuple[str, Optional[str]]:
    """
    Analyze an issue using Claude AI.
    Returns tuple of (full_response, response_tag_content)
    """
    anthropic = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
    
    prompt = load_prompt(project, issue_title, issue_body)
    
    message = anthropic.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": prompt
        }]
    )
    
    full_response = message.content[0].text
    response_tag_content = extract_response_tag(full_response)
    
    return full_response, response_tag_content

def post_comment(issue: Issue, comment_text: str):
    """Post a comment on the issue."""
    issue.create_comment(comment_text)

def github_workflow_mode():
    """Handle GitHub workflow action mode."""
    try:
        github_token = os.getenv('GITHUB_TOKEN')
        if not github_token:
            raise ValueError("GITHUB_TOKEN not set")
        
        gh = Github(github_token)
        
        event = get_github_event()
        issue_data = event['issue']
        
        repo_name = os.getenv('GITHUB_REPOSITORY')
        if not repo_name:
            raise ValueError("GITHUB_REPOSITORY not set")
        
        repo = gh.get_repo(repo_name)
        issue = repo.get_issue(number=issue_data['number'])
        
        # Get project name from repo
        project = repo_name.split('/')[-1]
        
        # Analyze issue with Claude
        full_response, response_tag_content = analyze_issue_with_claude(
            project=project,
            issue_title=issue_data['title'],
            issue_body=issue_data['body']
        )
        
        # Log full response for debugging
        logger.debug("Full Claude Response:")
        logger.debug("=" * 50)
        logger.debug(full_response)
        logger.debug("=" * 50)

        # Extract decision tag content
        decision = extract_decision_tag(full_response)
        if decision:
            # Get label mapping and add label if appropriate
            label_mapping = get_label_mapping()
            add_label_to_issue(issue, decision, label_mapping)
        
        # Only post comment if there's content in response tags
        if response_tag_content:
            post_comment(issue, response_tag_content)
        
    except Exception as e:
        logger.error(f"Error in workflow mode: {str(e)}")
        sys.exit(1)

def local_test_mode(repo: str, issue_number: int):
    """Handle local testing mode by fetching and analyzing a GitHub issue."""
    try:
        # Fetch the issue
        title, body = fetch_issue(repo, issue_number)
        
        # Get project name from repo
        project = repo.split('/')[-1]
        
        # Get analysis from Claude
        full_response, response_tag_content = analyze_issue_with_claude(project, title, body)

        # Extract decision for testing
        decision = extract_decision_tag(full_response)
        
        # Log complete analysis for debugging
        logger.info("\nAnalysis Results")
        logger.info("=" * 50)
        logger.info(f"Repository: {repo}")
        logger.info(f"Issue: #{issue_number}")
        logger.info(f"Title: {title}")
        logger.info("-" * 50)
        logger.info("Full Claude Response:")
        logger.info(full_response)
        logger.info("-" * 50)
        logger.info("Response Tag Content:")
        logger.info(response_tag_content if response_tag_content else "No response tag content")
        logger.info("-" * 50)
        logger.info("Decision Tag Content:")
        logger.info(decision if decision else "No decision tag content")
        logger.info("=" * 50)

        # Show what label would be added in non-test mode
        if decision:
            label_mapping = get_label_mapping()
            label = label_mapping.get(decision.strip())
            if label:
                logger.info(f"Would add label: {label}")
            else:
                logger.warning(f"No matching label found for decision: {decision}")

    except Exception as e:
        logger.error(f"Error in local test mode: {str(e)}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='GitHub Issue Analyzer with Claude AI')
    parser.add_argument('--test', action='store_true', help='Run in local test mode')
    parser.add_argument('--repo', help='Repository name (format: owner/repo) for test mode')
    parser.add_argument('--issue', type=int, help='Issue number for test mode')
    args = parser.parse_args()

    # Check for API keys
    if not os.getenv('ANTHROPIC_API_KEY'):
        logger.error("ANTHROPIC_API_KEY not set in environment")
        sys.exit(1)

    if args.test:
        # Validate test mode arguments
        if not args.repo or not args.issue:
            parser.error("Test mode requires both --repo and --issue arguments")
        
        # Local test mode
        local_test_mode(args.repo, args.issue)
    else:
        # GitHub workflow action mode
        github_workflow_mode()

if __name__ == "__main__":
    main()