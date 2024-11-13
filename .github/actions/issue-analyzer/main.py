#!/usr/bin/env python3
import os
import sys
import json
import argparse
from typing import Dict, Any, Tuple, Optional
import re
from anthropic import Anthropic
from github import Github
from github.Issue import Issue
from github.GithubException import GithubException

from prompt import render_prompt

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
        print(f"GitHub API error: {e}", file=sys.stderr)
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
        print("Full Claude Response:")
        print("=" * 50)
        print(full_response)
        print("=" * 50)
        
        # Only post comment if there's content in response tags
        if response_tag_content:
            post_comment(issue, response_tag_content)
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
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
        
        # Print complete analysis for debugging
        print("\nAnalysis Results")
        print("=" * 50)
        print(f"Repository: {repo}")
        print(f"Issue: #{issue_number}")
        print(f"Title: {title}")
        print("-" * 50)
        print("Full Claude Response:")
        print(full_response)
        print("-" * 50)
        print("Response Tag Content:")
        print(response_tag_content if response_tag_content else "No response tag content")
        print("=" * 50)

    except Exception as e:
        print(f"Error in local test mode: {str(e)}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description='GitHub Issue Analyzer with Claude AI')
    parser.add_argument('--test', action='store_true', help='Run in local test mode')
    parser.add_argument('--repo', help='Repository name (format: owner/repo) for test mode')
    parser.add_argument('--issue', type=int, help='Issue number for test mode')
    args = parser.parse_args()

    # Check for API keys
    if not os.getenv('ANTHROPIC_API_KEY'):
        print("Error: ANTHROPIC_API_KEY not set in environment", file=sys.stderr)
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