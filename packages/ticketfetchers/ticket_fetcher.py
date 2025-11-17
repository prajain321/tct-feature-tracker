from jira import JIRA
import pandas as pd
import re
import os
from dotenv import load_dotenv

load_dotenv()

jira_server = 'https://ontrack-internal.amd.com/'

class TicketFetch:
    def __init__(self,auth_key=os.getenv("Access_Token"),rocm_version="7.2", unique_key="4633961"):
        self.rocm = rocm_version
        self.options = {'server': jira_server}
        self.auth = JIRA(self.options, token_auth=auth_key)
        self.jql_query = f'"Target SW Release" in ("{self.rocm} [{unique_key}]") AND Project in ("Software Development") AND type = Feature'

    def get_task_details(self,feature_task, qa_task = None):

        task_related_data = {
                'Feature_task':feature_task.key,
                'Feature_status': feature_task.fields.status.name,
                'Feature_summary': feature_task.fields.summary,
                'QA_task': "NA",
                'QA_status': "NA",
                'QA_assignee': "NA",
                'QA_labels': "NA",
                'Auto_task': "NA",
                'Auto_status': "NA",
                'TMS_task': "NA",
                'TMS_status': "NA"
                }

        if qa_task != None:

            task_related_data.update({'QA_task':qa_task.key,
                                    'QA_status': qa_task.fields.status.name,
                                    'QA_assignee': qa_task.fields.assignee,
                                    'QA_labels': ", ".join(qa_task.fields.labels)
                                    })


            auto_task = False
            tms_task = False

            for task in qa_task.fields.issuelinks:
                for issue_type in ('inwardIssue', 'outwardIssue'):
                    if hasattr(task, issue_type) and getattr(task, issue_type).fields.issuetype.name == 'Task':
                        if re.search('auto', getattr(task, issue_type).fields.summary, re.IGNORECASE):
                            auto_task = True
                            auto_task = getattr(task, issue_type)
                            task_related_data.update({'Auto_task':auto_task.key,
                                                    'Auto_status':  auto_task.fields.status.name,
                                                    })

                        if re.search('tms', getattr(task, issue_type).fields.summary, re.IGNORECASE):
                            tms_task = True
                            tms_task = getattr(task, issue_type)
                            task_related_data.update({'TMS_task': tms_task.key,
                                                    'TMS_status':  tms_task.fields.status.name,
                                                    })


        return task_related_data
    
    def get_qa_committed_task(self,feature_tasks):
        QA_committed_feature_tasks = []
        for task in feature_tasks:
            description = task.fields.description
            pattern =  r'#teams_committed.*?QA'
            QA_committed = re.search(pattern, description, re.IGNORECASE)
            if QA_committed:
                QA_committed_feature_tasks.append(task)

        return QA_committed_feature_tasks
        
    def fetch_tickets(self):
        feature_tasks = self.auth.search_issues(self.jql_query, maxResults=1000)
        QA_committed_feature_tasks = self.get_qa_committed_task(feature_tasks)
        required_data = []

        for index, feature_task in enumerate(QA_committed_feature_tasks):
            qa_task_available = False

            for link in feature_task.fields.issuelinks:
                linked_issue = getattr(link, 'inwardIssue', None) or getattr(link, 'outwardIssue', None)

                if link.raw['type'].get('inward') == 'Comprised of Task' and linked_issue:
                    if linked_issue.fields.issuetype.name == 'Task':
                        task_info = self.auth.issue(linked_issue.key)
                        triage_field = getattr(task_info.fields, 'customfield_14308', None)

                        if triage_field and triage_field[0] == '73317' and task_info.fields.status.name != 'Rejected':
                            qa_task_available = True
                            task_related_data = self.get_task_details(feature_task, task_info)
                            required_data.append(task_related_data)
                            print(f"Details updated for {feature_task.key}  ({index+1}/{len(QA_committed_feature_tasks)})\n")

            if not qa_task_available:
                task_related_data = self.get_task_details(feature_task)
                required_data.append(task_related_data)
                print(f"Details updated for {feature_task.key}  ({index+1}/{len(QA_committed_feature_tasks)})\n")

        data_df = pd.DataFrame(required_data)
        return data_df

                    
                    