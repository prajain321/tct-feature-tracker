from ticketfetchers.ticket_fetcher_optimized import TicketFetch
import pandas as pd
from database.schema import Database
import json

def comments_addition(rocm_version: str, ticket_id,comment):
    db = Database(rocm_version)
    return db.update_comments(ticket_id,comment)

def get_comments(rocm_version: str, ticket_id):
    db = Database(rocm_version)
    result = db.find(ticket_id)
    return result

def force_refetch_and_update(rocm_version: str, unique_key: str):
    db = Database(rocm_version)
    
    # Check if collection exists
    if not db.iscollection_present():
        print("Collection not present. Creating...")
        # Optionally create collection here or return False
        return False
    
    # print("Collection present")
    
    # Fetch tickets
    tf = TicketFetch(rocm_version=rocm_version, unique_key=unique_key, 
                     verbose=True, is_json=True, max_workers=6)
    data = tf.fetch_tickets()
    
    # Validate data
    if not data or len(data) == 0:
        print("No data fetched")
        return False
    
    print(f"Fetched {len(data)} tickets")
    
    # Parse JSON if needed
    try:
        tickets = json.loads(data) if isinstance(data, str) else data
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return False
    
    # Update/insert tickets
    updated_count = 0
    inserted_count = 0
    error_count = 0
    
    for ticket in tickets:
        try:
            ticket_id = ticket.get("_id")
            if not ticket_id:
                print(f"Warning: Ticket missing _id: {ticket}")
                continue
            
            # Check if ticket exists
            existing = db.find(ticket_id)
            
            if existing:
                # Update existing ticket
                update_data = {
                    'Feature_status': ticket.get('Feature_status'),
                    'Feature_summary': ticket.get('Feature_summary'),
                    'QA_task': ticket.get("QA_task"),
                    'QA_status': ticket.get('QA_status'),
                    'QA_assignee': ticket.get('QA_assignee'),
                    'QA_labels': ticket.get("QA_labels"),
                    'Auto_task': ticket.get("Auto_task"),
                    'Auto_status': ticket.get("Auto_status"),
                    'TMS_task': ticket.get("TMS_task"),
                    'TMS_status': ticket.get("TMS_status"),
                }
                
                result = db.update(ticket_id, update_data)
                if result:
                    updated_count += 1
                    print(f"Updated ticket: {ticket_id}")
                else:
                    print(f"Failed to update ticket: {ticket_id}")
                    error_count += 1
            else:
                # Insert new ticket
                print(f"Inserting new ticket: {ticket_id}")
                result = db.insert([ticket])
                if result:
                    inserted_count += 1
                else:
                    print(f"Failed to insert ticket: {ticket_id}")
                    error_count += 1
                    
        except Exception as e:
            print(f"Error processing ticket {ticket.get('_id', 'unknown')}: {e}")
            error_count += 1
    
    print(f"\nSummary:")
    print(f"  Updated: {updated_count}")
    print(f"  Inserted: {inserted_count}")
    print(f"  Errors: {error_count}")
    
    return updated_count + inserted_count > 0


def balance(rocm_version: str, unique_key: str):
    db = Database(rocm_version)
    if db.iscollection_present():
        return list(db.find_all())
    else:
        print("Collection not present, fetching tickets...")
        tf = TicketFetch(rocm_version=rocm_version, unique_key=unique_key, 
                        verbose=True, is_json=True, max_workers=6)
        
        try:
            data = tf.fetch_tickets()
            tickets = json.loads(data) if isinstance(data, str) else data
            
            if db.insert(tickets):
                return list(db.find_all())
            else:
                print("Failed to insert tickets")
                return False
        except Exception as e:
            print(f"Error in balance: {e}")
            return False
        
# print(comments_addition("7.2" , "SWDEV-564650|SWDEV-564653", "This is a comment"))
# print(get_comments("7.2" , "SWDEV-564650|SWDEV-564653"))