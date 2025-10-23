![](banner.jpg)

# MR Status Monitor

A desktop application for monitoring GitLab merge requests across multiple repositories with real-time status updates and automated Slack notifications.

## Purpose

MR Status Monitor provides a persistent desktop window that displays all open merge requests from your configured GitLab repositories. It shows critical status information at a glance—pipeline status, approvals, merge conflicts, and unresolved threads—eliminating the need to constantly check GitLab in your browser.

The application also automates reviewer notifications via Slack, ensuring that merge requests ready for review don't get overlooked.

## Installation

### Prerequisites

- Python 3.10 or higher
- GitLab personal access token with `api`, `read_api`, and `read_repository` scopes
- (Optional) Slack bot token for notifications

### Setup Steps

1. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Store your GitLab token in the system keyring:
   ```bash
   python -c "import keyring; keyring.set_password('gitlab', 'token', 'YOUR_GITLAB_TOKEN')"
   ```
   
   Get your token from: https://gitlab.com/-/user_settings/personal_access_tokens

3. (Optional) Store your Slack token for notifications:
   ```bash
   python -c "import keyring; keyring.set_password('slack', 'token', 'YOUR_SLACK_TOKEN')"
   ```

4. Configure your repositories in `resources/config.json`:
   ```json
   {
     "repositories": [
       {
         "name": "my-repo",
         "url": "git@gitlab.com:owner/repository.git"
       }
     ]
   }
   ```

5. Verify installation:
   ```bash
   ./run install
   ```

## Usage

### Starting the Monitor

Launch the application:
```bash
./run monitor
```

A desktop window appears displaying all open merge requests from your configured repositories. The window shows:
- Repository name
- MR number
- Branch name
- MR title
- Status indicators (colored pills)

The display updates automatically every 30 seconds.

### Interactions

**Left-click on any MR**: Opens the merge request in your browser

**Right-click on an MR**: Shows a context menu with options:
- Fix MR (opens terminal with fix-mr command)
- Open in browser
- Copy MR URL

**Right-click on a branch name**: Shows a context menu with options:
- Copy branch name
- Checkout branch locally

**Click on status pills**: Opens relevant pages (e.g., clicking pipeline status opens the pipeline page)

### Status Indicators

The application displays colored status pills indicating:

- **Pipeline** (Red): Pipeline failed
- **Pipeline** (Blue): Pipeline running or pending
- **Cancelled** (Orange): Pipeline was cancelled
- **Skipped** (Grey): Pipeline was skipped
- **No Pipeline** (Brown): No pipeline configured
- **Conflict** (Orange): Merge conflicts present
- **Threads** (Purple): Unresolved discussion threads
- **Approved** (Green): All required approvals received
- **Coverage** (Cyan): Coverage check pending

### Slack Notifications

When enabled, the application:
- Sends notifications to reviewers when MRs are ready for review
- Only notifies once per day per MR
- Only sends notifications when pipeline passes and no conflicts exist
- Mentions only reviewers who haven't approved yet
- Automatically assigns coverage reviewers when appropriate

Notification history is tracked in `output/mr_status/` to prevent duplicate alerts.

## Examples

### Basic Usage

```bash
# Start monitoring
./run monitor

# The window appears showing your MRs
# Left-click any MR to open it in browser
# Right-click for additional options
```

### Multi-Repository Setup

Configure multiple repositories in `resources/config.json`:

```json
{
  "repositories": [
    {
      "name": "backend",
      "url": "git@gitlab.com:company/backend.git"
    },
    {
      "name": "frontend",
      "url": "git@gitlab.com:company/frontend.git"
    },
    {
      "name": "mobile",
      "url": "git@gitlab.com:company/mobile.git"
    }
  ]
}
```

The monitor displays MRs from all repositories simultaneously, sorted by repository and MR number.

### Checking Installation

```bash
./run install
```

This runs an interactive check that verifies:
- Python dependencies are installed
- GitLab token is configured
- Slack token is configured (optional)
- Configuration file exists and is valid

## Troubleshooting

**"No GitLab token found"**  
Run: `python -c "import keyring; keyring.set_password('gitlab', 'token', 'YOUR_TOKEN')"`

**"Could not authenticate with GitLab"**  
Verify your token has the required scopes: `api`, `read_api`, `read_repository`

**Notifications not working**  
Check that your Slack token is stored in keyring and the Slack app has permission to post to the configured channel. Review logs in `output/mr_status/mr_notifier.log`

**Branch checkout fails**  
Ensure local repository paths are configured correctly and the working directory is clean

**Application logs**  
Review logs in the `output/` directory:
- `output/mr_status_monitor.log` - Main application log
- `output/mr_status/mr_notifier.log` - Notification system log