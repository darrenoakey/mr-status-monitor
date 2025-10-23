#!/usr/bin/env python3

import os
import json
import logging
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import requests
import keyring
from colorama import Fore, Style

logger = logging.getLogger(__name__)

# ##################################################################
# merge request notifier
# sends slack notifications for merge requests requiring review
# tracks notification state to prevent duplicates per day
class MRNotifier:
    def __init__(self, state_dir: Optional[Path] = None) -> None:
        if state_dir is None:
            script_dir = Path(__file__).parent.resolve()
            self.state_dir = script_dir.parent / "output" / "mr_status"
        else:
            self.state_dir = Path(state_dir)

        logger.info(f"mr notifier state dir={self.state_dir}")

        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"state directory verified path={self.state_dir}")
        except Exception as err:
            logger.error(f"error creating state directory path={self.state_dir} err={err}")

        self.person_cache_file = self.state_dir / "person_translations.json"
        self.person_cache = self._load_person_cache()

        self.slack_token = keyring.get_password("slack", "token")
        self.gitlab_token = keyring.get_password("gitlab", "token")

        if not self.slack_token:
            logger.error("no slack token found in keyring")

        if not self.gitlab_token:
            logger.error("no gitlab token found in keyring")

    # ##################################################################
    # load person cache
    # retrieves cached gitlab name to slack user id mappings from disk
    def _load_person_cache(self) -> Dict[str, Optional[str]]:
        try:
            if self.person_cache_file.exists():
                with open(self.person_cache_file, 'r') as f:
                    return json.load(f)
        except Exception as err:
            logger.warning(f"could not load person cache err={err}")
        return {}

    # ##################################################################
    # save person cache
    # persists gitlab name to slack user id mappings to avoid repeated lookups
    def _save_person_cache(self) -> None:
        try:
            with open(self.person_cache_file, 'w') as f:
                json.dump(self.person_cache, f, indent=2)
        except Exception as err:
            logger.error(f"error saving person cache err={err}")

    # ##################################################################
    # get notification date file
    # returns path to file tracking last notification date for specific mr
    def _get_notification_date_file(self, mr_key: str) -> Path:
        safe_mr_key = mr_key.replace('/', '_').replace('!', '_')
        return self.state_dir / f"notified_{safe_mr_key}.date"

    # ##################################################################
    # should notify
    # checks if notification should be sent today based on last notification date
    def _should_notify(self, mr_key: str) -> bool:
        date_file = self._get_notification_date_file(mr_key)

        if not date_file.exists():
            return True

        try:
            with open(date_file, 'r') as f:
                last_notified = f.read().strip()

            today = date.today().isoformat()
            return last_notified != today

        except Exception as err:
            logger.warning(f"could not read notification date mr_key={mr_key} err={err}")
            return True

    # ##################################################################
    # mark notified
    # records that notification was sent today for this merge request
    def _mark_notified(self, mr_key: str) -> None:
        date_file = self._get_notification_date_file(mr_key)
        today = date.today().isoformat()

        logger.info(f"marking notified mr_key={mr_key} date={today} file={date_file}")

        try:
            with open(date_file, 'w') as f:
                f.write(today)
            logger.info(f"notification marker created successfully")

            if date_file.exists():
                with open(date_file, 'r') as f:
                    content = f.read().strip()
                    logger.info(f"verified file content={content}")
            else:
                logger.error("file does not exist after creation")

        except Exception as err:
            logger.error(f"error marking notification sent mr_key={mr_key} err={err}")

    # ##################################################################
    # get slack user id
    # translates gitlab person name to slack user id using cache
    def _get_slack_user_id(self, person_name: str) -> Optional[str]:
        if person_name in self.person_cache:
            return self.person_cache[person_name]

        if not self.slack_token:
            return None

        try:
            headers = {'Authorization': f'Bearer {self.slack_token}'}
            response = requests.get('https://slack.com/api/users.list', headers=headers)

            if response.status_code != 200:
                logger.error(f"failed to get slack users status={response.status_code}")
                return None

            data = response.json()
            if not data.get('ok'):
                logger.error(f"slack api error={data.get('error')}")
                return None

            for user in data['members']:
                if user.get('deleted', False):
                    continue

                names_to_check = [
                    user.get('real_name', ''),
                    user.get('display_name', ''),
                    user.get('name', ''),
                    user.get('profile', {}).get('display_name', ''),
                    user.get('profile', {}).get('real_name', '')
                ]

                for name in names_to_check:
                    if name and person_name.lower() in name.lower():
                        user_id = user['id']
                        self.person_cache[person_name] = user_id
                        self._save_person_cache()
                        return user_id

            self.person_cache[person_name] = None
            self._save_person_cache()
            logger.warning(f"could not find slack user person_name={person_name}")
            return None

        except Exception as err:
            logger.error(f"error looking up slack user person_name={person_name} err={err}")
            return None

    # ##################################################################
    # check and add coverage reviewers
    # adds coverage team members as reviewers when mr is otherwise approved
    def _check_and_add_coverage_reviewers(self, project_id: str, mr_iid: int, mr_data: Dict[str, Any]) -> bool:
        from .gitlab_api import add_reviewers_to_mr

        try:
            if 'approval_status' not in mr_data or 'pipeline_status' not in mr_data:
                return False

            approval_status = mr_data['approval_status']
            pipeline_status = mr_data['pipeline_status']

            if (pipeline_status == 'success' and
                approval_status.get('approved_except_coverage', False) and
                approval_status.get('needs_coverage_check', False)):

                logger.info("mr approved with passing pipeline, adding coverage reviewers")

                coverage_reviewers = ['AdityaM3', 'Tejas52']
                if add_reviewers_to_mr(project_id, mr_iid, coverage_reviewers, self.gitlab_token):
                    logger.info("added coverage reviewers to mr")
                    return True

            return False

        except Exception as err:
            logger.error(f"error checking or adding coverage reviewers err={err}")
            return False

    # ##################################################################
    # send slack message
    # posts notification message to squad lending pr channel
    def _send_slack_message(self, message: str) -> bool:
        if not self.slack_token:
            return False

        try:
            headers = {
                'Authorization': f'Bearer {self.slack_token}',
                'Content-Type': 'application/json'
            }

            channel_name = "#squad-lending-pr"

            payload = {
                'channel': channel_name,
                'text': message
            }

            response = requests.post('https://slack.com/api/chat.postMessage',
                                   headers=headers,
                                   json=payload)

            if response.status_code != 200:
                logger.error(f"failed to send slack message status={response.status_code}")
                return False

            data = response.json()
            if data.get('ok'):
                return True
            else:
                logger.error(f"failed to send slack message error={data.get('error')}")
                return False

        except Exception as err:
            logger.error(f"error sending slack message err={err}")
            return False

    # ##################################################################
    # format notification message
    # creates concise single line slack message mentioning pending reviewers
    def _format_notification_message(self, mr_data: Dict[str, Any], assignees: List[str]) -> str:
        mr = mr_data['mr']
        mr_url = mr['web_url']

        assignee_mentions = []
        for assignee in assignees:
            slack_user_id = self._get_slack_user_id(assignee)
            if slack_user_id:
                assignee_mentions.append(f"<@{slack_user_id}>")
            else:
                assignee_mentions.append(assignee)

        if assignee_mentions:
            mentions = ", ".join(assignee_mentions)
        else:
            mentions = "reviewers"

        message = f"Please review {mentions}: {mr_url} (ty)"

        return message

    # ##################################################################
    # process merge request for notification
    # checks if mr needs notification and sends it with pending reviewer list
    def process_mr_for_notification(self, mr_data: Dict[str, Any]) -> bool:
        from .gitlab_api import get_mr_assignees_and_approvals

        logger.info(f"processing mr for notification keys={list(mr_data.keys())}")

        try:
            repo_name = mr_data.get('repo_name', 'unknown')
            mr = mr_data['mr']
            mr_iid = mr['iid']

            mr_key = f"{repo_name}-{mr_iid}"

            logger.info(f"processing mr repo={repo_name} iid={mr_iid} key={mr_key}")

            should_notify = self._should_notify(mr_key)
            logger.info(f"should notify={should_notify}")

            if not should_notify:
                logger.info("already notified today")
                return False

            logger.info("new mr or not notified today")

            if 'project_id' not in mr_data:
                logger.error(f"no project id in mr data available_keys={list(mr_data.keys())}")
                return False

            project_id = mr_data['project_id']
            logger.info(f"using project id={project_id}")

            if 'approval_status' in mr_data:
                approval_status = mr_data['approval_status']
                if approval_status.get('approved_by_all', False):
                    logger.info("mr has received all required approvals")
                    self._mark_notified(mr_key)
                    return False

            logger.info("checking if coverage reviewers needed")
            self._check_and_add_coverage_reviewers(project_id, mr_iid, mr_data)

            logger.info("fetching assignees and approvals from gitlab")
            assignees, approved_users = get_mr_assignees_and_approvals(project_id, mr_iid, self.gitlab_token)
            logger.info(f"found assignees={assignees} approved={approved_users}")

            pending_reviewers = [assignee for assignee in assignees if assignee not in approved_users]
            logger.info(f"pending reviewers={pending_reviewers}")

            if not assignees:
                logger.warning("no assignees found")
                self._mark_notified(mr_key)
                return False

            if not pending_reviewers:
                logger.info("all assignees have already approved")
                self._mark_notified(mr_key)
                return False

            logger.info(f"processing pending reviewers count={len(pending_reviewers)}")

            message = self._format_notification_message(mr_data, pending_reviewers)
            logger.info(f"formatted message={message}")

            if self._send_slack_message(message):
                logger.info("notification sent successfully")
                self._mark_notified(mr_key)
                return True
            else:
                logger.error("failed to send notification")
                return False

        except Exception as err:
            logger.error(f"error in process mr for notification err={err}")
            return False

    # ##################################################################
    # process merge request list
    # sends notifications for all merge requests needing review
    def process_mr_list(self, mr_list: List[Dict[str, Any]]) -> int:
        if not mr_list:
            logger.info("no mrs to process")
            return 0

        logger.info(f"processing mrs count={len(mr_list)}")

        notifications_sent = 0
        for mr_data in mr_list:
            if self.process_mr_for_notification(mr_data):
                notifications_sent += 1

        if notifications_sent > 0:
            logger.info(f"sent notifications count={notifications_sent}")
        else:
            logger.info("no notifications sent")

        return notifications_sent
