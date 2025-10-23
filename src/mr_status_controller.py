#!/usr/bin/env python3

import os
import json
import time
import re
import queue
import multiprocessing
import traceback
from urllib.parse import quote
import webbrowser
import subprocess
import logging

import requests
import keyring

from PySide6.QtCore import QObject, Signal, Slot, QTimer, Property
from PySide6.QtGui import QClipboard
from PySide6.QtWidgets import QApplication

from src.mr_model import MRModel
from src.mr_notifier import MRNotifier
from src.gitlab_api import (
    make_gitlab_request,
    get_merge_requests,
    get_pipeline_status,
    get_approval_status,
    get_merge_status,
    get_unresolved_threads_count
)

# ##################################################################
# mr status controller
# coordinates fetching merge request data from gitlab, updating
# the ui model, and managing notifications through slack
class MRStatusController(QObject):
    statusChanged = Signal(str)
    loadingChanged = Signal(bool)

    def __init__(self, logger):
        super().__init__()
        self.logger = logger
        self.repositories = []
        self.token = None
        self.user_id = None
        self.mr_model = MRModel()
        self._loading = True
        self._repos_loaded = set()
        self.notifier = None
        self.temp_status = None

        self._initialize_notifier()
        self._initialize_multiprocessing()
        self._initialize_timers()

        self.loadingChanged.emit(True)
        self.statusChanged.emit("Initializing...")

    # ##################################################################
    # initialize notifier
    # sets up the mr notification system for sending slack messages
    def _initialize_notifier(self):
        try:
            self.notifier = MRNotifier(self.logger)
            self.logger.info("MR notification system initialized")
        except Exception as e:
            self.logger.warning(f"Could not initialize MR notifier: {e}")

    # ##################################################################
    # initialize multiprocessing
    # creates queues and prepares worker process for background fetching
    def _initialize_multiprocessing(self):
        self.repo_queue = multiprocessing.Queue()
        self.result_queue = multiprocessing.Queue()
        self.worker_process = None

    # ##################################################################
    # initialize timers
    # sets up periodic refresh, result checking, and status clearing
    def _initialize_timers(self):
        self.result_timer = QTimer()
        self.result_timer.timeout.connect(self.check_results)
        self.result_timer.start(100)

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.schedule_refresh)
        self.refresh_timer.start(30000)

        self.status_clear_timer = QTimer()
        self.status_clear_timer.setSingleShot(True)
        self.status_clear_timer.timeout.connect(self.clear_temporary_status)

    @Property(bool, notify=loadingChanged)
    def loading(self):
        return self._loading

    @Property(QObject, constant=True)
    def model(self):
        return self.mr_model

    # ##################################################################
    # set temporary status
    # displays a status message that automatically clears after duration
    def set_temporary_status(self, message, duration_ms=5000):
        self.temp_status = message
        self.statusChanged.emit(message)
        self.status_clear_timer.start(duration_ms)

    # ##################################################################
    # clear temporary status
    # restores the normal status display after temporary message expires
    def clear_temporary_status(self):
        self.temp_status = None
        total_mrs = self.mr_model.rowCount()
        if total_mrs == 0:
            self.statusChanged.emit("No open merge requests")
        else:
            self.statusChanged.emit(f"Last updated: {time.strftime('%H:%M:%S')} ({total_mrs} MRs)")

    # ##################################################################
    # load config
    # reads repository configuration from json file
    def load_config(self, config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                self.repositories = config.get('repositories', [])

                for repo in self.repositories:
                    if repo['name'] == 'bosphorus':
                        repo['local_path'] = os.path.expanduser('~/work/bosphorus-middleware')
                    elif repo['name'] == 'webapp':
                        repo['local_path'] = os.path.expanduser('~/work/webapp')
        except Exception as e:
            self.logger.error(f"Error loading config: {e}")
            self.repositories = []

    # ##################################################################
    # parse gitlab url
    # extracts owner and repository name from gitlab remote url
    def parse_gitlab_url(self, remote_url):
        if not re.search(r'(git@gitlab\.com:|https://gitlab\.com/)', remote_url):
            return None, None

        ssh_match = re.search(r'git@gitlab\.com:([^/]+)/([^\.]+)(\.git)?$', remote_url)
        https_match = re.search(r'https://gitlab\.com/([^/]+)/([^\.]+)(\.git)?', remote_url)

        if ssh_match:
            return ssh_match.group(1), ssh_match.group(2)
        elif https_match:
            return https_match.group(1), https_match.group(2)
        else:
            return None, None

    # ##################################################################
    # get gitlab token
    # retrieves gitlab api token from system keyring
    def get_gitlab_token(self):
        try:
            return keyring.get_password("gitlab", "token")
        except Exception:
            return None

    # ##################################################################
    # get current user
    # fetches authenticated user information from gitlab api
    def get_current_user(self, token):
        headers = {'PRIVATE-TOKEN': token}
        return make_gitlab_request('https://gitlab.com/api/v4/user', headers)

    # ##################################################################
    # get project id
    # looks up gitlab project id by owner and repository name
    def get_project_id(self, owner, repo, token):
        headers = {'PRIVATE-TOKEN': token}
        project_path = quote(f"{owner}/{repo}", safe='')
        project_data = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_path}', headers)

        if project_data is not None:
            return project_data['id']
        return None

    # ##################################################################
    # initialize data
    # loads configuration, authenticates, and starts background fetching
    def initialize_data(self):
        self.statusChanged.emit("Loading configuration...")

        if not self.repositories:
            self.statusChanged.emit("No repositories configured")
            self._loading = False
            self.loadingChanged.emit(False)
            return

        self.statusChanged.emit("Getting GitLab token...")
        self.token = self.get_gitlab_token()
        if not self.token:
            self.statusChanged.emit("No GitLab token found in keyring")
            self._loading = False
            self.loadingChanged.emit(False)
            return

        self.statusChanged.emit("Authenticating with GitLab...")
        user = self.get_current_user(self.token)
        if not user:
            self.statusChanged.emit("Could not authenticate with GitLab")
            self._loading = False
            self.loadingChanged.emit(False)
            return

        self.user_id = user['id']

        self.statusChanged.emit("Loading repository information...")
        for repo_config in self.repositories:
            owner, repo = self.parse_gitlab_url(repo_config['url'])
            if owner and repo:
                project_id = self.get_project_id(owner, repo, self.token)
                if project_id:
                    repo_config['owner'] = owner
                    repo_config['repo'] = repo
                    repo_config['project_id'] = project_id

        self.statusChanged.emit("Fetching merge requests...")
        self.start_background_fetch()

    # ##################################################################
    # start background fetch
    # launches worker process for concurrent mr data retrieval
    def start_background_fetch(self):
        self.worker_process = multiprocessing.Process(
            target=fetch_mr_data_worker,
            args=(self.repo_queue, self.result_queue, self.token, self.user_id)
        )
        self.worker_process.start()
        self.queue_refresh()

    # ##################################################################
    # queue refresh
    # adds all configured repositories to the fetch queue
    def queue_refresh(self):
        for repo_config in self.repositories:
            if 'project_id' in repo_config:
                self.repo_queue.put(repo_config)

    # ##################################################################
    # schedule refresh
    # triggers periodic background refresh of all repositories
    def schedule_refresh(self):
        self.queue_refresh()

    # ##################################################################
    # check results
    # processes completed mr data from the background worker
    def check_results(self):
        try:
            while True:
                try:
                    message_type, data1, data2 = self.result_queue.get_nowait()

                    if message_type == 'repo_complete':
                        repo_name, repo_mrs = data1, data2
                        self.update_repo_data(repo_name, repo_mrs)
                    elif message_type == 'error':
                        self.logger.error(f"Worker error: {data1}")

                except queue.Empty:
                    break
        except:
            pass

    # ##################################################################
    # update repo data
    # updates ui model and checks for notification triggers
    def update_repo_data(self, repo_name, repo_mrs):
        self._repos_loaded.add(repo_name)
        self.check_for_notifications(repo_name, repo_mrs)

        new_items = []
        for mr_data in repo_mrs:
            mr = mr_data['mr']
            pipeline_status = mr_data['pipeline_status']
            pipeline_url = mr_data['pipeline_url']
            approval_status = mr_data['approval_status']
            merge_status = mr_data['merge_status']
            unresolved_threads = mr_data['unresolved_threads']

            mr_number = f"!{mr['iid']}"
            title = mr['title'][:50] + '...' if len(mr['title']) > 50 else mr['title']

            status_pills = self._build_status_pills(
                pipeline_status, pipeline_url, merge_status,
                unresolved_threads, approval_status
            )

            new_items.append({
                'repo': repo_name,
                'mr': mr_number,
                'title': title,
                'status_pills': status_pills,
                'mr_url': mr['web_url'],
                'pipeline_url': pipeline_url,
                'branch': mr['source_branch']
            })

        self.mr_model.update_repo_data(repo_name, new_items)

        expected_repos = {repo['name'] for repo in self.repositories if 'project_id' in repo}
        if self._repos_loaded >= expected_repos and self._loading:
            self._loading = False
            self.loadingChanged.emit(False)

        if not self.temp_status:
            total_mrs = self.mr_model.rowCount()
            if total_mrs == 0:
                self.statusChanged.emit("No open merge requests")
            else:
                self.statusChanged.emit(f"Last updated: {time.strftime('%H:%M:%S')} ({total_mrs} MRs)")

    # ##################################################################
    # build status pills
    # creates colored status indicators for pipeline, conflicts, threads, and approvals
    def _build_status_pills(self, pipeline_status, pipeline_url, merge_status, unresolved_threads, approval_status):
        status_pills = []

        if pipeline_status == 'failed':
            status_pills.append({'text': 'Pipeline', 'color': '#F44336', 'url': pipeline_url})
        elif pipeline_status in ['running', 'pending', 'created']:
            status_pills.append({'text': 'Pipeline', 'color': '#2196F3', 'url': pipeline_url})
        elif pipeline_status in ['canceled', 'cancelled']:
            status_pills.append({'text': 'Cancelled', 'color': '#FF9800', 'url': pipeline_url})
        elif pipeline_status == 'skipped':
            status_pills.append({'text': 'Skipped', 'color': '#9E9E9E', 'url': pipeline_url})
        elif pipeline_status is None:
            status_pills.append({'text': 'No Pipeline', 'color': '#795548', 'url': ''})

        if merge_status == 'CONFLICT':
            status_pills.append({'text': 'Conflict', 'color': '#FF9800', 'url': ''})

        if unresolved_threads > 0:
            status_pills.append({
                'text': f'{unresolved_threads} Thread{"s" if unresolved_threads > 1 else ""}',
                'color': '#9C27B0',
                'url': ''
            })

        if approval_status['approved_by_all']:
            status_pills.append({'text': 'Approved', 'color': '#4CAF50', 'url': ''})
        elif approval_status['approved_except_coverage']:
            status_pills.append({'text': 'Approved', 'color': '#4CAF50', 'url': ''})
            if approval_status['needs_coverage_check']:
                status_pills.append({'text': 'Coverage', 'color': '#00BCD4', 'url': ''})
        elif approval_status['needs_coverage_check'] and not approval_status['approved_except_coverage']:
            status_pills.append({'text': 'Coverage', 'color': '#00BCD4', 'url': ''})

        return status_pills

    # ##################################################################
    # check for notifications
    # determines if slack notifications should be sent for passing mrs
    def check_for_notifications(self, repo_name, repo_mrs):
        self.logger.info(f"NOTIFICATION CHECK: {repo_name} with {len(repo_mrs)} MRs")

        if not self.notifier:
            self.logger.info("No notifier available - skipping notifications")
            return

        try:
            project_id = None
            for repo_config in self.repositories:
                if repo_config.get('name') == repo_name:
                    project_id = repo_config.get('project_id')
                    break

            if not project_id:
                self.logger.warning(f"No project_id found for {repo_name} - skipping notifications")
                return

            for mr_data in repo_mrs:
                pipeline_status = mr_data.get('pipeline_status')
                merge_status = mr_data.get('merge_status')

                if pipeline_status != 'success':
                    continue

                if merge_status == 'CONFLICT':
                    continue

                notification_data = mr_data.copy()
                notification_data['project_id'] = project_id

                self.notifier.process_mr_for_notification(notification_data)

        except Exception as e:
            self.logger.error(f"ERROR checking notifications for {repo_name}: {e}")
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    @Slot(str)
    def openUrl(self, url):
        if url:
            webbrowser.open(url)

    @Slot(str)
    def launchFixMR(self, mr_url):
        if not mr_url:
            return

        import platform
        import shutil

        fix_mr_command = f"fix-mr {mr_url}"

        try:
            system = platform.system()

            if system == "Darwin":
                apple_script = f'''
                tell application "Terminal"
                    activate
                    do script "{fix_mr_command}"
                end tell
                '''
                subprocess.run(["osascript", "-e", apple_script])
                self.logger.info(f"Launched fix-mr in Terminal for: {mr_url}")

            elif system == "Linux":
                terminals = [
                    ["gnome-terminal", "--", "bash", "-c", f"{fix_mr_command}; read -p 'Press enter to close'"],
                    ["konsole", "-e", "bash", "-c", f"{fix_mr_command}; read -p 'Press enter to close'"],
                    ["xterm", "-e", "bash", "-c", f"{fix_mr_command}; read -p 'Press enter to close'"],
                ]

                launched = False
                for terminal_cmd in terminals:
                    if shutil.which(terminal_cmd[0]):
                        subprocess.Popen(terminal_cmd)
                        self.logger.info(f"Launched fix-mr in {terminal_cmd[0]} for: {mr_url}")
                        launched = True
                        break

                if not launched:
                    self.logger.error("Could not find a suitable terminal emulator on Linux")

            elif system == "Windows":
                if shutil.which("wt"):
                    subprocess.Popen(["wt", "cmd", "/k", fix_mr_command])
                else:
                    subprocess.Popen(["cmd", "/c", "start", "cmd", "/k", fix_mr_command])
                self.logger.info(f"Launched fix-mr in Windows terminal for: {mr_url}")

        except Exception as e:
            self.logger.error(f"Error launching fix-mr: {e}")

    @Slot(str)
    def copyToClipboard(self, text):
        if not text:
            return

        try:
            app = QApplication.instance()
            if app:
                clipboard = app.clipboard()
                clipboard.setText(text)
                if text.startswith('http'):
                    self.statusChanged.emit("URL copied to clipboard")
                else:
                    self.statusChanged.emit(f"'{text}' copied to clipboard")
                self.logger.info(f"Copied to clipboard: {text}")

        except Exception as e:
            self.logger.error(f"Error copying to clipboard: {e}")

    # ##################################################################
    # do checkout branch
    # performs git checkout operation in a background thread
    def _do_checkout_branch(self, repo_name, branch_name):
        try:
            repo_config = None
            for repo in self.repositories:
                if repo['name'] == repo_name:
                    repo_config = repo
                    break

            if not repo_config or 'local_path' not in repo_config:
                self.set_temporary_status(f"No local path configured for {repo_name}")
                return

            repo_path = repo_config['local_path']

            if not os.path.exists(repo_path):
                self.set_temporary_status(f"{repo_name} path does not exist: {repo_path}")
                return

            result = subprocess.run(
                ['git', 'status', '--porcelain'],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or "git status failed"
                self.set_temporary_status(f"Failed to checkout {branch_name} in {repo_name} because {error_msg}")
                return

            if result.stdout.strip():
                subprocess.run(['git', 'checkout', '--', 'package.json'], cwd=repo_path, capture_output=True, timeout=5)
                subprocess.run(['git', 'checkout', '--', 'package-lock.json'], cwd=repo_path, capture_output=True, timeout=5)

                result = subprocess.run(['git', 'status', '--porcelain'], cwd=repo_path, capture_output=True, text=True, timeout=5)

                if result.returncode != 0:
                    error_msg = result.stderr.strip() or "git status failed"
                    self.set_temporary_status(f"Failed to checkout {branch_name} in {repo_name} because {error_msg}")
                    return

            if result.stdout.strip():
                self.set_temporary_status(f"Can't checkout because {repo_name} isn't clean")
                return

            checkout_result = subprocess.run(
                ['git', 'checkout', branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if checkout_result.returncode != 0:
                error_msg = checkout_result.stderr.strip() or "checkout failed"
                self.set_temporary_status(f"Failed to checkout {branch_name} in {repo_name} because {error_msg}")
                return

            self.set_temporary_status(f"{repo_name} is now at {branch_name}")
            self.logger.info(f"Successfully checked out {branch_name} in {repo_name}")

        except subprocess.TimeoutExpired:
            self.set_temporary_status(f"Failed to checkout {branch_name} in {repo_name} because timeout")
        except Exception as e:
            self.set_temporary_status(f"Failed to checkout {branch_name} in {repo_name} because {str(e)}")
            self.logger.error(f"Error during checkout: {e}")

    @Slot(str, str)
    def checkoutBranch(self, repo_name, branch_name):
        if not repo_name or not branch_name:
            return

        self.logger.info(f"Checkout requested: {repo_name} -> {branch_name}")
        self.statusChanged.emit(f"Checking out {branch_name} in {repo_name}...")
        QTimer.singleShot(100, lambda: self._do_checkout_branch(repo_name, branch_name))

    # ##################################################################
    # cleanup
    # terminates background worker process and releases resources
    def cleanup(self):
        if self.worker_process and self.worker_process.is_alive():
            self.repo_queue.put(None)
            self.worker_process.join(timeout=1)
            if self.worker_process.is_alive():
                self.worker_process.terminate()


# ##################################################################
# fetch mr data worker
# background process that retrieves mr information from gitlab api
def fetch_mr_data_worker(repo_queue, result_queue, token, user_id):
    while True:
        try:
            repo_config = repo_queue.get(timeout=1)
            if repo_config is None:
                break

            mrs = get_merge_requests(repo_config['project_id'], user_id, token)

            repo_mrs = []
            for mr in mrs:
                pipeline_status, pipeline_url, debug_info = get_pipeline_status(
                    repo_config['project_id'],
                    mr['sha'],
                    token,
                    mr['iid']
                )

                approval_status = get_approval_status(
                    repo_config['project_id'],
                    mr['iid'],
                    token
                )

                merge_status = get_merge_status(
                    repo_config['project_id'],
                    mr['iid'],
                    token
                )

                unresolved_threads = get_unresolved_threads_count(
                    repo_config['project_id'],
                    mr['iid'],
                    token
                )

                repo_mrs.append({
                    'repo_name': repo_config['name'],
                    'mr': mr,
                    'pipeline_status': pipeline_status,
                    'pipeline_url': pipeline_url,
                    'approval_status': approval_status,
                    'merge_status': merge_status,
                    'unresolved_threads': unresolved_threads,
                    'debug_info': debug_info
                })

            result_queue.put(('repo_complete', repo_config['name'], repo_mrs))

        except queue.Empty:
            continue
        except Exception as e:
            result_queue.put(('error', str(e), None))
