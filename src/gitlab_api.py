#!/usr/bin/env python3

import time
import logging
from typing import Optional, Dict, List, Any
import requests

logger = logging.getLogger(__name__)

# ##################################################################
# gitlab request with retry
# wraps gitlab api calls with exponential backoff for rate limiting
# and transient failures to ensure reliable data retrieval
def make_gitlab_request(url: str, headers: Dict[str, str], params: Optional[Dict[str, Any]] = None,
                        max_retries: int = 3, base_delay: int = 1) -> Optional[Any]:
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                delay = base_delay * (2 ** attempt) + 5
                logger.warning(f"rate limited url={url} retry={attempt+1}/{max_retries} delay={delay}s")
                time.sleep(delay)
            else:
                logger.error(f"request failed url={url} status={response.status_code}")
                return None
        except requests.exceptions.Timeout:
            delay = base_delay * (2 ** attempt)
            logger.warning(f"timeout url={url} retry={attempt+1}/{max_retries} delay={delay}s")
            if attempt < max_retries - 1:
                time.sleep(delay)
        except Exception as err:
            logger.error(f"request error url={url} err={err}")
            if attempt < max_retries - 1:
                time.sleep(base_delay)
    return None

# ##################################################################
# get merge requests
# retrieves all open merge requests for a specific user and project
# from gitlab api with pagination support
def get_merge_requests(project_id: str, user_id: str, token: str) -> List[Dict[str, Any]]:
    headers = {'PRIVATE-TOKEN': token}
    params = {
        'state': 'opened',
        'author_id': user_id,
        'per_page': 50
    }
    result = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests',
                                 headers, params)
    return result if result is not None else []

# ##################################################################
# get pipeline status
# determines the current pipeline state for a merge request by sha
# returns tuple of status, url, and debug information for diagnostics
def get_pipeline_status(project_id: str, mr_sha: str, token: str,
                       mr_iid: Optional[int] = None) -> tuple[Optional[str], Optional[str], Dict[str, Any]]:
    debug_info = {}
    headers = {'PRIVATE-TOKEN': token}

    pipelines_data = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_id}/pipelines',
                                        headers, {'sha': mr_sha})

    if pipelines_data is not None:
        debug_info['pipelines_count'] = len(pipelines_data)

        if pipelines_data:
            latest_pipeline = pipelines_data[0]
            debug_info['latest_pipeline_status'] = latest_pipeline['status']
            debug_info['latest_pipeline_id'] = latest_pipeline['id']
            return latest_pipeline['status'], latest_pipeline['web_url'], debug_info
        else:
            debug_info['pipelines_empty'] = True

    if mr_iid:
        mr_data = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
                                     headers)

        if mr_data is not None:
            debug_info['mr_head_sha'] = mr_data.get('sha')
            debug_info['mr_source_branch'] = mr_data.get('source_branch')

            if 'head_pipeline' in mr_data and mr_data['head_pipeline']:
                pipeline_id = mr_data['head_pipeline']['id']
                pipeline_data = make_gitlab_request(
                    f'https://gitlab.com/api/v4/projects/{project_id}/pipelines/{pipeline_id}',
                    headers)

                if pipeline_data is not None:
                    debug_info['head_pipeline_status'] = pipeline_data['status']
                    return pipeline_data['status'], pipeline_data['web_url'], debug_info

            debug_info['no_head_pipeline'] = True

    debug_info['all_requests_failed'] = True
    return None, None, debug_info

# ##################################################################
# get approval status
# checks approval state including special handling for coverage check
# returns dict with approval flags and coverage requirement status
def get_approval_status(project_id: str, mr_iid: int, token: str) -> Dict[str, bool]:
    headers = {'PRIVATE-TOKEN': token}
    approvals_data = make_gitlab_request(
        f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals',
        headers)

    if approvals_data is not None:
        approval_rules = approvals_data.get('approval_rules_left', [])

        needs_coverage_check = False
        needs_other_approval = False

        for rule in approval_rules:
            rule_name = rule.get('name', '')
            if rule_name == 'Coverage-Check':
                needs_coverage_check = True
            else:
                needs_other_approval = True

        approved_by_all = approvals_data.get('approved', False)
        approved_except_coverage = (not needs_other_approval) and (not approved_by_all or needs_coverage_check)

        return {
            'approved_by_all': approved_by_all,
            'approved_except_coverage': approved_except_coverage,
            'needs_coverage_check': needs_coverage_check
        }

    return {
        'approved_by_all': False,
        'approved_except_coverage': False,
        'needs_coverage_check': False
    }

# ##################################################################
# get merge status
# determines if merge request has conflicts that block merging
# returns conflict indicator or empty string for clean merges
def get_merge_status(project_id: str, mr_iid: int, token: str) -> str:
    headers = {'PRIVATE-TOKEN': token}
    params = {'with_merge_status_recheck': 'true'}
    mr_data = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
                                 headers, params)

    if mr_data is not None:
        merge_status = mr_data.get('merge_status')
        detailed_merge_status = mr_data.get('detailed_merge_status')
        has_conflicts = mr_data.get('has_conflicts', False)

        if (detailed_merge_status == 'conflict' or
            merge_status == 'cannot_be_merged' or
            has_conflicts):
            return 'CONFLICT'
        else:
            return ''

    return ''

# ##################################################################
# get unresolved threads count
# counts discussion threads that remain unresolved on merge request
# used to indicate outstanding review comments requiring attention
def get_unresolved_threads_count(project_id: str, mr_iid: int, token: str) -> int:
    headers = {'PRIVATE-TOKEN': token}
    discussions_data = make_gitlab_request(
        f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/discussions',
        headers)

    if discussions_data is not None:
        unresolved_count = 0
        for discussion in discussions_data:
            if discussion.get('notes') and not discussion.get('notes', [{}])[0].get('resolved', True):
                unresolved_count += 1
        return unresolved_count
    return 0

# ##################################################################
# get current user
# retrieves authenticated gitlab user information
# used to filter merge requests by author
def get_current_user(token: str) -> Optional[Dict[str, Any]]:
    headers = {'PRIVATE-TOKEN': token}
    return make_gitlab_request('https://gitlab.com/api/v4/user', headers)

# ##################################################################
# get project id
# converts project owner and repo name to gitlab project id
# required for all project-specific api calls
def get_project_id(owner: str, repo: str, token: str) -> Optional[int]:
    from urllib.parse import quote
    headers = {'PRIVATE-TOKEN': token}
    project_path = quote(f"{owner}/{repo}", safe='')
    project_data = make_gitlab_request(f'https://gitlab.com/api/v4/projects/{project_path}', headers)

    if project_data is not None:
        return project_data['id']
    return None

# ##################################################################
# get merge request assignees and approvals
# retrieves both assigned reviewers and users who have already approved
# returns tuple of assignee names and approved user names for filtering
def get_mr_assignees_and_approvals(project_id: str, mr_iid: int, token: str) -> tuple[List[str], List[str]]:
    headers = {'PRIVATE-TOKEN': token}

    mr_response = requests.get(
        f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
        headers=headers)

    if mr_response.status_code != 200:
        logger.error(f"failed to get mr data project_id={project_id} mr_iid={mr_iid} status={mr_response.status_code}")
        return [], []

    mr_data = mr_response.json()
    assignees = []

    if 'assignees' in mr_data and mr_data['assignees']:
        for assignee in mr_data['assignees']:
            assignees.append(assignee.get('name', assignee.get('username', 'Unknown')))

    if 'assignee' in mr_data and mr_data['assignee']:
        assignee_name = mr_data['assignee'].get('name', mr_data['assignee'].get('username', 'Unknown'))
        if assignee_name not in assignees:
            assignees.append(assignee_name)

    if 'reviewers' in mr_data and mr_data['reviewers']:
        for reviewer in mr_data['reviewers']:
            reviewer_name = reviewer.get('name', reviewer.get('username', 'Unknown'))
            if reviewer_name not in assignees:
                assignees.append(reviewer_name)

    approvals_response = requests.get(
        f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}/approvals',
        headers=headers)

    approved_users = []
    if approvals_response.status_code == 200:
        approvals_data = approvals_response.json()

        if 'approved_by' in approvals_data and approvals_data['approved_by']:
            for approval in approvals_data['approved_by']:
                user = approval.get('user', {})
                approved_user_name = user.get('name', user.get('username', 'Unknown'))
                approved_users.append(approved_user_name)

        logger.info(f"approved by count={len(approved_users)}")
    else:
        logger.warning(f"could not get approval data status={approvals_response.status_code}")

    return assignees, approved_users

# ##################################################################
# add reviewers to merge request
# adds specified gitlab usernames as reviewers to an mr
# merges with existing reviewers to avoid duplication
def add_reviewers_to_mr(project_id: str, mr_iid: int, usernames: List[str], token: str) -> bool:
    if not token or not usernames:
        return False

    try:
        headers = {'PRIVATE-TOKEN': token}

        mr_response = requests.get(
            f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
            headers=headers)

        if mr_response.status_code != 200:
            logger.error(f"failed to get mr data status={mr_response.status_code}")
            return False

        mr_data = mr_response.json()
        current_reviewer_ids = set()

        if 'reviewers' in mr_data and mr_data['reviewers']:
            for reviewer in mr_data['reviewers']:
                current_reviewer_ids.add(reviewer['id'])

        reviewer_ids_to_add = []
        for username in usernames:
            user_response = requests.get(
                f'https://gitlab.com/api/v4/users',
                headers=headers,
                params={'username': username})

            if user_response.status_code == 200:
                users = user_response.json()
                if users:
                    user_id = users[0]['id']
                    if user_id not in current_reviewer_ids:
                        reviewer_ids_to_add.append(user_id)
                        logger.info(f"found user username={username} id={user_id}")

        if not reviewer_ids_to_add:
            logger.info("all requested reviewers already assigned")
            return True

        all_reviewer_ids = list(current_reviewer_ids) + reviewer_ids_to_add

        update_response = requests.put(
            f'https://gitlab.com/api/v4/projects/{project_id}/merge_requests/{mr_iid}',
            headers=headers,
            json={'reviewer_ids': all_reviewer_ids})

        if update_response.status_code == 200:
            logger.info(f"added reviewers usernames={usernames}")
            return True
        else:
            logger.error(f"failed to add reviewers status={update_response.status_code}")
            return False

    except Exception as err:
        logger.error(f"error adding reviewers err={err}")
        return False
