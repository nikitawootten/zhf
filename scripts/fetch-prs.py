#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3


import os
import sys
import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def fetch_graphql(token, query, variables):
    """Execute a GraphQL query against GitHub's API."""
    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    data = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(url, data=data, headers=headers)

    try:
        with urlopen(request) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        print(f"Error fetching from GitHub API: {e}", file=sys.stderr)
        print(f"Response: {e.read().decode('utf-8')}", file=sys.stderr)
        sys.exit(1)


def fetch_prs(token, since_date):
    """Fetch PRs that have been merged or updated since the given date."""
    query = """
    query($owner: String!, $repo: String!, $cursor: String) {
      repository(owner: $owner, name: $repo) {
        pullRequests(first: 100, after: $cursor, orderBy: {field: UPDATED_AT, direction: DESC}) {
          pageInfo {
            hasNextPage
            endCursor
          }
          nodes {
            title
            url
            merged
            mergedAt
            updatedAt
            state
          }
        }
      }
    }
    """

    all_prs = []
    cursor = None
    should_continue = True

    while should_continue:
        variables = {
            "owner": "NixOS",
            "repo": "nixpkgs",
            "cursor": cursor,
            "since": since_date.isoformat()
        }

        result = fetch_graphql(token, query, variables)

        if "errors" in result:
            print(f"GraphQL errors: {result['errors']}", file=sys.stderr)
            sys.exit(1)

        if "data" not in result or not result["data"]["repository"]:
            print(f"Repository not accessible", file=sys.stderr)
            sys.exit(1)

        pull_requests = result["data"]["repository"]["pullRequests"]
        page_info = pull_requests["pageInfo"]

        for pr in pull_requests["nodes"]:
            updated_at = datetime.fromisoformat(pr["updatedAt"].replace("Z", "+00:00"))

            if updated_at < since_date:
                should_continue = False
                break

            is_merged = pr["merged"]
            is_open = pr["state"] == "OPEN"

            if is_merged or is_open:
                all_prs.append({
                    "title": pr["title"],
                    "link": pr["url"],
                    "merged": "true" if is_merged else "false",
                    "updated": pr["updatedAt"]
                })

        if page_info["hasNextPage"] and should_continue:
            cursor = page_info["endCursor"]
        else:
            break

    return all_prs


def main():
    parser = argparse.ArgumentParser(
        description="Fetch GitHub PRs that have been merged or updated recently"
    )
    parser.add_argument(
        "--newer-than-days",
        type=int,
        default=30,
        help="Fetch PRs merged or updated within this many days (default: 30)"
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is required", file=sys.stderr)
        sys.exit(1)

    # Calculate the cutoff date
    since_date = datetime.now(timezone.utc) - timedelta(days=args.newer_than_days)

    prs = fetch_prs(token, since_date)
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=["title", "link", "merged", "updated"],
        lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(prs)


if __name__ == "__main__":
    main()
