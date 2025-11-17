from jira import JIRA
import pandas as pd
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Iterable, List, Optional, Set
import time
from dotenv import load_dotenv
import os
load_dotenv()
from datetime import datetime


# -----------------------------
# Configuration (edit as needed)
# -----------------------------
JIRA_SERVER = "https://ontrack-internal.amd.com/" 


class TicketFetch:
    """
    Faster implementation of your original TicketFetch:
    - Batches issue fetches via JQL `key in (...)`
    - Minimizes fields for faster payloads
    - Optional parallelization for batch queries
    - Robust error handling and backoff
    """

    # --- Tunables ---
    MAX_RESULTS = 1000                   # upper bound for initial feature fetch
    CHUNK_SIZE = 100                     # keys per JQL chunk (keep below URL length limits)
    MAX_WORKERS = 6                      # adjust based on your Jira rate limits
    BACKOFF_BASE_SEC = 1.5               # exponential backoff base
    BACKOFF_MAX_RETRIES = 4              # retries for transient failures

    # --- Fields we actually need ---
    FIELDS_FEATURE = "key,status,summary,description,issuelinks"
    FIELDS_QA = (
        "key,status,summary,assignee,labels,issuelinks,issuetype,customfield_14308"
    )

    def __init__(self, auth_key: str = os.environ.get("Access_Token"), rocm_version: str = "7.2", unique_key: str = "4633961",
                 max_workers: Optional[int] = None, verbose: bool = True , is_json: bool = False):
        self.rocm = rocm_version
        self.unique_key = unique_key
        self.verbose = verbose
        self.is_json = is_json
        if max_workers:
            self.MAX_WORKERS = max_workers

        self.options = {'server': JIRA_SERVER}
        self.auth = JIRA(self.options, token_auth=auth_key)

        # Keep your original JQL semantics
        self.jql_query = (
            f'"Target SW Release" in ("{self.rocm} [{unique_key}]") '
            f'AND Project in ("Software Development") AND type = Feature'
        )

        # Precompile regex for performance
        self._qa_committed_pattern = re.compile(r'#teams_committed.*?QA', re.IGNORECASE)
        self._auto_pattern = re.compile(r'auto', re.IGNORECASE)
        self._tms_pattern = re.compile(r'tms', re.IGNORECASE)

    # ------------- Helpers -------------
    @staticmethod
    def _chunked(iterable: Iterable[str], size: int) -> Iterable[List[str]]:
        chunk = []
        for item in iterable:
            chunk.append(item)
            if len(chunk) >= size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    def _search_issues_with_backoff(self, jql: str, fields: str, max_results: int = 1000):
        """
        Wrapper to call JIRA.search_issues with retries/backoff for transient failures (e.g., 429, 5xx).
        """
        delay = self.BACKOFF_BASE_SEC
        for attempt in range(self.BACKOFF_MAX_RETRIES + 1):
            try:
                return self.auth.search_issues(
                    jql,
                    maxResults=max_results,
                    validate_query=False,
                    fields=fields
                )
            except Exception as e:
                # Retry on transient errors; otherwise re-raise
                if attempt >= self.BACKOFF_MAX_RETRIES:
                    raise
                if self.verbose:
                    print(f"[warn] search_issues failed (attempt {attempt+1}/{self.BACKOFF_MAX_RETRIES}) "
                          f"-> {e}. Backing off {delay:.1f}s")
                time.sleep(delay)
                delay *= 2

    def _bulk_fetch_issues_by_keys(self, keys: Set[str], fields: str) -> Dict[str, object]:
        """
        Batch-fetch issues by keys using JQL `key in (...)`, chunked and (optionally) parallelized.
        Returns a dict: key -> Issue object
        """
        keys = [k for k in set(keys) if k]  # de-dup and drop falsy
        if not keys:
            return {}

        key_to_issue: Dict[str, object] = {}

        def fetch_chunk(chunk_keys: List[str]) -> List[object]:
            jql = f"key in ({','.join(chunk_keys)})"
            return self._search_issues_with_backoff(jql, fields=fields, max_results=len(chunk_keys))

        chunks = list(self._chunked(keys, self.CHUNK_SIZE))
        if self.verbose:
            print(f"[info] Bulk fetching {len(keys)} issues in {len(chunks)} chunk(s)")

        # Parallelize chunk fetches to improve wall-clock time
        if self.MAX_WORKERS and self.MAX_WORKERS > 1 and len(chunks) > 1:
            with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as exe:
                futures = {exe.submit(fetch_chunk, chunk): chunk for chunk in chunks}
                for fut in as_completed(futures):
                    issues = fut.result()
                    for issue in issues:
                        key_to_issue[issue.key] = issue
        else:
            for chunk in chunks:
                issues = fetch_chunk(chunk)
                for issue in issues:
                    key_to_issue[issue.key] = issue

        return key_to_issue

    def get_task_details(self, feature_task, qa_task=None) -> Dict[str, str]:
        """
        Builds the final dict for a row in the output, handling NAs & optional Auto/TMS discovery.
        """
        row = {
            '_id': feature_task.key+"|"+qa_task.key if qa_task is not None else feature_task.key,
            'Feature_status': getattr(feature_task.fields.status, 'name', 'NA'),
            'Feature_summary': getattr(feature_task.fields, 'summary', 'NA'),
            'QA_task': "NA",
            'QA_status': "NA",
            'QA_assignee': "NA",
            'QA_labels': "NA",
            'Auto_task': "NA",
            'Auto_status': "NA",
            'TMS_task': "NA",
            'TMS_status': "NA",
            "comments": []
        }

        if qa_task is None:
            return row

        # QA fields
        row['QA_task'] = qa_task.key
        row['QA_status'] = getattr(getattr(qa_task.fields, 'status', None), 'name', 'NA')

        assignee = getattr(qa_task.fields, 'assignee', None)
        if assignee:
            # Prefer displayName if available, else use name or accountId
            display = getattr(assignee, 'displayName', None) or getattr(assignee, 'name', None) or getattr(assignee, 'accountId', None)
            row['QA_assignee'] = display or "NA"

        labels = getattr(qa_task.fields, 'labels', None) or []
        row['QA_labels'] = ", ".join(labels) if labels else "NA"

        # Try to find Auto/TMS tasks from QA issue links (without extra network calls)
        issuelinks = getattr(qa_task.fields, 'issuelinks', None) or []
        for link in issuelinks:
            for issue_side in ('inwardIssue', 'outwardIssue'):
                linked = getattr(link, issue_side, None)
                if not linked:
                    continue

                # Only consider Task issuetype
                try:
                    is_task = getattr(getattr(linked, 'fields', None), 'issuetype', None)
                    if not is_task or getattr(is_task, 'name', '') != 'Task':
                        continue
                except Exception:
                    continue

                # We need summary & status for classification
                li_fields = getattr(linked, 'fields', None)
                summary = getattr(li_fields, 'summary', '') if li_fields else ''
                status_name = getattr(getattr(li_fields, 'status', None), 'name', 'NA') if li_fields else 'NA'
                key = getattr(linked, 'key', None)

                if summary and self._auto_pattern.search(summary) and row['Auto_task'] == "NA":
                    row['Auto_task'] = key or "NA"
                    row['Auto_status'] = status_name or "NA"

                if summary and self._tms_pattern.search(summary) and row['TMS_task'] == "NA":
                    row['TMS_task'] = key or "NA"
                    row['TMS_status'] = status_name or "NA"

                # If both found, we can stop scanning
                if row['Auto_task'] != "NA" and row['TMS_task'] != "NA":
                    break

        return row

    def get_qa_committed_tasks(self, feature_tasks: List[object]) -> List[object]:
        """
        Filter feature tasks whose description contains '#teams_committed ... QA' (case-insensitive).
        """
        selected = []
        for t in feature_tasks:
            desc = getattr(t.fields, 'description', '') or ''
            if isinstance(desc, str) and self._qa_committed_pattern.search(desc):
                selected.append(t)
        return selected

    def _collect_candidate_linked_keys(self, feature_task) -> List[str]:
        """
        From a feature task, collect keys of linked issues that are of link type 'Comprised of Task'.
        We will validate issuetype/triage via the bulk-fetched issues.
        """
        keys = []
        links = getattr(feature_task.fields, 'issuelinks', None) or []
        for link in links:
            linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)
            if not linked_issue:
                continue

            # Preserve your original link-type check
            link_type_inward = link.raw.get('type', {}).get('inward')
            if link_type_inward == 'Comprised of Task':
                key = getattr(linked_issue, 'key', None)
                if key:
                    keys.append(key)
        return keys

    def _qa_filter(self, issue_obj) -> bool:
        """
        Keep QA tasks that:
         - are of issuetype 'Task'
         - triage customfield_14308 first value equals '73317'
         - status != 'Rejected'
        """
        try:
            fields = issue_obj.fields
            issuetype_ok = getattr(getattr(fields, 'issuetype', None), 'name', '') == 'Task'
            status_name = getattr(getattr(fields, 'status', None), 'name', '')
            triage = getattr(fields, 'customfield_14308', None)

            triage_ok = False
            if isinstance(triage, list) and len(triage) > 0:
                triage_ok = str(triage[0]) == '73317'
            elif isinstance(triage, str):
                triage_ok = triage == '73317'

            return issuetype_ok and triage_ok and status_name != 'Rejected'
        except Exception:
            return False

    def fetch_tickets(self) -> pd.DataFrame:
        """
        Orchestrates the entire flow, now optimized for speed.
        Returns a pandas DataFrame with the required columns.
        """
        # 1) Fetch candidate feature tasks (minimal fields)
        if self.verbose:
            print("[info] Fetching feature tasks ...")
        feature_tasks = self._search_issues_with_backoff(
            self.jql_query, fields=self.FIELDS_FEATURE, max_results=self.MAX_RESULTS
        )

        # 2) Filter by QA committed marker
        qa_committed_features = self.get_qa_committed_tasks(feature_tasks)
        if self.verbose:
            print(f"[info] QA-committed features: {len(qa_committed_features)} / {len(feature_tasks)}")

        # 3) Collect all linked keys once (potential QA tasks)
        all_linked_keys: Set[str] = set()
        feature_to_linked_keys: Dict[str, List[str]] = {}
        for ft in qa_committed_features:
            keys = self._collect_candidate_linked_keys(ft)
            feature_to_linked_keys[ft.key] = keys
            all_linked_keys.update(keys)

        # 4) Bulk fetch those linked issues (we'll filter to valid QA later)
        if self.verbose:
            print(f"[info] Bulk fetching candidate linked issues: {len(all_linked_keys)}")
        linked_issues_map = self._bulk_fetch_issues_by_keys(all_linked_keys, fields=self.FIELDS_QA)

        # 5) Build result rows
        rows: List[Dict[str, str]] = []

        for idx, feature_task in enumerate(qa_committed_features, start=1):
            keys = feature_to_linked_keys.get(feature_task.key, [])
            qa_added = False

            for k in keys:
                qa_issue = linked_issues_map.get(k)
                if qa_issue and self._qa_filter(qa_issue):
                    rows.append(self.get_task_details(feature_task, qa_issue))
                    qa_added = True

            if not qa_added:
                rows.append(self.get_task_details(feature_task, None))

            if self.verbose:
                print(f"Latest info fetched for {feature_task.key}  ({idx}/{len(qa_committed_features)})")

        df = pd.DataFrame(rows)
        if self.is_json:
            return df.to_json(orient="records")
        return df


# -----------------------------
# Example usage
# -----------------------------
# if __name__ == "__main__":
#     # Fill in your values
#     AUTH_TOKEN = "YOUR_JIRA_TOKEN"
#     ROCM_VERSION = "7.2"
#     UNIQUE_KEY = ""

    
#     start_time = datetime.now()
#     print(f"Start Time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

#     tf = TicketFetch(
#         rocm_version=ROCM_VERSION,
#         max_workers=6,      # tweak per your Jira rate limits
#         verbose=True,
#         is_json=True
#     )

#     df = tf.fetch_tickets()
    
#     end_time = datetime.now()
#     print(f"End Time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")

#     duration = end_time - start_time
#     print(f"Total Duration: {duration}")

#     print("\nFinal DataFrame preview:")
#     print(df)
    # df.to_excel("tickets.xlsx", index=False)