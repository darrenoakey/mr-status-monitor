# MR Status Monitor - Release Notes

## Release Information

**Version:** 1.0.0
**Release Date:** 2025-10-23
**Status:** Ready for Use

## What's New

This is the initial releasable version of the MR Status Monitor, refactored from the internal prototype to follow production standards.

### Core Features

- **Real-time GitLab MR Monitoring**: Monitors multiple repositories simultaneously
- **Visual Status Indicators**: Color-coded pills for pipeline status, approvals, conflicts, and threads
- **Slack Notifications**: Automatic daily notifications to reviewers when MRs are ready
- **Branch Management**: One-click branch checkout from the UI
- **Coverage Automation**: Auto-assigns coverage reviewers when conditions are met
- **Interactive UI**: Drag-and-drop window with context menus and keyboard shortcuts

### Technical Improvements

- **Clean Architecture**: Follows DRY, KISS, and YAGNI principles
- **Separation of Concerns**: Pure functions for all GitLab API interactions
- **Proper Logging**: Structured logging to files for debugging
- **State Management**: Persistent notification tracking to avoid duplicate alerts
- **Error Handling**: Graceful degradation with user-friendly error messages
- **Type Safety**: Comprehensive type hints throughout the codebase

## Installation

See [README.md](README.md) for detailed installation instructions.

Quick start:
```bash
cd ~/src/mr-status-monitor
./run install     # Interactive setup
./run monitor     # Start the application
```

## Configuration Requirements

### Required Secrets (Keyring)

- **GitLab Token**: Personal access token with `api`, `read_api`, `read_repository` scopes
  - Get from: https://gitlab.com/-/user_settings/personal_access_tokens
  - Store: `keyring.set_password('gitlab', 'token', 'YOUR_TOKEN')`

### Optional Secrets

- **Slack Token**: Bot token for notification system
  - Store: `keyring.set_password('slack', 'token', 'YOUR_TOKEN')`

### Configuration File

Edit `resources/config.json` to add your repositories:

```json
{
  "repositories": [
    {
      "name": "repo-name",
      "url": "git@gitlab.com:owner/repository.git"
    }
  ]
}
```

## Usage

### Starting the Monitor

```bash
./run monitor
```

The application will:
1. Load configuration from `resources/config.json`
2. Authenticate with GitLab using your token
3. Fetch open merge requests from all configured repositories
4. Display MRs with real-time status updates every 30 seconds
5. Send Slack notifications for MRs ready for review (once per day)

### Interactions

- **Left-click MR**: Opens in browser
- **Right-click MR**: Context menu (Fix MR, Open, Copy URL)
- **Right-click Branch**: Context menu (Copy name, Checkout)
- **Click Status Pill**: Opens related URL (e.g., pipeline page)

## Directory Structure

```
mr-status-monitor/
├── src/                          # All source code
│   ├── gitlab_api.py            # GitLab API functions
│   ├── mr_model.py              # Qt model for display
│   ├── mr_notifier.py           # Slack notification system
│   ├── mr_status_controller.py # Main controller
│   └── main.py                  # Application entry point
├── resources/                    # Static resources
│   ├── config.json              # Repository configuration
│   └── mr-status-bar.qml        # UI definition
├── output/                       # Runtime outputs (gitignored)
│   ├── mr_status_monitor.log   # Application log
│   └── mr_status/               # Notification state
├── local/                        # Large files (gitignored)
├── run                          # Command-line interface
├── requirements.txt             # Python dependencies
├── README.md                    # User documentation
└── .gitignore                   # Git ignore rules
```

## Known Limitations

1. **Local Paths**: Branch checkout requires hardcoded paths in `mr_status_controller.py`
2. **Channel Hardcoded**: Slack notifications go to `#squad-lending-pr` (configurable in code)
3. **Coverage Reviewers**: Usernames hardcoded as `AdityaM3` and `Tejas52`
4. **No Tests Yet**: Test suite not implemented (would be added before production release)

## Future Enhancements

- [ ] Move local paths to configuration file
- [ ] Make Slack channel configurable
- [ ] Add test suite with pytest
- [ ] Add CI/CD pipeline configuration
- [ ] Create installer script for easier deployment
- [ ] Add system tray icon for background running
- [ ] Support filtering and sorting MRs
- [ ] Add keyboard shortcuts for common actions

## Dependencies

See `requirements.txt` for exact versions:

- Python 3.10+
- requests 2.32.4
- keyring 25.6.0
- colorama 0.4.6
- python-gitlab 6.2.0
- PySide6 6.9.2

## Support

For issues or questions:
1. Check logs in `output/` directory
2. Run `./run install` to verify setup
3. See "Troubleshooting" section in README.md

## License

Internal tool - not for public distribution.

## Credits

Original prototype: ~/icloud/bin/mr-status-bar
Refactored version: Following standards from ~/icloud/agents.md
Release: 2025-10-23
